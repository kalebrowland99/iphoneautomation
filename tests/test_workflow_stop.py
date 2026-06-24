"""Tests for workflow stop/clear paused state."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.config.models import DeviceState, WorkflowConfig
from imouse_farm.devices.manager import ManagedDevice
from imouse_farm.workflows.engine import WorkflowEngine


@pytest.mark.asyncio
async def test_stop_device_clears_paused_without_runner() -> None:
    device_id = "14:9D:99:ED:CC:15"
    device = ManagedDevice(
        device_id=device_id,
        workflow_name="tiktok_prep",
        workflow_paused=True,
        current_state=DeviceState.ERROR,
        is_online=True,
    )

    dm = MagicMock()
    dm.get_device.return_value = device
    dm.resume_workflow = AsyncMock()
    dm.set_workflow = AsyncMock()
    dm.set_state = AsyncMock()

    engine = WorkflowEngine(
        config=MagicMock(),
        workflows={"tiktok_prep": WorkflowConfig(name="tiktok_prep")},
        device_manager=dm,
        screenshot_service=MagicMock(),
        vision=MagicMock(),
        popup_manager=MagicMock(),
        state_machine=MagicMock(),
        action_engine=MagicMock(),
        db=MagicMock(),
        permission_watchers=None,
    )

    assert await engine.stop_device(device_id) is True
    dm.resume_workflow.assert_awaited_once_with(device_id)
    dm.set_workflow.assert_awaited_once_with(device_id, "")
    dm.set_state.assert_awaited_once_with(device_id, DeviceState.IDLE, "workflow_stopped")
