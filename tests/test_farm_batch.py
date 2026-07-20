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
async def test_start_skips_excluded_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    from imouse_farm.workflows import farm_batch as farm_batch_mod

    monkeypatch.setattr(farm_batch_mod, "get_batch_size", lambda: 1)
    devices = [
        SimpleNamespace(device_id="phone-11", user_name="11"),
        SimpleNamespace(device_id="phone-12", user_name="12"),
        SimpleNamespace(device_id="phone-13", user_name="13"),
    ]
    runner = FarmBatchRunner(
        BatchConfig(batch_size=1, excluded_slots=[12]),
        _APP,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        auto_generate_captions=False,
    )
    runner._distribute_supplied_if_needed = MagicMock()  # type: ignore[method-assign]
    runner._run_batches = AsyncMock()  # type: ignore[method-assign]

    assert await runner.start(devices) is True
    # 12 is excluded; only 11 and 13 remain (2 batches at size 1).
    assert runner.get_status()["batch_total"] == 2
    batched = runner._distribute_supplied_if_needed.call_args.args[0]
    assert [d.user_name for d in batched] == ["11", "13"]


@pytest.mark.asyncio
async def test_start_returns_false_when_all_slots_excluded() -> None:
    devices = [SimpleNamespace(device_id="phone-12", user_name="12")]
    runner = FarmBatchRunner(
        BatchConfig(excluded_slots=[12]),
        _APP,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        auto_generate_captions=False,
    )
    assert await runner.start(devices) is False
    assert "excluded" in runner.get_status()["message"].lower()


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
    dm.get_device = MagicMock(
        return_value=SimpleNamespace(device_id="phone-1", user_name="1")
    )
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
async def test_pipeline_paused_unblocks_batch_and_stops_pipeline() -> None:
    dm = MagicMock()
    dm.disconnect_airplay = AsyncMock(return_value=True)
    dm.get_device = MagicMock(
        return_value=SimpleNamespace(device_id="phone-1", user_name="1")
    )
    pipeline = MagicMock()
    pipeline.stop = AsyncMock(return_value=True)
    db = MagicMock()
    db.log_activity = AsyncMock()
    runner = FarmBatchRunner(
        BatchConfig(disconnect_on_complete=True),
        _APP,
        dm,
        pipeline,
        db,
        auto_generate_captions=False,
    )
    done = asyncio.Event()
    runner._batch_done_events = {"phone-1": done}
    runner._status = {"completed": [], "failed": []}

    await runner._on_pipeline_event("pipeline_paused", {"device_id": "phone-1"})

    assert done.is_set()
    assert runner._batch_done_events == {}
    assert runner._status["failed"] == [
        {
            "slot": "1",
            "device_id": "phone-1",
            "event": "pipeline_paused",
            "reason": "paused",
        }
    ]
    dm.disconnect_airplay.assert_not_awaited()
    pipeline.stop.assert_awaited_once_with("phone-1")
    db.log_activity.assert_awaited_once()


@pytest.mark.asyncio
async def test_pipeline_completed_disconnects_when_configured() -> None:
    dm = MagicMock()
    dm.disconnect_airplay = AsyncMock(return_value=True)
    dm.get_device = MagicMock(
        return_value=SimpleNamespace(device_id="phone-1", user_name="1")
    )
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
async def test_wait_done_does_not_force_completed_on_timeout() -> None:
    runner = FarmBatchRunner(
        BatchConfig(batch_device_timeout_seconds=7200),
        _APP,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        auto_generate_captions=False,
    )

    async def slow_batch() -> None:
        runner._status["status"] = "running"
        try:
            await asyncio.sleep(60)
        finally:
            runner._status["status"] = "completed"

    runner._task = asyncio.create_task(slow_batch())
    runner._status["status"] = "running"
    assert runner.is_running()

    assert await runner.wait_done(timeout=0.01) is False
    assert runner.is_running()
    assert runner._status["status"] == "running"

    runner._task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runner._task


@pytest.mark.asyncio
async def test_wait_until_idle_blocks_until_task_finishes() -> None:
    runner = FarmBatchRunner(
        BatchConfig(),
        _APP,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        auto_generate_captions=False,
    )
    done = asyncio.Event()

    async def batch() -> None:
        runner._status["status"] = "running"
        await asyncio.sleep(0.05)
        runner._status["status"] = "completed"
        done.set()

    runner._task = asyncio.create_task(batch())
    assert await runner.wait_done(timeout=0.01) is False
    await runner.wait_until_idle()
    assert done.is_set()
    assert runner._status["status"] == "completed"


@pytest.mark.asyncio
async def test_start_queues_one_phone_per_step(monkeypatch: pytest.MonkeyPatch) -> None:
    from imouse_farm.workflows import farm_batch as farm_batch_mod

    monkeypatch.setattr(farm_batch_mod, "get_batch_size", lambda: 1)
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
    assert runner.get_status()["batch_size"] == 1
    assert runner.is_running()


@pytest.mark.asyncio
async def test_flawed_timeout_slot_restarts_before_cast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    device = SimpleNamespace(device_id="phone-7", user_name="7")
    dm = MagicMock()
    dm.disconnect_airplay = AsyncMock(return_value=True)
    dm.controller.restart_device = AsyncMock(return_value=True)
    db = MagicMock()
    db.log_activity = AsyncMock()
    runner = FarmBatchRunner(
        BatchConfig(flawed_timeout_slots=[2, 7, 9, 16, 18, 20]),
        AppConfig(),
        dm,
        MagicMock(),
        db,
        auto_generate_captions=False,
    )
    runner._ensure_cast = AsyncMock(return_value=True)  # type: ignore[method-assign]

    result = await runner._connect_batch_device(device, batch_index=1)

    assert result is device
    dm.disconnect_airplay.assert_not_awaited()
    dm.controller.restart_device.assert_awaited_once_with("phone-7")
    runner._ensure_cast.assert_awaited_once_with("phone-7")
    messages = [c.args[2] for c in db.log_activity.await_args_list]
    assert any("flawed-timeout preflight" in m for m in messages)


@pytest.mark.asyncio
async def test_non_flawed_slot_skips_restart_preflight() -> None:
    device = SimpleNamespace(device_id="phone-3", user_name="3")
    dm = MagicMock()
    dm.disconnect_airplay = AsyncMock(return_value=True)
    dm.controller.restart_device = AsyncMock(return_value=True)
    runner = FarmBatchRunner(
        BatchConfig(flawed_timeout_slots=[2, 7, 9, 16, 18, 20]),
        AppConfig(),
        dm,
        MagicMock(),
        MagicMock(log_activity=AsyncMock()),
        auto_generate_captions=False,
    )
    runner._ensure_cast = AsyncMock(return_value=True)  # type: ignore[method-assign]

    result = await runner._connect_batch_device(device, batch_index=1)

    assert result is device
    dm.controller.restart_device.assert_not_awaited()
    runner._ensure_cast.assert_awaited_once_with("phone-3")
