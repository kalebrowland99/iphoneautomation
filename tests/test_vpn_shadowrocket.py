"""Tests for fixed-coord Shadowrocket VPN helpers."""

from imouse_farm.actions.vpn_shadowrocket import (
    SHADOWROCKET_ICON_X,
    SHADOWROCKET_ICON_Y,
    SHADOWROCKET_TOGGLE_X,
    SHADOWROCKET_TOGGLE_Y,
    TIKTOK_HOME_ICON_X,
    TIKTOK_HOME_ICON_Y,
)


def test_shadowrocket_icon_coordinates() -> None:
    assert SHADOWROCKET_ICON_X == 373
    assert SHADOWROCKET_ICON_Y == 1003


def test_shadowrocket_toggle_coordinates() -> None:
    assert SHADOWROCKET_TOGGLE_X == 515
    assert SHADOWROCKET_TOGGLE_Y == 171


def test_tiktok_home_icon_coordinates() -> None:
    assert TIKTOK_HOME_ICON_X == 507
    assert TIKTOK_HOME_ICON_Y == 1011
