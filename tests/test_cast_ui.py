"""Control Bar UI cast (no airplay/connect API)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.config.models import AppConfig, BatchConfig, CastUiConfig
from imouse_farm.workflows.farm_batch import FarmBatchRunner


def _runner(batch: BatchConfig, dm: MagicMock) -> FarmBatchRunner:
    return FarmBatchRunner(
        batch,
        AppConfig(),
        dm,
        MagicMock(),
        MagicMock(),
        imouse_connect_delay=0,
        auto_generate_captions=False,
    )


def _cast_cfg(**kwargs: object) -> CastUiConfig:
    base = dict(
        enabled=True,
        wake_screen=True,
        wake_settle_seconds=0,
        post_home_settle_seconds=0,
        control_bar_fn_key="ControlBar",
        after_control_bar_seconds=0,
        screen_mirroring_x=159,
        screen_mirroring_y=384,
        after_mirroring_seconds=0,
        target_x=178,
        target_y=316,
        after_target_seconds=0,
        confirm_timeout_seconds=0.01,
        confirm_poll_seconds=0.01,
        home_after_connect_count=3,
        home_after_connect_interval_seconds=0,
    )
    base.update(kwargs)
    return CastUiConfig(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_ensure_cast_control_bar_sequence_then_online() -> None:
    dm = MagicMock()
    dm.controller = MagicMock()
    order: list[str] = []

    async def _unlock(device_id: str) -> bool:
        order.append("unlock")
        return True

    async def _home(device_id: str) -> bool:
        order.append("home")
        return True

    async def _fn(device_id: str, fn_key: str) -> bool:
        order.append(f"fn:{fn_key}")
        return True

    async def _tap(device_id: str, x: int, y: int) -> bool:
        order.append(f"tap:{x},{y}")
        return True

    call_idx = {"n": 0}

    def _get_device(device_id: str) -> SimpleNamespace:
        call_idx["n"] += 1
        # Offline until after UI sequence confirm poll.
        online = call_idx["n"] >= 2
        return SimpleNamespace(device_id=device_id, is_online=online)

    dm.controller.press_unlock = _unlock
    dm.controller.press_home = _home
    dm.controller.send_fn_key = _fn
    dm.controller.tap = _tap
    dm.reconnect_airplay = AsyncMock(return_value=True)
    dm.refresh_devices = AsyncMock()
    dm.get_device = MagicMock(side_effect=_get_device)

    ok = await _runner(
        BatchConfig(cast_connect_max_attempts=1, cast_ui=_cast_cfg()),
        dm,
    )._ensure_cast("dev-1")

    assert ok is True
    assert order == [
        "unlock",
        "home",
        "fn:ControlBar",
        "tap:159,384",
        "tap:178,316",
        "home",
        "home",
        "home",
    ]
    dm.reconnect_airplay.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_cast_skips_when_already_online() -> None:
    online = SimpleNamespace(device_id="dev-1", is_online=True)
    dm = MagicMock()
    dm.controller = MagicMock()
    dm.controller.tap = AsyncMock(return_value=True)
    dm.controller.send_fn_key = AsyncMock(return_value=True)
    dm.controller.press_unlock = AsyncMock(return_value=True)
    dm.controller.press_home = AsyncMock(return_value=True)
    dm.reconnect_airplay = AsyncMock(return_value=True)
    dm.refresh_devices = AsyncMock()
    dm.get_device = MagicMock(return_value=online)

    ok = await _runner(
        BatchConfig(cast_ui=_cast_cfg()),
        dm,
    )._ensure_cast("dev-1")

    assert ok is True
    dm.controller.tap.assert_not_awaited()
    dm.controller.send_fn_key.assert_not_awaited()
    dm.controller.press_home.assert_not_awaited()
    dm.reconnect_airplay.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_cast_fails_when_never_online() -> None:
    offline = SimpleNamespace(device_id="dev-1", is_online=False)
    dm = MagicMock()
    dm.controller = MagicMock()
    dm.controller.press_unlock = AsyncMock(return_value=True)
    dm.controller.press_home = AsyncMock(return_value=True)
    dm.controller.send_fn_key = AsyncMock(return_value=True)
    dm.controller.tap = AsyncMock(return_value=True)
    dm.reconnect_airplay = AsyncMock(return_value=True)
    dm.refresh_devices = AsyncMock()
    dm.get_device = MagicMock(return_value=offline)

    ok = await _runner(
        BatchConfig(cast_connect_max_attempts=1, cast_ui=_cast_cfg()),
        dm,
    )._ensure_cast("dev-1")

    assert ok is False
    dm.reconnect_airplay.assert_not_awaited()
    assert dm.controller.send_fn_key.await_count == 1
    assert dm.controller.tap.await_count == 2
    # Wake home once only — no post-connect homes on failure.
    assert dm.controller.press_home.await_count == 1
