"""Periodic AirPlay/mDNS refresh while DeviceManager is running."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from imouse_farm.config.models import AppConfig, DeviceState, IMouseConfig
from imouse_farm.devices.manager import DeviceManager, ManagedDevice


@pytest.mark.asyncio
async def test_mdns_refresh_loop_calls_regmdns_when_idle() -> None:
    config = AppConfig(
        imouse=IMouseConfig(
            mdns_refresh_enabled=True,
            mdns_refresh_interval_seconds=5.0,
        )
    )
    controller = MagicMock()
    controller.is_connected = True
    controller.refresh_mdns = AsyncMock(return_value=True)
    dm = DeviceManager(config, controller, MagicMock())
    dm._running = True
    dm._devices["dev-1"] = ManagedDevice(
        device_id="dev-1",
        is_online=False,
        current_state=DeviceState.DISCONNECTED,
    )

    real_sleep = asyncio.sleep

    async def _instant_sleep(_delay: float) -> None:
        await real_sleep(0.01)

    with patch.object(asyncio, "sleep", side_effect=_instant_sleep):
        task = asyncio.create_task(dm._mdns_refresh_loop())
        await real_sleep(0.15)
        dm._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert controller.refresh_mdns.await_count >= 1


@pytest.mark.asyncio
async def test_mdns_refresh_loop_skips_when_casting() -> None:
    config = AppConfig(imouse=IMouseConfig(mdns_refresh_enabled=True))
    controller = MagicMock()
    controller.is_connected = True
    controller.refresh_mdns = AsyncMock(return_value=True)
    dm = DeviceManager(config, controller, MagicMock())
    dm._running = True
    dm._devices["dev-1"] = ManagedDevice(
        device_id="dev-1",
        is_online=True,
        current_state=DeviceState.IDLE,
    )

    real_sleep = asyncio.sleep

    async def _instant_sleep(_delay: float) -> None:
        await real_sleep(0.01)

    with patch.object(asyncio, "sleep", side_effect=_instant_sleep):
        task = asyncio.create_task(dm._mdns_refresh_loop())
        await real_sleep(0.12)
        dm._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert controller.refresh_mdns.await_count == 0


@pytest.mark.asyncio
async def test_mdns_refresh_loop_skips_when_disconnected() -> None:
    config = AppConfig(imouse=IMouseConfig(mdns_refresh_enabled=True))
    controller = MagicMock()
    controller.is_connected = False
    controller.refresh_mdns = AsyncMock(return_value=True)
    dm = DeviceManager(config, controller, MagicMock())
    dm._running = True

    real_sleep = asyncio.sleep

    async def _instant_sleep(_delay: float) -> None:
        await real_sleep(0.01)

    with patch.object(asyncio, "sleep", side_effect=_instant_sleep):
        task = asyncio.create_task(dm._mdns_refresh_loop())
        await real_sleep(0.08)
        dm._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert controller.refresh_mdns.await_count == 0


def test_mdns_refresh_config_defaults() -> None:
    cfg = IMouseConfig()
    assert cfg.mdns_refresh_enabled is True
    assert cfg.mdns_refresh_interval_seconds == 30.0


def test_any_device_casting() -> None:
    dm = DeviceManager(AppConfig(), MagicMock(), MagicMock())
    assert dm._any_device_casting() is False
    dm._devices["a"] = ManagedDevice(device_id="a", is_online=False)
    assert dm._any_device_casting() is False
    dm._devices["b"] = ManagedDevice(device_id="b", is_online=True)
    assert dm._any_device_casting() is True
