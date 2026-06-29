"""Tests for farm batch runner cast hygiene."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import asyncio

import pytest

from imouse_farm.config.models import AppConfig, BatchConfig
from imouse_farm.workflows.farm_batch import FarmBatchRunner

_APP = AppConfig()


@pytest.mark.asyncio
async def test_disconnect_unselected_casts_drops_extra_online_phones() -> None:
    selected = SimpleNamespace(device_id="phone-1", user_name="1")
    extra = SimpleNamespace(device_id="phone-9", user_name="9", is_online=True)
    offline = SimpleNamespace(device_id="phone-2", user_name="2", is_online=False)

    dm = MagicMock()
    dm.devices = {
        selected.device_id: SimpleNamespace(**selected.__dict__, is_online=True),
        extra.device_id: extra,
        offline.device_id: offline,
    }
    dm.refresh_devices = AsyncMock()
    dm.disconnect_airplay = AsyncMock(return_value=True)

    db = MagicMock()
    db.log_activity = AsyncMock()

    runner = FarmBatchRunner(
        BatchConfig(),
        _APP,
        dm,
        MagicMock(),
        db,
        auto_generate_captions=False,
    )

    await runner._disconnect_unselected_casts({selected.device_id})

    dm.refresh_devices.assert_awaited_once()
    dm.disconnect_airplay.assert_awaited_once_with(extra.device_id)
    db.log_activity.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_does_not_disconnect_airplay() -> None:
    dm = MagicMock()
    dm.disconnect_airplay = AsyncMock(return_value=True)
    pipeline = MagicMock()
    pipeline.stop = AsyncMock()
    runner = FarmBatchRunner(
        BatchConfig(disconnect_on_complete=True),
        _APP,
        dm,
        pipeline,
        MagicMock(),
        auto_generate_captions=False,
    )
    runner._batch_done_events = {"phone-1": asyncio.Event()}
    runner._task = None

    await runner.stop()

    pipeline.stop.assert_awaited_once_with("phone-1")
    dm.disconnect_airplay.assert_not_awaited()


@pytest.mark.asyncio
async def test_pipeline_stopped_does_not_disconnect_airplay() -> None:
    dm = MagicMock()
    dm.disconnect_airplay = AsyncMock(return_value=True)
    dm.get_device = MagicMock(return_value=SimpleNamespace(user_name="1"))
    runner = FarmBatchRunner(
        BatchConfig(disconnect_on_complete=True),
        _APP,
        dm,
        MagicMock(),
        MagicMock(),
        auto_generate_captions=False,
    )
    runner._batch_done_events = {"phone-1": asyncio.Event()}
    runner._status = {"completed": [], "failed": []}

    await runner._on_pipeline_event(
        "pipeline_stopped",
        {"device_id": "phone-1", "message": "stopped"},
    )

    dm.disconnect_airplay.assert_not_awaited()
    assert runner._batch_done_events == {}


@pytest.mark.asyncio
async def test_pipeline_completed_disconnects_when_configured() -> None:
    dm = MagicMock()
    dm.disconnect_airplay = AsyncMock(return_value=True)
    dm.get_device = MagicMock(return_value=SimpleNamespace(user_name="1"))
    runner = FarmBatchRunner(
        BatchConfig(disconnect_on_complete=True),
        _APP,
        dm,
        MagicMock(),
        MagicMock(),
        auto_generate_captions=False,
    )
    runner._batch_done_events = {"phone-1": asyncio.Event()}
    runner._status = {"completed": [], "failed": []}

    await runner._on_pipeline_event(
        "pipeline_completed",
        {"device_id": "phone-1"},
    )

    dm.disconnect_airplay.assert_awaited_once_with("phone-1")


@pytest.mark.asyncio
async def test_start_queues_one_phone_per_step() -> None:
    devices = [
        SimpleNamespace(device_id=f"phone-{i}", user_name=str(i))
        for i in (3, 7, 12)
    ]
    runner = FarmBatchRunner(
        BatchConfig(batch_size=1),
        _APP,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        auto_generate_captions=False,
    )
    runner._run_batches = AsyncMock()  # type: ignore[method-assign]
    assert await runner.start(devices) is True
    assert runner.get_status()["batch_total"] == 3
    assert runner.is_running()
