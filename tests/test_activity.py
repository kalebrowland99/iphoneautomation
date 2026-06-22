"""Tests for activity log repository."""

from __future__ import annotations

import pytest

from imouse_farm.database.repository import DatabaseRepository


@pytest.mark.asyncio
async def test_activity_log_roundtrip(tmp_path) -> None:
    db = DatabaseRepository(str(tmp_path / "test.db"))
    await db.connect()

    entry = await db.log_activity(
        "info",
        "workflow",
        "→ open_shadowrocket",
        "AA:BB:CC:DD:EE:FF",
        {"workflow": "tiktok_prep", "step_type": "execute_action"},
    )
    assert entry["id"] > 0
    assert entry["message"] == "→ open_shadowrocket"

    rows = await db.get_activity_logs(device_id="AA:BB:CC:DD:EE:FF", limit=10)
    assert len(rows) == 1
    assert rows[0]["details"]["workflow"] == "tiktok_prep"

    await db.close()
