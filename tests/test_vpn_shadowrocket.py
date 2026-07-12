"""Tests for VPN Shadowrocket shortcut helpers."""

from imouse_farm.actions.vpn_shadowrocket import (
    SHADOWROCKET_ICON_X,
    SHADOWROCKET_ICON_Y,
    TIKTOK_HOME_ICON_X,
    TIKTOK_HOME_ICON_Y,
)


def test_shadowrocket_icon_coordinates() -> None:
    assert SHADOWROCKET_ICON_X == 376
    assert SHADOWROCKET_ICON_Y == 1013


def test_tiktok_home_icon_coordinates() -> None:
    assert TIKTOK_HOME_ICON_X == 507
    assert TIKTOK_HOME_ICON_Y == 1011
