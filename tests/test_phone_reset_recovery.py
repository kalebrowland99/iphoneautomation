"""Tests: phone reboot recovery has been removed from workflow paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.config.models import AppConfig, WorkflowConfig, WorkflowStepConfig
from imouse_farm.workflows.engine import WorkflowRunner


def _tiktok_post_runner() -> WorkflowRunner:
    workflow = WorkflowConfig(
        name="tiktok_post",
        steps=[
            WorkflowStepConfig(
                type="wait_for_detection",
                name="wait_for_plus",
                action={"max_failure_recoveries": 2},
            ),
            WorkflowStepConfig(type="execute_action", name="tap_plus", on_failure="pause"),
            WorkflowStepConfig(type="wait", name="after_plus"),
        ],
    )
    return WorkflowRunner(
        workflow=workflow,
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


@pytest.mark.asyncio
async def test_recovery_does_not_reboot_phone_when_tiktok_restart_fails() -> None:
    runner = _tiktok_post_runner()
    runner._running = True
    runner._device_manager.is_workflow_paused = AsyncMock(return_value=False)
    runner._log_activity = AsyncMock()
    runner._restart_tiktok = AsyncMock(side_effect=RuntimeError("no tiktok icon"))
    runner._resume_tiktok_post_from_plus = AsyncMock(return_value=True)
    assert not hasattr(runner, "_reset_phone_recast_and_open_tiktok")

    fail_step = runner._workflow.steps[1]
    recovered = await runner._try_recover_tiktok_post(fail_step, RuntimeError("tap failed"))

    assert recovered is False
    runner._resume_tiktok_post_from_plus.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_does_not_reboot_when_tiktok_restart_does_not_recover() -> None:
    runner = _tiktok_post_runner()
    runner._running = True
    runner._device_manager.is_workflow_paused = AsyncMock(return_value=False)
    runner._log_activity = AsyncMock()
    runner._restart_tiktok = AsyncMock()
    runner._resume_tiktok_post_from_plus = AsyncMock(return_value=False)
    assert not hasattr(runner, "_reset_phone_recast_and_open_tiktok")

    fail_step = runner._workflow.steps[1]
    recovered = await runner._try_recover_tiktok_post(fail_step, RuntimeError("tap failed"))

    assert recovered is False
    runner._resume_tiktok_post_from_plus.assert_awaited_once()
