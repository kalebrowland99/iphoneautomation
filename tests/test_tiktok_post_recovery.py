"""Tests for tiktok_post failure recovery (restart + resume from plus)."""

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
async def test_recovery_restarts_and_resumes_from_plus() -> None:
    runner = _tiktok_post_runner()
    runner._running = True
    runner._device_manager.is_workflow_paused = AsyncMock(return_value=False)
    runner._log_activity = AsyncMock()
    runner._restart_tiktok = AsyncMock()
    runner._execute_step = AsyncMock()

    fail_step = runner._workflow.steps[1]
    recovered = await runner._try_recover_tiktok_post(fail_step, RuntimeError("tap failed"))

    assert recovered is True
    assert runner._iteration_completed_by_recovery is True
    assert runner._tiktok_post_failure_recoveries == 1
    runner._restart_tiktok.assert_awaited_once()
    assert runner._execute_step.await_count == 3


@pytest.mark.asyncio
async def test_recovery_not_used_for_other_workflows() -> None:
    runner = _tiktok_post_runner()
    runner._workflow = WorkflowConfig(name="tiktok_end", steps=[])
    step = WorkflowStepConfig(type="execute_action", name="kill_apps", on_failure="pause")

    recovered = await runner._try_recover_tiktok_post(step, RuntimeError("boom"))

    assert recovered is False
    assert runner._tiktok_post_failure_recoveries == 0


@pytest.mark.asyncio
async def test_recovery_exhausted_returns_false() -> None:
    runner = _tiktok_post_runner()
    runner._tiktok_post_failure_recoveries = 2
    runner._log_activity = AsyncMock()
    step = runner._workflow.steps[1]

    recovered = await runner._try_recover_tiktok_post(step, RuntimeError("still broken"))

    assert recovered is False


@pytest.mark.asyncio
async def test_execute_step_uses_recovery_before_pause() -> None:
    runner = _tiktok_post_runner()
    runner._running = True
    runner._device_manager.is_workflow_paused = AsyncMock(return_value=False)
    runner._log_activity = AsyncMock()
    runner._try_dismiss_popups = AsyncMock()
    runner._try_recover_tiktok_post = AsyncMock(return_value=True)
    runner._handle_failure = AsyncMock()
    runner._execute_step_body = AsyncMock(side_effect=RuntimeError("fail"))

    step = runner._workflow.steps[1]
    await runner._execute_step(step)

    runner._try_recover_tiktok_post.assert_awaited_once()
    runner._handle_failure.assert_not_awaited()


def test_white_background_skipped_on_post_2_without_restart() -> None:
    runner = _tiktok_post_runner()
    runner._variables["post_index"] = 2
    step = WorkflowStepConfig(
        type="execute_action",
        name="tap_white_background",
        when_post_index=1,
    )
    reason = runner._step_skip_reason(step)
    assert reason is not None
    assert "white background" in reason


def test_white_background_runs_on_post_2_after_restart() -> None:
    runner = _tiktok_post_runner()
    runner._variables["post_index"] = 2
    runner._pending_white_background_after_restart = True
    step = WorkflowStepConfig(
        type="execute_action",
        name="tap_white_background",
        when_post_index=1,
    )
    assert runner._step_skip_reason(step) is None


def test_white_background_runs_on_post_1() -> None:
    runner = _tiktok_post_runner()
    runner._variables["post_index"] = 1
    step = WorkflowStepConfig(
        type="execute_action",
        name="tap_white_background",
        when_post_index=1,
    )
    assert runner._step_skip_reason(step) is None
