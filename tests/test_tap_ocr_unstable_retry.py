"""Tests for tap_ocr unstable-network retry after favorites."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.actions.cancel import clear_cancelled
from imouse_farm.actions.engine import ActionEngine
from imouse_farm.config.models import ActionRequest, ActionType

_HVITSERK = "Hvitserk's choice"
_UNSTABLE = "Your network is unstable. Tap to retry."


@pytest.mark.asyncio
async def test_tap_ocr_unstable_retry_finds_hvitserk_in_phase1() -> None:
    clear_cancelled("device-1")
    ctrl = MagicMock()
    ctrl.find_text_on_device = AsyncMock(
        return_value=[{"text": _HVITSERK, "x": 120, "y": 400, "confidence": 0.9}]
    )
    ctrl.tap = AsyncMock(return_value=True)

    device_manager = MagicMock()
    device_manager.get_device.return_value = MagicMock(screen_width=406, screen_height=720)

    engine = ActionEngine(
        config=MagicMock(),
        controller=ctrl,
        device_manager=device_manager,
        db=MagicMock(),
    )

    ok = await engine._run_action(
        ActionRequest(
            device_id="device-1",
            action_type=ActionType.TAP_OCR,
            params={
                "texts": [_HVITSERK],
                "optional": False,
                "wait_timeout_seconds": 0.1,
                "unstable_retry_texts": [_UNSTABLE],
                "poll_interval_seconds": 0.01,
            },
            step_name="test_phase1_hit",
        )
    )

    assert ok is True
    ctrl.tap.assert_called_once_with("device-1", 120, 400)


@pytest.mark.asyncio
async def test_tap_ocr_unstable_retry_taps_unstable_then_hvitserk() -> None:
    clear_cancelled("device-1")
    seen_after_unstable = False

    async def find_side_effect(
        _device_id: str, texts: list[str], **_kw: object
    ) -> list[dict[str, object]]:
        if any("Hvitserk" in t for t in texts):
            if seen_after_unstable:
                return [{"text": _HVITSERK, "x": 120, "y": 400, "confidence": 0.9}]
            return []
        joined = " ".join(texts)
        if "unstable" in joined.lower() or "Tap to retry" in joined:
            return [{"text": _UNSTABLE, "x": 80, "y": 300, "confidence": 0.88}]
        return []

    async def tap_side_effect(_device_id: str, x: int, y: int) -> bool:
        nonlocal seen_after_unstable
        if x == 80 and y == 300:
            seen_after_unstable = True
        return True

    ctrl = MagicMock()
    ctrl.find_text_on_device = AsyncMock(side_effect=find_side_effect)
    ctrl.tap = AsyncMock(side_effect=tap_side_effect)

    device_manager = MagicMock()
    device_manager.get_device.return_value = MagicMock(screen_width=406, screen_height=720)

    engine = ActionEngine(
        config=MagicMock(),
        controller=ctrl,
        device_manager=device_manager,
        db=MagicMock(),
    )

    ok = await engine._run_action(
        ActionRequest(
            device_id="device-1",
            action_type=ActionType.TAP_OCR,
            params={
                "texts": [_HVITSERK],
                "optional": False,
                "wait_timeout_seconds": 0.3,
                "unstable_retry_texts": [_UNSTABLE],
                "unstable_retry_cooldown_seconds": 0.05,
                "poll_interval_seconds": 0.02,
            },
            step_name="test_unstable_then_hvitserk",
        )
    )

    assert ok is True
    assert ctrl.tap.call_count == 2
    assert ctrl.tap.call_args_list[0].args == ("device-1", 80, 300)
    assert ctrl.tap.call_args_list[1].args == ("device-1", 120, 400)


@pytest.mark.asyncio
async def test_tap_ocr_unstable_retry_waits_through_loading() -> None:
    """Neither Hvitserk nor unstable visible for a few polls, then Hvitserk appears."""
    clear_cancelled("device-1")
    polls = {"n": 0}

    async def find_side_effect(
        _device_id: str, texts: list[str], **_kw: object
    ) -> list[dict[str, object]]:
        if any("Hvitserk" in t for t in texts):
            polls["n"] += 1
            if polls["n"] >= 3:
                return [{"text": _HVITSERK, "x": 120, "y": 400, "confidence": 0.9}]
            return []
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

    ok = await engine._run_action(
        ActionRequest(
            device_id="device-1",
            action_type=ActionType.TAP_OCR,
            params={
                "texts": [_HVITSERK],
                "optional": False,
                "wait_timeout_seconds": 0.2,
                "unstable_retry_texts": [_UNSTABLE],
                "poll_interval_seconds": 0.02,
            },
            step_name="test_loading_then_hvitserk",
        )
    )

    assert ok is True
    assert polls["n"] >= 3
    ctrl.tap.assert_called_once_with("device-1", 120, 400)


@pytest.mark.asyncio
async def test_tap_ocr_unstable_retry_extends_deadline_after_late_unstable() -> None:
    """Unstable prompt near end of initial window — extension allows Hvitserk to appear."""
    clear_cancelled("device-1")
    polls = {"hvitserk": 0, "unstable": 0}

    async def find_side_effect(
        _device_id: str, texts: list[str], **_kw: object
    ) -> list[dict[str, object]]:
        if any("Hvitserk" in t for t in texts):
            polls["hvitserk"] += 1
            if polls["hvitserk"] >= 4:
                return [{"text": _HVITSERK, "x": 120, "y": 400, "confidence": 0.9}]
            return []
        joined = " ".join(texts)
        if "unstable" in joined.lower() or "Tap to retry" in joined:
            polls["unstable"] += 1
            if polls["unstable"] >= 2:
                return [{"text": _UNSTABLE, "x": 80, "y": 300, "confidence": 0.88}]
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

    ok = await engine._run_action(
        ActionRequest(
            device_id="device-1",
            action_type=ActionType.TAP_OCR,
            params={
                "texts": [_HVITSERK],
                "optional": False,
                "wait_timeout_seconds": 0.12,
                "after_retry_wait_seconds": 0.15,
                "max_wait_timeout_seconds": 0.4,
                "unstable_retry_texts": [_UNSTABLE],
                "unstable_retry_cooldown_seconds": 0.01,
                "poll_interval_seconds": 0.02,
            },
            step_name="test_late_unstable_extension",
        )
    )

    assert ok is True
    assert polls["unstable"] >= 2
    assert ctrl.tap.call_count == 2
