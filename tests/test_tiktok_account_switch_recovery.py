"""Tests for tiktok_account_switch failure recovery (reopen + retry)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.config.models import AppConfig, WorkflowConfig, WorkflowStepConfig
from imouse_farm.workflows.engine import WorkflowRunner


def _account_switch_runner() -> WorkflowRunner:
    workflow = WorkflowConfig(
        name="tiktok_account_switch",
        steps=[
            WorkflowStepConfig(
                type="ensure_tiktok_account",
                name="ensure_tiktok_account",
                on_failure="pause",
            ),
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
async def test_account_switch_recovery_reopens_and_retries() -> None:
    runner = _account_switch_runner()
    runner._log_activity = AsyncMock()
    runner._vision_recover = AsyncMock()
    runner._execute_step_body = AsyncMock()

    step = runner._workflow.steps[0]
    result = await runner._try_recover_tiktok_account_switch(
        step,
        RuntimeError("Could not find @user in account dropdown via OCR"),
    )

    assert result is True
    assert runner._tiktok_account_switch_recoveries == 1
    runner._vision_recover.assert_awaited_once()
    runner._execute_step_body.assert_awaited_once_with(step)


@pytest.mark.asyncio
async def test_account_switch_recovery_returns_none_when_retry_fails() -> None:
    runner = _account_switch_runner()
    runner._log_activity = AsyncMock()
    runner._vision_recover = AsyncMock()
    runner._execute_step_body = AsyncMock(
        side_effect=RuntimeError("still missing handle"),
    )

    step = runner._workflow.steps[0]
    result = await runner._try_recover_tiktok_account_switch(step, RuntimeError("first fail"))

    assert result is None
    assert runner._tiktok_account_switch_recoveries == 3
    assert runner._vision_recover.await_count == 3
    assert runner._pending_failure_exc.args[0] == "still missing handle"


@pytest.mark.asyncio
async def test_account_switch_recovery_not_used_for_other_steps() -> None:
    runner = _account_switch_runner()
    step = WorkflowStepConfig(type="execute_action", name="tap_plus", on_failure="pause")

    result = await runner._try_recover_tiktok_account_switch(step, RuntimeError("boom"))

    assert result is False
    assert runner._tiktok_account_switch_recoveries == 0
