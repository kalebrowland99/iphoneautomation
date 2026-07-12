"""Device discovery, tracking, and auto-reconnect via DeviceController."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Awaitable

from imouse_farm.config.models import AppConfig, DeviceState
from imouse_farm.controller.device_controller import DeviceController, DeviceStatus
from imouse_farm.database.repository import DatabaseRepository
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class ManagedDevice:
    """In-memory representation of a managed device."""

    device_id: str
    device_name: str = ""
    phone_name: str = ""
    user_name: str = ""
    group_name: str = "default"
    model: str = ""
    ios_version: str = ""
    screen_width: int = 0
    screen_height: int = 0
    is_online: bool = False
    current_state: DeviceState = DeviceState.DISCONNECTED
    last_seen_at: datetime | None = None
    last_activity_at: datetime | None = None
    last_action: str = ""
    workflow_name: str = ""
    error_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    consecutive_failures: int = 0
    unknown_screen_count: int = 0
    workflow_paused: bool = False

    @property
    def display_label(self) -> str:
        parts: list[str] = []
        if self.user_name:
            parts.append(f"Phone {self.user_name}")
        if self.phone_name:
            parts.append(self.phone_name)
        elif self.device_name and self.device_name != self.device_id:
            parts.append(self.device_name)
        if self.device_name and self.phone_name and self.device_name != self.phone_name:
            parts.append(f"({self.device_name})")
        return " · ".join(parts) if parts else self.device_id


class DeviceManager:
    """Detect, track, and reconnect devices through the iMouseXP SDK."""

    def __init__(
        self,
        config: AppConfig,
        controller: DeviceController,
        db: DatabaseRepository,
    ) -> None:
        self._config = config
        self._controller = controller
        self._db = db
        self._devices: dict[str, ManagedDevice] = {}
        self._poll_task: asyncio.Task[None] | None = None
        self._startup_task: asyncio.Task[None] | None = None
        self._running = False
        self._event_callbacks: list[EventCallback] = []
        self._reconnect_queue: set[str] = set()
        self._last_airplay_attempt: dict[str, datetime] = {}
        self._tap_locks: dict[str, asyncio.Lock] = {}

    @property
    def controller(self) -> DeviceController:
        return self._controller

    @property
    def devices(self) -> dict[str, ManagedDevice]:
        return dict(self._devices)

    def get_device(self, device_id: str) -> ManagedDevice | None:
        return self._devices.get(device_id)

    def get_tap_lock(self, device_id: str) -> asyncio.Lock:
        """Return the per-device tap lock (created on first access).

        The workflow engine holds this lock during every touch action so the
        permission watcher cannot tap at the same time.
        """
        if device_id not in self._tap_locks:
            self._tap_locks[device_id] = asyncio.Lock()
        return self._tap_locks[device_id]

    def on_event(self, callback: EventCallback) -> None:
        self._event_callbacks.append(callback)

    async def _emit(self, event: str, data: dict[str, Any]) -> None:
        for cb in self._event_callbacks:
            try:
                await cb(event, data)
            except Exception as exc:
                logger.error("event_callback_failed", event=event, error=str(exc))

    async def start(self) -> None:
        self._running = True
        await self._load_from_db()
        await self.refresh_devices()
        self._poll_task = asyncio.create_task(self._poll_loop())
        if self._config.imouse.airplay_reconnect_on_startup:
            self._startup_task = asyncio.create_task(self._startup_airplay_reconnect())
        logger.info("device_manager_started")

    async def stop(self) -> None:
        self._running = False
        for task in (self._poll_task, self._startup_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info("device_manager_stopped")

    async def _load_from_db(self) -> None:
        rows = await self._db.list_devices()
        for row in rows:
            device = ManagedDevice(
                device_id=row["id"],
                device_name=row.get("name") or "",
                phone_name=(row.get("metadata_json") and _meta_str(row, "device_name")) or row.get("name") or row["id"],
                user_name=_meta_str(row, "user_name"),
                group_name=row.get("group_name", "default"),
                model=row.get("model", ""),
                ios_version=row.get("ios_version", ""),
                screen_width=row.get("screen_width") or 0,
                screen_height=row.get("screen_height") or 0,
                is_online=bool(row.get("is_online")),
                current_state=DeviceState(row.get("current_state", "DISCONNECTED")),
                last_action=row.get("last_action") or "",
                workflow_name=row.get("workflow_name") or "",
                error_count=int(row.get("error_count") or 0),
            )
            self._devices[device.device_id] = device
            if row.get("is_online"):
                self._reconnect_queue.add(device.device_id)
            elif row.get("last_seen_at"):
                try:
                    last_raw = row["last_seen_at"]
                    last = datetime.fromisoformat(
                        last_raw.replace("Z", "+00:00") if isinstance(last_raw, str) else last_raw
                    )
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    if (datetime.now(timezone.utc) - last).total_seconds() < 7200:
                        self._reconnect_queue.add(device.device_id)
                except Exception:
                    pass

    async def reconnect_airplay(self, device_id: str) -> bool:
        """Manually reconnect AirPlay for one device (dashboard Connect button)."""
        return await self._try_reconnect_airplay(device_id, force=True, manual=True)

    async def disconnect_airplay(self, device_id: str) -> bool:
        """Disconnect AirPlay cast for one device."""
        success = await self._controller.disconnect_device(device_id)
        await asyncio.sleep(1)
        await self.refresh_devices()
        device = self._devices.get(device_id)
        if device and device.is_online:
            device.is_online = False
            device.current_state = DeviceState.DISCONNECTED
            await self._db.set_device_online(device_id, False)
            await self._db.update_device_state(device_id, DeviceState.DISCONNECTED, "airplay_disconnected")
            await self._emit("device_disconnected", {"device_id": device_id})
        logger.info("airplay_disconnect", device_id=device_id, success=success)
        return success

    async def _startup_airplay_reconnect(self) -> None:
        """Re-establish AirPlay for devices that were online before restart."""
        delay = self._config.imouse.airplay_connect_delay_seconds
        await asyncio.sleep(delay)
        if not self._reconnect_queue:
            logger.info("airplay_startup_reconnect_skipped", reason="no_devices_were_online")
            return
        logger.info(
            "airplay_startup_reconnect",
            device_count=len(self._reconnect_queue),
            devices=list(self._reconnect_queue),
        )
        for device_id in list(self._reconnect_queue):
            if not self._running:
                return
            await self._try_reconnect_airplay(device_id, force=True)
            await asyncio.sleep(1)
        await self.refresh_devices()

    async def _try_reconnect_airplay(
        self, device_id: str, *, force: bool = False, manual: bool = False
    ) -> bool:
        if not manual and not self._config.imouse.auto_airplay_reconnect:
            return False
        device = self._devices.get(device_id)
        if device and device.is_online and not force:
            return True
        now = datetime.now(timezone.utc)
        last = self._last_airplay_attempt.get(device_id)
        interval = self._config.imouse.airplay_reconnect_interval_seconds
        if not force and last and (now - last).total_seconds() < interval:
            return False
        self._last_airplay_attempt[device_id] = now

        logger.info("airplay_reconnect_attempt", device_id=device_id)
        success = await self._controller.connect_device(device_id)
        if success:
            await asyncio.sleep(2)
            await self.refresh_devices()
            device = self._devices.get(device_id)
            if device and device.is_online:
                self._reconnect_queue.discard(device_id)
                await self._emit("device_connected", {"device_id": device_id})
                logger.info("airplay_reconnect_success", device_id=device_id)
                return True
        logger.warning("airplay_reconnect_failed", device_id=device_id)
        return False

    async def _maybe_reconnect_offline_devices(self) -> None:
        if not self._config.imouse.auto_airplay_reconnect or not self._reconnect_queue:
            return
        for device_id in list(self._reconnect_queue):
            device = self._devices.get(device_id)
            if device and device.is_online:
                self._reconnect_queue.discard(device_id)
                continue
            await self._try_reconnect_airplay(device_id)

    async def refresh_devices(self) -> list[ManagedDevice]:
        if not self._controller.is_connected:
            try:
                await self._controller.connect()
            except Exception as exc:
                logger.error("sdk_connect_failed", error=str(exc))
                return list(self._devices.values())

        discovered = await self._controller.enumerate_devices()
        discovered_ids = {d.device_id for d in discovered}
        now = datetime.now(timezone.utc)

        for info in discovered:
            await self._register_device(info, now)

        for device_id, device in list(self._devices.items()):
            if device_id not in discovered_ids and device.is_online:
                await self._mark_offline(device_id)

        return list(self._devices.values())

    async def _register_device(self, info: DeviceStatus, now: datetime) -> None:
        group_name = self._resolve_group(info.device_id)
        existing = self._devices.get(info.device_id)

        if existing:
            existing.device_name = info.device_name or existing.device_name
            existing.phone_name = info.phone_name or existing.phone_name
            existing.user_name = info.user_name or existing.user_name
            existing.model = info.model or existing.model
            existing.ios_version = info.ios_version or existing.ios_version
            existing.screen_width = info.screen_width or existing.screen_width
            existing.screen_height = info.screen_height or existing.screen_height
            existing.is_online = info.is_online
            existing.last_seen_at = now
            if info.is_online:
                if existing.current_state == DeviceState.DISCONNECTED:
                    existing.current_state = DeviceState.IDLE
                    await self._db.update_device_state(info.device_id, DeviceState.IDLE, "reconnected")
            elif existing.current_state != DeviceState.DISCONNECTED:
                existing.current_state = DeviceState.DISCONNECTED
        else:
            device = ManagedDevice(
                device_id=info.device_id,
                device_name=info.device_name,
                phone_name=info.phone_name,
                user_name=info.user_name,
                group_name=group_name,
                model=info.model,
                ios_version=info.ios_version,
                screen_width=info.screen_width,
                screen_height=info.screen_height,
                is_online=info.is_online,
                current_state=DeviceState.IDLE if info.is_online else DeviceState.DISCONNECTED,
                last_seen_at=now,
                last_activity_at=now,
                metadata=info.raw,
            )
            self._devices[info.device_id] = device
            if info.is_online:
                await self._emit("device_connected", {"device_id": info.device_id})
            logger.info(
                "device_registered",
                device_id=info.device_id,
                label=device.display_label,
                online=info.is_online,
            )

        await self._db.upsert_device(
            info.device_id,
            name=info.device_name,
            group_name=group_name,
            model=info.model,
            ios_version=info.ios_version,
            screen_width=info.screen_width,
            screen_height=info.screen_height,
            is_online=info.is_online,
            current_state=DeviceState.IDLE if info.is_online else DeviceState.DISCONNECTED,
            metadata=info.raw,
        )

    async def _mark_offline(self, device_id: str) -> None:
        device = self._devices.get(device_id)
        if not device:
            return
        device.is_online = False
        device.current_state = DeviceState.DISCONNECTED
        device.workflow_name = ""
        self._reconnect_queue.add(device_id)
        await self._db.set_device_online(device_id, False)
        await self._db.update_device_state(device_id, DeviceState.DISCONNECTED, "device_lost")
        await self._db.update_device_runtime(device_id, workflow_name="")
        await self._emit("device_disconnected", {"device_id": device_id})
        logger.warning("device_disconnected", device_id=device_id, timestamp=_utcnow_iso())

    def _resolve_group(self, device_id: str) -> str:
        existing = self._devices.get(device_id)
        return existing.group_name if existing else "default"

    async def set_state(self, device_id: str, state: DeviceState, reason: str = "") -> None:
        device = self._devices.get(device_id)
        if not device:
            return
        device.current_state = state
        device.last_activity_at = datetime.now(timezone.utc)
        await self._db.update_device_state(device_id, state, reason)
        logger.info(
            "state_changed",
            device_id=device_id,
            state=state.value,
            reason=reason,
            timestamp=_utcnow_iso(),
        )
        await self._emit("state_changed", {"device_id": device_id, "state": state.value})

    async def set_last_action(self, device_id: str, action: str) -> None:
        device = self._devices.get(device_id)
        if device:
            device.last_action = action
        await self._db.update_device_runtime(device_id, last_action=action)

    async def set_workflow(self, device_id: str, workflow_name: str) -> None:
        device = self._devices.get(device_id)
        if device:
            device.workflow_name = workflow_name
        await self._db.update_device_runtime(device_id, workflow_name=workflow_name)

    async def pause_workflow(self, device_id: str) -> None:
        device = self._devices.get(device_id)
        if device:
            device.workflow_paused = True

    async def is_workflow_paused(self, device_id: str) -> bool:
        device = self._devices.get(device_id)
        return device.workflow_paused if device else False

    async def resume_workflow(self, device_id: str) -> None:
        device = self._devices.get(device_id)
        if device:
            device.workflow_paused = False

    async def reset_phone_and_recast(
        self,
        device_id: str,
        *,
        boot_wait_seconds: float | None = None,
        max_cast_attempts: int | None = None,
        cast_retry_seconds: float | None = None,
    ) -> None:
        """Reboot phone, wait for boot, then reconnect AirPlay cast."""
        boot_wait = float(
            boot_wait_seconds
            if boot_wait_seconds is not None
            else self._config.diagnostics.phone_restart_boot_wait_seconds
        )
        attempts = max(1, int(
            max_cast_attempts
            if max_cast_attempts is not None
            else self._config.batch.cast_connect_max_attempts
        ))
        retry_s = float(
            cast_retry_seconds
            if cast_retry_seconds is not None
            else self._config.batch.cast_connect_retry_seconds
        )

        if not await self._controller.restart_device(device_id):
            raise RuntimeError("Phone restart command failed")

        await self._db.log_activity(
            "warn",
            "device",
            f"Phone rebooting — waiting {int(boot_wait)}s before recast",
            device_id,
        )
        await asyncio.sleep(boot_wait)

        # After reboot, re-sync iMouse hardware then mouse before AirPlay connect.
        # USB restart + mouse reset often unsticks cast-after-reboot failures.
        await self._db.log_activity(
            "info",
            "device",
            "Resetting iMouse USB hardware before recast",
            device_id,
        )
        if not await self._controller.restart_usb(device_id):
            await self._db.log_activity(
                "warn",
                "device",
                "USB hardware restart failed — continuing with mouse reset + cast",
                device_id,
            )
        else:
            await asyncio.sleep(5.0)

        await self._db.log_activity(
            "info",
            "device",
            "Resetting mouse before hardware AirPlay cast",
            device_id,
        )
        await self._controller.reset_cursor(device_id)
        await asyncio.sleep(0.25)
        await self._controller.reset_cursor(device_id)
        await asyncio.sleep(0.5)

        for attempt in range(1, attempts + 1):
            await self.refresh_devices()
            await self._db.log_activity(
                "info",
                "device",
                f"Hardware AirPlay cast after phone reset (attempt {attempt}/{attempts})",
                device_id,
            )
            if await self.reconnect_airplay(device_id):
                device = self._devices.get(device_id)
                if device and device.is_online:
                    await self._controller.reset_cursor(device_id)
                    await self._db.log_activity(
                        "info",
                        "device",
                        f"Cast reconnected after phone reset (attempt {attempt}/{attempts})",
                        device_id,
                    )
                    return
            await self._db.log_activity(
                "warn",
                "device",
                f"Cast reconnect after phone reset failed (attempt {attempt}/{attempts})",
                device_id,
            )
            if attempt < attempts:
                await self._controller.reset_cursor(device_id)
                await asyncio.sleep(retry_s)

        raise RuntimeError(
            f"AirPlay reconnect failed after phone reset ({attempts} attempts)"
        )

    async def record_activity(self, device_id: str) -> None:
        device = self._devices.get(device_id)
        if device:
            device.last_activity_at = datetime.now(timezone.utc)
            device.consecutive_failures = 0

    async def record_failure(self, device_id: str) -> int:
        device = self._devices.get(device_id)
        if not device:
            return 0
        device.consecutive_failures += 1
        device.error_count = await self._db.increment_error_count(device_id)
        return device.consecutive_failures

    async def is_frozen(self, device_id: str) -> bool:
        device = self._devices.get(device_id)
        if not device or not device.last_activity_at:
            return False
        if device.workflow_paused:
            return False
        if device.current_state == DeviceState.ERROR:
            return False
        threshold = self._config.timing.frozen_device_threshold_seconds
        elapsed = (datetime.now(timezone.utc) - device.last_activity_at).total_seconds()
        return elapsed > threshold and device.is_online

    async def _poll_loop(self) -> None:
        interval = self._config.imouse.device_poll_interval_seconds
        reconnect_interval = self._config.imouse.reconnect_interval_seconds

        while self._running:
            try:
                if not self._controller.is_connected:
                    try:
                        await self._controller.reconnect()
                    except Exception as exc:
                        logger.warning("sdk_reconnect_failed", error=str(exc))
                        await asyncio.sleep(reconnect_interval)
                        continue
                await self.refresh_devices()
                await self._maybe_reconnect_offline_devices()
            except Exception as exc:
                logger.error("device_poll_error", error=str(exc))
            await asyncio.sleep(interval)

    def devices_in_group(self, group_name: str) -> list[ManagedDevice]:
        return [d for d in self._devices.values() if d.group_name == group_name and d.is_online]

    def to_dict(self, device: ManagedDevice) -> dict[str, Any]:
        return {
            "device_id": device.device_id,
            "device_name": device.device_name,
            "phone_name": device.phone_name,
            "user_name": device.user_name,
            "display_label": device.display_label,
            "name": device.display_label,
            "group_name": device.group_name,
            "model": device.model,
            "ios_version": device.ios_version,
            "screen_width": device.screen_width,
            "screen_height": device.screen_height,
            "is_online": device.is_online,
            "connected": device.is_online,
            "current_state": device.current_state.value,
            "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
            "last_action": device.last_action,
            "workflow_name": device.workflow_name,
            "error_count": device.error_count,
            "workflow_paused": device.workflow_paused,
            "consecutive_failures": device.consecutive_failures,
            "unknown_screen_count": device.unknown_screen_count,
        }


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta_str(row: dict[str, Any], key: str) -> str:
    import json
    raw = row.get("metadata_json")
    if not raw:
        return ""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return str(data.get(key, "") or "")
    except Exception:
        return ""
