"""Tests for VPN Shadowrocket helpers."""

from imouse_farm.actions.vpn_shadowrocket import (
    SHADOWROCKET_ICON_X,
    SHADOWROCKET_ICON_Y,
    VPN_TOGGLE_X,
    VPN_TOGGLE_Y,
)


def test_shadowrocket_icon_coordinates() -> None:
    assert SHADOWROCKET_ICON_X == 376
    assert SHADOWROCKET_ICON_Y == 1013


def test_vpn_toggle_coordinates() -> None:
    assert VPN_TOGGLE_X == 511
    assert VPN_TOGGLE_Y == 172
