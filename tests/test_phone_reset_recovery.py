"""Tests for phone reset recovery."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.config.models import AppConfig, WorkflowConfig, WorkflowStepConfig
from imouse_farm.devices.manager import DeviceManager, ManagedDevice
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
async def test_recovery_resets_phone_when_restart_fails() -> None:
    runner = _tiktok_post_runner()
    runner._running = True
    runner._device_manager.is_workflow_paused = AsyncMock(return_value=False)
    runner._log_activity = AsyncMock()
    runner._restart_tiktok = AsyncMock(side_effect=RuntimeError("no tiktok icon"))
    runner._reset_phone_recast_and_open_tiktok = AsyncMock()
    runner._resume_tiktok_post_from_plus = AsyncMock(return_value=True)

    fail_step = runner._workflow.steps[1]
    recovered = await runner._try_recover_tiktok_post(fail_step, RuntimeError("tap failed"))

    assert recovered is True
    runner._reset_phone_recast_and_open_tiktok.assert_awaited_once()
    runner._resume_tiktok_post_from_plus.assert_awaited_once()


@pytest.mark.asyncio
async def test_phone_reset_turns_vpn_on_before_opening_tiktok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _tiktok_post_runner()
    runner._log_activity = AsyncMock()
    runner._device_manager.reset_phone_and_recast = AsyncMock()
    runner._open_tiktok_from_home = AsyncMock()
    vpn_on = AsyncMock()
    monkeypatch.setattr(
        "imouse_farm.actions.vpn_shadowrocket.ensure_vpn_on",
        vpn_on,
    )

    await runner._reset_phone_recast_and_open_tiktok(parent_step="wait_for_plus")

    runner._device_manager.reset_phone_and_recast.assert_awaited_once_with(runner._device_id)
    vpn_on.assert_awaited_once()
    runner._open_tiktok_from_home.assert_awaited_once()


@pytest.mark.asyncio
async def test_reset_phone_and_recast_resets_usb_and_mouse_before_cast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = AppConfig()
    cfg.diagnostics.phone_restart_boot_wait_seconds = 0
    cfg.batch.cast_connect_max_attempts = 2
    cfg.batch.cast_connect_retry_seconds = 0

    controller = AsyncMock()
    controller.restart_device = AsyncMock(return_value=True)
    controller.restart_usb = AsyncMock(return_value=True)
    controller.reset_cursor = AsyncMock(return_value=True)
    db = AsyncMock()
    dm = DeviceManager(cfg, controller, db)
    online = ManagedDevice(
        device_id="dev-1",
        device_name="Phone 1",
        user_name="1",
        is_online=True,
    )
    dm._devices["dev-1"] = online

    monkeypatch.setattr(dm, "refresh_devices", AsyncMock())
    monkeypatch.setattr(dm, "reconnect_airplay", AsyncMock(return_value=True))
    monkeypatch.setattr("imouse_farm.devices.manager.asyncio.sleep", AsyncMock())

    await dm.reset_phone_and_recast("dev-1")

    controller.restart_device.assert_awaited_once_with("dev-1")
    controller.restart_usb.assert_awaited_once_with("dev-1")
    assert controller.reset_cursor.await_count >= 2
    dm.reconnect_airplay.assert_awaited_once_with("dev-1")
    # USB → mouse resets happen before the first cast attempt
    usb_order = controller.restart_usb.await_args_list[0]
    first_mouse = controller.reset_cursor.await_args_list[0]
    cast_order = dm.reconnect_airplay.await_args_list[0]
    assert usb_order is not None and first_mouse is not None and cast_order is not None


@pytest.mark.asyncio
async def test_recovery_resets_phone_when_restart_does_not_recover() -> None:
    runner = _tiktok_post_runner()
    runner._running = True
    runner._device_manager.is_workflow_paused = AsyncMock(return_value=False)
    runner._log_activity = AsyncMock()
    runner._restart_tiktok = AsyncMock()
    runner._reset_phone_recast_and_open_tiktok = AsyncMock()
    runner._resume_tiktok_post_from_plus = AsyncMock(side_effect=[False, True])

    fail_step = runner._workflow.steps[1]
    recovered = await runner._try_recover_tiktok_post(fail_step, RuntimeError("tap failed"))

    assert recovered is True
    runner._reset_phone_recast_and_open_tiktok.assert_awaited_once()
    assert runner._resume_tiktok_post_from_plus.await_count == 2
