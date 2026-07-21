"""Tests for fixed-coord Shadowrocket VPN helpers."""

import pytest

from imouse_farm.actions.vpn_shadowrocket import (
    SHADOWROCKET_ICON_X,
    SHADOWROCKET_ICON_Y,
    SHADOWROCKET_TOGGLE_X,
    SHADOWROCKET_TOGGLE_Y,
    TIKTOK_HOME_ICON_X,
    TIKTOK_HOME_ICON_Y,
    VpnVisionUnreadable,
    _looks_unreadable_vpn_reply,
    _parse_vpn_status,
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


def test_parse_vpn_status_on_off() -> None:
    assert _parse_vpn_status("STATUS: ON") == "on"
    assert _parse_vpn_status("STATUS: OFF") == "off"


def test_parse_vpn_status_rejects_apology() -> None:
    with pytest.raises(VpnVisionUnreadable):
        _parse_vpn_status("I'm sorry, I can't determine the status from this image.")


def test_parse_vpn_status_unknown() -> None:
    with pytest.raises(VpnVisionUnreadable):
        _parse_vpn_status("STATUS: UNKNOWN")


def test_looks_unreadable() -> None:
    assert _looks_unreadable_vpn_reply("STATUS: UNKNOWN")
    assert _looks_unreadable_vpn_reply("I can't determine the status")
    assert not _looks_unreadable_vpn_reply("STATUS: OFF")
