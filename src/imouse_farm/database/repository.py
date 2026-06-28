"""SQLite database repository for state tracking."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

import aiosqlite

from imouse_farm.config.models import DeviceState
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

ActivityCallback = Callable[[dict[str, Any]], Awaitable[None]]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class DatabaseRepository:
    """Async SQLite repository for all persistent state."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._activity_callbacks: list[ActivityCallback] = []

    def on_activity(self, callback: ActivityCallback) -> None:
        self._activity_callbacks.append(callback)

    async def connect(self) -> None:
        """Open database connection and initialize schema."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        schema_path = Path(__file__).parent / "schema.sql"
        schema = schema_path.read_text(encoding="utf-8")
        await self._conn.executescript(schema)
        await self._migrate()
        await self._conn.commit()
        logger.info("database_connected", path=self._db_path)

    async def _migrate(self) -> None:
        """Apply additive schema migrations."""
        migrations = [
            "ALTER TABLE devices ADD COLUMN last_action TEXT",
            "ALTER TABLE devices ADD COLUMN workflow_name TEXT",
            "ALTER TABLE devices ADD COLUMN error_count INTEGER DEFAULT 0",
        ]
        for sql in migrations:
            try:
                await self.conn.execute(sql)
            except Exception:
                pass  # column already exists

    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected")
        return self._conn

    # --- Devices ---

    async def upsert_device(
        self,
        device_id: str,
        *,
        name: str | None = None,
        group_name: str = "default",
        model: str | None = None,
        ios_version: str | None = None,
        screen_width: int | None = None,
        screen_height: int | None = None,
        is_online: bool = True,
        current_state: DeviceState = DeviceState.IDLE,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = _utcnow()
        await self.conn.execute(
            """
            INSERT INTO devices (id, name, group_name, model, ios_version,
                screen_width, screen_height, is_online, current_state,
                last_seen_at, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=COALESCE(excluded.name, devices.name),
                group_name=excluded.group_name,
                model=COALESCE(excluded.model, devices.model),
                ios_version=COALESCE(excluded.ios_version, devices.ios_version),
                screen_width=COALESCE(excluded.screen_width, devices.screen_width),
                screen_height=COALESCE(excluded.screen_height, devices.screen_height),
                is_online=excluded.is_online,
                current_state=excluded.current_state,
                last_seen_at=excluded.last_seen_at,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (
                device_id,
                name,
                group_name,
                model,
                ios_version,
                screen_width,
                screen_height,
                int(is_online),
                current_state.value,
                now,
                json.dumps(metadata or {}),
                now,
                now,
            ),
        )
        await self.conn.commit()

    async def set_device_online(self, device_id: str, is_online: bool) -> None:
        state = DeviceState.IDLE.value if is_online else DeviceState.DISCONNECTED.value
        await self.conn.execute(
            "UPDATE devices SET is_online=?, current_state=?, last_seen_at=?, updated_at=? WHERE id=?",
            (int(is_online), state, _utcnow(), _utcnow(), device_id),
        )
        await self.conn.commit()

    async def get_device(self, device_id: str) -> dict[str, Any] | None:
        async with self.conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def list_devices(self, group_name: str | None = None) -> list[dict[str, Any]]:
        if group_name:
            query = "SELECT * FROM devices WHERE group_name=? ORDER BY id"
            params: tuple[Any, ...] = (group_name,)
        else:
            query = "SELECT * FROM devices ORDER BY id"
            params = ()
        async with self.conn.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def update_device_state(self, device_id: str, state: DeviceState, reason: str = "") -> None:
        device = await self.get_device(device_id)
        from_state = device["current_state"] if device else None
        await self.conn.execute(
            "UPDATE devices SET current_state=?, updated_at=? WHERE id=?",
            (state.value, _utcnow(), device_id),
        )
        await self.conn.execute(
            """
            INSERT INTO state_transitions (device_id, from_state, to_state, reason)
            VALUES (?, ?, ?, ?)
            """,
            (device_id, from_state, state.value, reason),
        )
        await self.conn.commit()

    async def update_device_runtime(
        self,
        device_id: str,
        *,
        last_action: str | None = None,
        workflow_name: str | None = None,
        error_count: int | None = None,
    ) -> None:
        updates: list[str] = ["updated_at=?"]
        params: list[Any] = [_utcnow()]
        if last_action is not None:
            updates.append("last_action=?")
            params.append(last_action)
        if workflow_name is not None:
            updates.append("workflow_name=?")
            params.append(workflow_name)
        if error_count is not None:
            updates.append("error_count=?")
            params.append(error_count)
        params.append(device_id)
        await self.conn.execute(
            f"UPDATE devices SET {', '.join(updates)} WHERE id=?",
            params,
        )
        await self.conn.commit()

    async def increment_error_count(self, device_id: str) -> int:
        await self.conn.execute(
            "UPDATE devices SET error_count = error_count + 1, updated_at=? WHERE id=?",
            (_utcnow(), device_id),
        )
        await self.conn.commit()
        device = await self.get_device(device_id)
        return int(device["error_count"]) if device else 0

    # --- Screenshots ---

    async def save_screenshot(
        self,
        device_id: str,
        file_path: str,
        width: int | None = None,
        height: int | None = None,
        workflow_id: str | None = None,
    ) -> int:
        async with self.conn.execute(
            """
            INSERT INTO screenshots (device_id, file_path, width, height, workflow_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (device_id, file_path, width, height, workflow_id),
        ) as cur:
            await self.conn.commit()
            return cur.lastrowid or 0

    async def get_latest_screenshot(self, device_id: str) -> dict[str, Any] | None:
        async with self.conn.execute(
            "SELECT * FROM screenshots WHERE device_id=? ORDER BY captured_at DESC LIMIT 1",
            (device_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def list_screenshots(self, device_id: str, limit: int = 20) -> list[dict[str, Any]]:
        async with self.conn.execute(
            "SELECT * FROM screenshots WHERE device_id=? ORDER BY captured_at DESC LIMIT ?",
            (device_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def delete_old_screenshots(self, before: str) -> list[str]:
        async with self.conn.execute(
            "SELECT file_path FROM screenshots WHERE captured_at < ?", (before,)
        ) as cur:
            rows = await cur.fetchall()
            paths = [r["file_path"] for r in rows]
        if paths:
            await self.conn.execute("DELETE FROM screenshots WHERE captured_at < ?", (before,))
            await self.conn.commit()
        return paths

    # --- Actions ---

    async def log_action_start(
        self,
        device_id: str,
        action_type: str,
        params: dict[str, Any],
        workflow_id: str | None = None,
        step_name: str | None = None,
    ) -> int:
        async with self.conn.execute(
            """
            INSERT INTO action_history (device_id, action_type, params_json, status, workflow_id, step_name)
            VALUES (?, ?, ?, 'running', ?, ?)
            """,
            (device_id, action_type, json.dumps(params), workflow_id, step_name),
        ) as cur:
            await self.conn.commit()
            return cur.lastrowid or 0

    async def log_action_complete(
        self,
        action_id: int,
        status: str,
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        await self.conn.execute(
            """
            UPDATE action_history SET status=?, error_message=?, completed_at=?, duration_ms=?
            WHERE id=?
            """,
            (status, error_message, _utcnow(), duration_ms, action_id),
        )
        await self.conn.commit()

        async with self.conn.execute(
            "SELECT * FROM action_history WHERE id=?", (action_id,)
        ) as cur:
            row = await cur.fetchone()
        if row:
            action = dict(row)
            step = action.get("step_name") or ""
            action_type = action.get("action_type") or "action"
            workflow = action.get("workflow_id") or ""
            label = f"{step}: {action_type}" if step else action_type
            if status == "success":
                msg = f"{label} OK"
                if duration_ms is not None:
                    msg += f" ({duration_ms}ms)"
                level = "info"
            else:
                msg = f"{label} failed"
                if error_message:
                    msg += f" — {error_message}"
                level = "warn"
            await self.log_activity(
                level,
                "action",
                msg,
                action.get("device_id"),
                {
                    "action_type": action_type,
                    "step_name": step,
                    "workflow": workflow,
                    "status": status,
                    "duration_ms": duration_ms,
                    "error_message": error_message,
                },
            )

    async def get_action_history(self, device_id: str, limit: int = 50) -> list[dict[str, Any]]:
        async with self.conn.execute(
            "SELECT * FROM action_history WHERE device_id=? ORDER BY started_at DESC LIMIT ?",
            (device_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def count_recent_failures(self, device_id: str, since: str) -> int:
        async with self.conn.execute(
            """
            SELECT COUNT(*) as cnt FROM action_history
            WHERE device_id=? AND status='failed' AND started_at > ?
            """,
            (device_id, since),
        ) as cur:
            row = await cur.fetchone()
            return row["cnt"] if row else 0

    # --- Errors ---

    async def log_error(
        self,
        error_type: str,
        message: str,
        device_id: str | None = None,
        details: dict[str, Any] | None = None,
        escalated: bool = False,
    ) -> int:
        async with self.conn.execute(
            """
            INSERT INTO error_logs (device_id, error_type, message, details_json, escalated)
            VALUES (?, ?, ?, ?, ?)
            """,
            (device_id, error_type, message, json.dumps(details or {}), int(escalated)),
        ) as cur:
            await self.conn.commit()
            error_id = cur.lastrowid or 0
        await self.log_activity(
            "error",
            "error",
            f"{error_type}: {message}",
            device_id,
            {"error_type": error_type, "escalated": escalated, **(details or {}), "error_id": error_id},
        )
        return error_id

    async def get_error_history(self, device_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if device_id:
            query = "SELECT * FROM error_logs WHERE device_id=? ORDER BY created_at DESC LIMIT ?"
            params: tuple[Any, ...] = (device_id, limit)
        else:
            query = "SELECT * FROM error_logs ORDER BY created_at DESC LIMIT ?"
            params = (limit,)
        async with self.conn.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # --- Activity log ---

    async def log_activity(
        self,
        level: str,
        category: str,
        message: str,
        device_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _utcnow()
        async with self.conn.execute(
            """
            INSERT INTO activity_logs (device_id, level, category, message, details_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (device_id, level, category, message, json.dumps(details or {}), now),
        ) as cur:
            await self.conn.commit()
            row_id = cur.lastrowid or 0
        entry: dict[str, Any] = {
            "id": row_id,
            "device_id": device_id,
            "level": level,
            "category": category,
            "message": message,
            "details": details or {},
            "created_at": now,
        }
        for cb in self._activity_callbacks:
            try:
                await cb(entry)
            except Exception as exc:
                logger.error("activity_callback_failed", error=str(exc))
        return entry

    async def get_activity_logs(
        self,
        *,
        device_id: str | None = None,
        level: str | None = None,
        category: str | None = None,
        limit: int = 100,
        since_id: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if device_id:
            clauses.append("device_id=?")
            params.append(device_id)
        if level:
            clauses.append("level=?")
            params.append(level)
        if category:
            clauses.append("category=?")
            params.append(category)
        if since_id is not None:
            clauses.append("id > ?")
            params.append(since_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM activity_logs {where} ORDER BY id DESC LIMIT ?"
        params.append(limit)
        async with self.conn.execute(query, params) as cur:
            rows = await cur.fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["details"] = json.loads(item.pop("details_json", "{}") or "{}")
            except json.JSONDecodeError:
                item["details"] = {}
            result.append(item)
        return result

    async def clear_activity_logs(self) -> None:
        await self.conn.execute("DELETE FROM activity_logs")
        await self.conn.commit()

    # --- State transitions ---

    async def get_state_transitions(self, device_id: str, limit: int = 20) -> list[dict[str, Any]]:
        async with self.conn.execute(
            "SELECT * FROM state_transitions WHERE device_id=? ORDER BY transitioned_at DESC LIMIT ?",
            (device_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # --- Workflow runs ---

    async def start_workflow_run(self, workflow_name: str, device_id: str) -> int:
        async with self.conn.execute(
            "INSERT INTO workflow_runs (workflow_name, device_id) VALUES (?, ?)",
            (workflow_name, device_id),
        ) as cur:
            await self.conn.commit()
            return cur.lastrowid or 0

    async def complete_workflow_run(
        self, run_id: int, status: str, error_message: str | None = None
    ) -> None:
        await self.conn.execute(
            "UPDATE workflow_runs SET status=?, completed_at=?, error_message=? WHERE id=?",
            (status, _utcnow(), error_message, run_id),
        )
        await self.conn.commit()

    async def get_active_workflow_runs(self) -> list[dict[str, Any]]:
        async with self.conn.execute(
            "SELECT * FROM workflow_runs WHERE status='running' ORDER BY started_at DESC"
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]
