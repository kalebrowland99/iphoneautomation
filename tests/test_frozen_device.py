"""Tests for frozen-device detection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from imouse_farm.config.models import AppConfig, DeviceState
from imouse_farm.devices.manager import DeviceManager, ManagedDevice


@pytest.mark.asyncio
async def test_is_frozen_false_when_workflow_paused() -> None:
    config = AppConfig()
    config.timing.frozen_device_threshold_seconds = 60
    dm = DeviceManager(config, MagicMock(), MagicMock())
    device = ManagedDevice(
        device_id="phone-1",
        device_name="1",
        user_name="1",
        is_online=True,
        workflow_paused=True,
        last_activity_at=datetime.now(timezone.utc) - timedelta(seconds=300),
    )
    dm._devices["phone-1"] = device

    assert await dm.is_frozen("phone-1") is False


@pytest.mark.asyncio
async def test_is_frozen_false_when_error_state() -> None:
    config = AppConfig()
    config.timing.frozen_device_threshold_seconds = 60
    dm = DeviceManager(config, MagicMock(), MagicMock())
    device = ManagedDevice(
        device_id="phone-1",
        device_name="1",
        user_name="1",
        is_online=True,
        current_state=DeviceState.ERROR,
        last_activity_at=datetime.now(timezone.utc) - timedelta(seconds=300),
    )
    dm._devices["phone-1"] = device

    assert await dm.is_frozen("phone-1") is False
