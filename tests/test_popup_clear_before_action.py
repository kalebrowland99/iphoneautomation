"""Tests for popup watcher gating before TikTok workflow actions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.config.models import ActionType, AppConfig, WorkflowConfig
from imouse_farm.workflows.engine import WorkflowRunner


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


@pytest.mark.asyncio
async def test_ensure_popups_cleared_loops_until_nothing_found() -> None:
    runner = _tiktok_runner()
    runner._permission_watchers = MagicMock()
    runner._try_dismiss_popups = AsyncMock(side_effect=[True, True, False])

    cleared = await runner._ensure_popups_cleared("tap_plus")

    assert cleared == 2
    assert runner._try_dismiss_popups.await_count == 3


@pytest.mark.asyncio
async def test_execute_direct_clears_popups_before_action() -> None:
    runner = _tiktok_runner()
    runner._ensure_popups_cleared = AsyncMock(return_value=0)
    runner._actions.execute_direct = AsyncMock(return_value=True)

    ok = await runner._execute_direct(
        ActionType.TAP_DETECTION,
        {"detection": "plus"},
        step_name="tap_plus",
    )

    assert ok is True
    runner._ensure_popups_cleared.assert_awaited_once_with("tap_plus")
    runner._actions.execute_direct.assert_awaited_once()
