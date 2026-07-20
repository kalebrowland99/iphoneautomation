"""Tests for fixed-coord Shadowrocket VPN helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from imouse_farm.actions.vpn_shadowrocket import (
    SHADOWROCKET_ICON_X,
    SHADOWROCKET_ICON_Y,
    SHADOWROCKET_TOGGLE_X,
    SHADOWROCKET_TOGGLE_Y,
    _parse_vpn_status,
    ensure_vpn,
    open_shadowrocket,
)
from imouse_farm.config.models import AppConfig, VpnConfig


def test_parse_vpn_status_variants() -> None:
    assert _parse_vpn_status("STATUS: ON") == "on"
    assert _parse_vpn_status("STATUS: OFF") == "off"
    assert _parse_vpn_status("status: on") == "on"


@pytest.mark.asyncio
async def test_open_shadowrocket_taps_home_icon() -> None:
    controller = AsyncMock()
    controller.press_home = AsyncMock(return_value=True)
    controller.tap = AsyncMock(return_value=True)
    controller.find_text_on_device = AsyncMock(return_value=[])
    cfg = AppConfig(vpn=VpnConfig(app_settle_seconds=0.05))

    await open_shadowrocket(controller, cfg, "phone-1")

    controller.press_home.assert_awaited_once_with("phone-1")
    controller.tap.assert_awaited_once_with(
        "phone-1", SHADOWROCKET_ICON_X, SHADOWROCKET_ICON_Y
    )


@pytest.mark.asyncio
async def test_ensure_vpn_taps_fixed_toggle_when_needed() -> None:
    controller = AsyncMock()
    controller.press_home = AsyncMock(return_value=True)
    controller.tap = AsyncMock(return_value=True)
    controller.find_text_on_device = AsyncMock(return_value=[])
    cfg = AppConfig(
        vpn=VpnConfig(
            app_settle_seconds=0.01,
            after_toggle_settle_seconds=0.01,
            confirm_settle_seconds=0.01,
        )
    )

    with patch(
        "imouse_farm.actions.vpn_shadowrocket.vision_read_vpn_status",
        new_callable=AsyncMock,
        side_effect=["off", "on"],
    ):
        await ensure_vpn(controller, cfg, "phone-1", want="on")

    # icon open + toggle
    assert controller.tap.await_count == 2
    controller.tap.assert_any_await("phone-1", SHADOWROCKET_ICON_X, SHADOWROCKET_ICON_Y)
    controller.tap.assert_any_await("phone-1", SHADOWROCKET_TOGGLE_X, SHADOWROCKET_TOGGLE_Y)


@pytest.mark.asyncio
async def test_ensure_vpn_skips_toggle_when_already_desired() -> None:
    controller = AsyncMock()
    controller.press_home = AsyncMock(return_value=True)
    controller.tap = AsyncMock(return_value=True)
    controller.find_text_on_device = AsyncMock(return_value=[])
    cfg = AppConfig(
        vpn=VpnConfig(
            app_settle_seconds=0.01,
            after_toggle_settle_seconds=0.01,
            confirm_settle_seconds=0.01,
        )
    )

    with patch(
        "imouse_farm.actions.vpn_shadowrocket.vision_read_vpn_status",
        new_callable=AsyncMock,
        side_effect=["on", "on"],
    ):
        await ensure_vpn(controller, cfg, "phone-1", want="on")

    # only icon open
    controller.tap.assert_awaited_once_with(
        "phone-1", SHADOWROCKET_ICON_X, SHADOWROCKET_ICON_Y
    )
