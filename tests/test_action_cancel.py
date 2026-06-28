"""Tests for cooperative action cancellation on Kill / Stop."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.actions.cancel import clear_cancelled, is_cancelled, mark_cancelled
from imouse_farm.actions.engine import ActionEngine
from imouse_farm.actions.pre_touch_reset import pre_touch_mouse_reset
from imouse_farm.config.models import ActionRequest, ActionType


@pytest.mark.asyncio
async def test_pre_touch_mouse_reset_skips_when_cancelled() -> None:
    ctrl = MagicMock()
    ctrl.reset_cursor = AsyncMock(return_value=True)
    device_id = "device-1"
    mark_cancelled(device_id)
    try:
        await pre_touch_mouse_reset(ctrl, device_id, step_name="test")
        ctrl.reset_cursor.assert_not_awaited()
    finally:
        clear_cancelled(device_id)


@pytest.mark.asyncio
async def test_tap_ocr_aborts_when_cancelled_mid_poll() -> None:
    calls = {"n": 0}

    async def find_side_effect(_device_id: str, texts: list[str], **_kw: object) -> list[dict]:
        calls["n"] += 1
        if calls["n"] >= 2:
            mark_cancelled("device-1")
        return []

    ctrl = MagicMock()
    ctrl.find_text_on_device = AsyncMock(side_effect=find_side_effect)
    ctrl.tap = AsyncMock(return_value=True)

    device_manager = MagicMock()
    device_manager.get_device.return_value = MagicMock(screen_width=406, screen_height=720)

    engine = ActionEngine(
        config=MagicMock(),
        controller=ctrl,
        device_manager=device_manager,
        db=MagicMock(),
    )
    clear_cancelled("device-1")

    ok = await engine._run_action(
        ActionRequest(
            device_id="device-1",
            action_type=ActionType.TAP_OCR,
            params={
                "texts": ["Hvitserk's choice"],
                "optional": False,
                "wait_timeout_seconds": 1.0,
                "poll_interval_seconds": 0.01,
            },
            step_name="test_cancel_poll",
        )
    )

    assert ok is False
    assert calls["n"] >= 2
    ctrl.tap.assert_not_awaited()
    clear_cancelled("device-1")


def test_mark_and_clear_cancelled() -> None:
    device_id = "phone-7"
    clear_cancelled(device_id)
    assert not is_cancelled(device_id)
    mark_cancelled(device_id)
    assert is_cancelled(device_id)
    clear_cancelled(device_id)
    assert not is_cancelled(device_id)
