"""Tests for Shadowrocket VPN URL shortcut helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from imouse_farm.actions.vpn_shadowrocket import (
    exec_vpn_shortcut_url,
    vpn_shortcut_url,
)
from imouse_farm.config.models import AppConfig, VpnConfig


def test_vpn_shortcut_url_defaults() -> None:
    cfg = AppConfig()
    assert vpn_shortcut_url(cfg, "on") == "shadowrocket://connect"
    assert vpn_shortcut_url(cfg, "off") == "shadowrocket://disconnect"
    assert vpn_shortcut_url(cfg, "toggle") == "shadowrocket://toggle"
    assert vpn_shortcut_url(cfg, "open") == "shadowrocket://"


def test_vpn_shortcut_url_custom() -> None:
    cfg = AppConfig(
        vpn=VpnConfig(
            shortcut_url_on="shortcuts://run-shortcut?name=VPNOn",
            shortcut_url_off="shortcuts://run-shortcut?name=VPNOff",
            shortcut_url_toggle="shortcuts://run-shortcut?name=VPNToggle",
        )
    )
    assert vpn_shortcut_url(cfg, "on") == "shortcuts://run-shortcut?name=VPNOn"
    assert vpn_shortcut_url(cfg, "off") == "shortcuts://run-shortcut?name=VPNOff"
    assert vpn_shortcut_url(cfg, "toggle") == "shortcuts://run-shortcut?name=VPNToggle"


@pytest.mark.asyncio
async def test_exec_vpn_shortcut_url_opens_and_homes() -> None:
    controller = AsyncMock()
    controller.launch_app_with_error = AsyncMock(return_value=(True, ""))
    controller.press_home = AsyncMock(return_value=True)
    controller.find_text_on_device = AsyncMock(return_value=[])

    await exec_vpn_shortcut_url(
        controller,
        "phone-1",
        "shadowrocket://connect",
        settle_seconds=0.1,
    )

    controller.launch_app_with_error.assert_awaited()
    controller.press_home.assert_awaited_once_with("phone-1")


@pytest.mark.asyncio
async def test_exec_vpn_shortcut_url_taps_allow_and_retries() -> None:
    controller = AsyncMock()
    controller.launch_app_with_error = AsyncMock(side_effect=[(False, "timeout"), (True, "")])
    controller.press_home = AsyncMock(return_value=True)
    allow_seen = {"done": False}

    async def _find_text(_device_id: str, texts: list[str], **kwargs: object) -> list[dict]:
        if "Allow" in texts and not allow_seen["done"]:
            allow_seen["done"] = True
            return [{"text": "Allow", "x": 280, "y": 520, "confidence": 0.9}]
        return []

    controller.find_text_on_device = AsyncMock(side_effect=_find_text)
    controller.tap = AsyncMock(return_value=True)

    await exec_vpn_shortcut_url(
        controller,
        "phone-1",
        "shadowrocket://connect",
        settle_seconds=0.1,
    )

    assert controller.launch_app_with_error.await_count == 2
    controller.tap.assert_awaited_once_with("phone-1", 280, 520)


@pytest.mark.asyncio
async def test_exec_vpn_shortcut_url_includes_sdk_error() -> None:
    controller = AsyncMock()
    controller.launch_app_with_error = AsyncMock(return_value=(False, "device offline"))
    controller.find_text_on_device = AsyncMock(return_value=[])

    with pytest.raises(RuntimeError, match="device offline"):
        await exec_vpn_shortcut_url(
            controller,
            "phone-1",
            "shadowrocket://connect",
            settle_seconds=0.1,
        )


@pytest.mark.asyncio
async def test_exec_vpn_shortcut_url_rejects_empty() -> None:
    controller = AsyncMock()
    with pytest.raises(ValueError, match="not configured"):
        await exec_vpn_shortcut_url(controller, "phone-1", "")
