"""Tests for tap_ocr skip_if_texts_present behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.actions.engine import ActionEngine
from imouse_farm.config.models import ActionRequest, ActionType


@pytest.mark.asyncio
async def test_tap_ocr_skips_when_co_present_text_on_screen() -> None:
    ctrl = MagicMock()
    ctrl.find_text_on_device = AsyncMock(return_value=[])
    ctrl.ocr_items_on_device = AsyncMock(
        return_value=[
            {"text": "Your", "x": 60, "y": 650},
            {"text": "Story", "x": 110, "y": 650},
            {"text": "Next", "x": 350, "y": 650},
        ]
    )
    ctrl.tap = AsyncMock()

    device_manager = MagicMock()
    device_manager.get_device.return_value = MagicMock(screen_width=406, screen_height=720)

    engine = ActionEngine(
        config=MagicMock(),
        controller=ctrl,
        device_manager=device_manager,
        db=MagicMock(),
    )

    request = ActionRequest(
        device_id="device-1",
        action_type=ActionType.TAP_OCR,
        params={
            "texts": ["Next"],
            "optional": True,
            "skip_if_texts_present": ["Your Story"],
            "skip_if_ocr_ex": True,
        },
        step_name="test_skip",
    )
    ok = await engine._run_action(request)

    assert ok is True
    ctrl.tap.assert_not_called()


@pytest.mark.asyncio
async def test_tap_ocr_taps_when_skip_text_absent() -> None:
    async def find_side_effect(_id: str, texts: list[str], **_kw: object) -> list[dict[str, object]]:
        if texts and texts[0] in ("Next", "NEXT"):
            return [{"text": "Next", "x": 350, "y": 650, "confidence": 0.9}]
        return []

    ctrl = MagicMock()
    ctrl.find_text_on_device = AsyncMock(side_effect=find_side_effect)
    ctrl.ocr_items_on_device = AsyncMock(return_value=[])
    ctrl.tap = AsyncMock(return_value=True)

    device_manager = MagicMock()
    device_manager.get_device.return_value = MagicMock(screen_width=406, screen_height=720)

    engine = ActionEngine(
        config=MagicMock(),
        controller=ctrl,
        device_manager=device_manager,
        db=MagicMock(),
    )

    request = ActionRequest(
        device_id="device-1",
        action_type=ActionType.TAP_OCR,
        params={
            "texts": ["Next"],
            "optional": True,
            "skip_if_texts_present": ["Your Story"],
        },
        step_name="test_tap",
    )
    ok = await engine._run_action(request)

    assert ok is True
    ctrl.tap.assert_called_once_with("device-1", 350, 650)
