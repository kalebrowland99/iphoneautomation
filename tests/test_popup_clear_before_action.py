"""Tests for popup watcher gating before TikTok workflow actions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.config.models import ActionType, AppConfig, WorkflowConfig, WorkflowStepConfig
from imouse_farm.workflows.engine import WorkflowRunner, step_needs_sync_popup_clear


def _tiktok_runner() -> WorkflowRunner:
    return WorkflowRunner(
        workflow=WorkflowConfig(name="tiktok_post", steps=[]),
        device_id="dev-1",
        config=AppConfig(),
        device_manager=MagicMock(),
        screenshot_service=MagicMock(),
        vision=MagicMock(),
        popup_manager=MagicMock(),
        state_machine=MagicMock(),
        action_engine=MagicMock(),
        db=AsyncMock(),
    )


def test_step_needs_sync_popup_clear_only_for_wait_for_plus() -> None:
    assert step_needs_sync_popup_clear(
        "tiktok_post",
        WorkflowStepConfig(type="wait_for_detection", name="wait_for_plus"),
    ) is True
    assert step_needs_sync_popup_clear(
        "tiktok_post",
        WorkflowStepConfig(type="execute_action", name="tap_plus", action={"type": "tap"}),
    ) is False
    assert step_needs_sync_popup_clear(
        "tiktok_prep",
        WorkflowStepConfig(type="execute_action", name="open_shadowrocket", action={"type": "tap"}),
    ) is False
    assert step_needs_sync_popup_clear(
        "tiktok_account_switch",
        WorkflowStepConfig(type="ensure_tiktok_account", name="ensure_tiktok_account"),
    ) is False


@pytest.mark.asyncio
async def test_ensure_popups_cleared_loops_until_nothing_found() -> None:
    runner = _tiktok_runner()
    runner._permission_watchers = MagicMock()
    runner._try_dismiss_popups = AsyncMock(side_effect=[True, True, False])

    cleared = await runner._ensure_popups_cleared("tap_plus")

    assert cleared == 2
    assert runner._try_dismiss_popups.await_count == 3


@pytest.mark.asyncio
async def test_execute_step_skips_popup_clear_for_post_taps() -> None:
    runner = _tiktok_runner()
    runner._workflow = WorkflowConfig(name="tiktok_post", steps=[])
    runner._ensure_popups_cleared = AsyncMock(return_value=0)
    runner._step_action = AsyncMock()
    runner._db.log_activity = AsyncMock()

    step = WorkflowStepConfig(
        type="execute_action",
        name="tap_plus",
        action={"type": "tap_detection", "detection": "plus"},
    )
    await runner._execute_step(step)

    runner._ensure_popups_cleared.assert_not_awaited()
    runner._step_action.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_step_clears_popups_before_wait_for_plus() -> None:
    runner = _tiktok_runner()
    runner._workflow = WorkflowConfig(name="tiktok_post", steps=[])
    runner._ensure_popups_cleared = AsyncMock(return_value=0)
    runner._step_wait_for_detection = AsyncMock()
    runner._db.log_activity = AsyncMock()

    step = WorkflowStepConfig(
        type="wait_for_detection",
        name="wait_for_plus",
        templates=["plus"],
        when_detection="plus",
    )
    await runner._execute_step(step)

    runner._ensure_popups_cleared.assert_awaited_once_with("wait_for_plus")
    runner._step_wait_for_detection.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_direct_does_not_clear_popups() -> None:
    runner = _tiktok_runner()
    runner._ensure_popups_cleared = AsyncMock(return_value=0)
    runner._actions.execute_direct = AsyncMock(return_value=True)

    ok = await runner._execute_direct(
        ActionType.TAP_DETECTION,
        {"detection": "plus"},
        step_name="tap_plus",
    )

    assert ok is True
    runner._ensure_popups_cleared.assert_not_awaited()
    runner._actions.execute_direct.assert_awaited_once()
