"""Tests for iMouseXP kernel recovery during farm batch runs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.config.models import AppConfig, BatchConfig, KernelRecoveryConfig
from imouse_farm.workflows.farm_batch import FarmBatchRunner
from imouse_farm.workflows.imouse_recovery import is_imouse_failure


def test_is_imouse_failure_detects_cast_and_timeout() -> None:
    assert is_imouse_failure("cast_connect_failed") is True
    assert is_imouse_failure("batch_device_timeout") is True
    assert is_imouse_failure("warmup_failed: screenshot capture failed") is True
    assert is_imouse_failure("missing post 1 caption") is False


@pytest.mark.asyncio
async def test_note_imouse_failure_schedules_recovery_at_threshold() -> None:
    runner = FarmBatchRunner(
        BatchConfig(kernel_recovery=KernelRecoveryConfig(failure_threshold=2)),
        AppConfig(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        auto_generate_captions=False,
    )
    runner._note_imouse_failure(3, "cast_connect_failed")
    assert runner._pending_kernel_recovery_batch_index is None
    runner._note_imouse_failure(5, "cast_connect_failed")
    assert runner._pending_kernel_recovery_batch_index == 3


@pytest.mark.asyncio
async def test_kernel_recovery_restarts_and_resumes_first_failed_phone() -> None:
    devices = [
        [SimpleNamespace(device_id="phone-2", user_name="2")],
        [SimpleNamespace(device_id="phone-3", user_name="3")],
        [SimpleNamespace(device_id="phone-4", user_name="4")],
    ]
    dm = MagicMock()
    dm.controller = MagicMock()
    dm.controller.restart_imouse_kernel = AsyncMock(return_value=True)
    dm.controller.reconnect = AsyncMock()
    dm.reconnect_airplay = AsyncMock(return_value=True)
    dm.refresh_devices = AsyncMock()
    dm.disconnect_airplay = AsyncMock(return_value=True)

    db = MagicMock()
    db.log_activity = AsyncMock()

    runner = FarmBatchRunner(
        BatchConfig(
            kernel_recovery=KernelRecoveryConfig(
                failure_threshold=2,
                kernel_restart_wait_seconds=0.01,
            )
        ),
        AppConfig(),
        dm,
        MagicMock(),
        db,
        imouse_connect_delay=0.01,
        auto_generate_captions=False,
    )
    runner._finish_device_session = AsyncMock()  # type: ignore[method-assign]
    runner._status = {"failed": [{"slot": "2"}, {"slot": "3"}], "completed": []}
    runner._pending_kernel_recovery_batch_index = 1
    runner._kernel_recovery_count = 0

    resume = await runner._check_kernel_recovery(devices, {"phone-2", "phone-3", "phone-4"})

    assert resume == 1
    dm.controller.restart_imouse_kernel.assert_awaited_once()
    dm.controller.reconnect.assert_awaited_once()
    assert dm.reconnect_airplay.await_count == 3
    assert runner._status["failed"] == []
    assert runner._kernel_recovery_count == 1
