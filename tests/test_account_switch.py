"""Tests for TikTok account switch workflow step."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.config.models import TabCoord, TikTokNavigationConfig
from imouse_farm.post.account_profile_store import opposite_brand
from imouse_farm.workflows.account_switch import (
    _open_account_switcher,
    _screen_shows_handle,
    ensure_tiktok_account,
)


def _navigation() -> TikTokNavigationConfig:
    return TikTokNavigationConfig(
        profile_tab=TabCoord(x=559, y=1037),
        home_tab=TabCoord(x=60, y=1041),
        account_switcher_opener=TabCoord(x=301, y=288),
        account_switcher_opener_alt=TabCoord(x=293, y=249),
        account_switcher_opener_fallback=TabCoord(x=136, y=156),
        account_likes_dismiss_ok=TabCoord(x=308, y=766),
    )


def _mock_plus_visible(controller: MagicMock) -> None:
    controller.find_template_on_device = AsyncMock(
        return_value={"x": 203, "y": 680, "confidence": 0.92}
    )


@pytest.mark.asyncio
async def test_skips_when_no_handle_configured() -> None:
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    result = await ensure_tiktok_account(
        controller=controller,
        device_id="dev-1",
        tiktok_handle="",
        navigation=_navigation(),
    )
    assert result is True
    controller.tap.assert_not_awaited()


@pytest.mark.asyncio
async def test_already_on_account_taps_home_only() -> None:
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    _mock_plus_visible(controller)
    controller.find_text_on_device = AsyncMock(
        return_value=[{"x": 100, "y": 50, "confidence": 0.9}]
    )
    nav = _navigation()
    result = await ensure_tiktok_account(
        controller=controller,
        device_id="dev-1",
        tiktok_handle="@myuser",
        navigation=nav,
        brand="labely",
    )
    assert result is True
    controller.tap.assert_any_await("dev-1", nav.profile_tab_x, nav.profile_tab_y)
    controller.tap.assert_any_await("dev-1", nav.home_tab_x, nav.home_tab_y)
    assert controller.tap.await_count == 3


@pytest.mark.asyncio
async def test_clear_popups_runs_on_home_profile_and_switcher() -> None:
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    _mock_plus_visible(controller)
    cleared: list[str] = []

    async def clear_popups(context: str) -> bool:
        cleared.append(context)
        return False

    find_calls = {"n": 0}

    async def find_text(*_args, **_kwargs):
        find_calls["n"] += 1
        if find_calls["n"] <= 2:
            return []
        if find_calls["n"] == 3:
            return [{"text": "@myuser", "confidence": 0.9}]
        return [{"x": 200, "y": 300, "confidence": 0.8}]

    controller.find_text_on_device = find_text
    controller.ocr_on_device = AsyncMock(return_value="")

    result = await ensure_tiktok_account(
        controller=controller,
        device_id="dev-1",
        tiktok_handle="@myuser",
        navigation=_navigation(),
        brand="labely",
        clear_popups=clear_popups,
    )

    assert result is True
    assert cleared == [
        "account_home_ready",
        "account_profile_tab",
        "account_profile_tab_after_tap",
        "account_switcher",
    ]


@pytest.mark.asyncio
async def test_profile_retap_after_popup_dismissed() -> None:
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    _mock_plus_visible(controller)
    nav = _navigation()
    profile = (nav.profile_tab_x, nav.profile_tab_y)

    async def clear_popups(context: str) -> bool:
        return context == "account_profile_tab_after_tap"

    controller.find_text_on_device = AsyncMock(
        return_value=[{"x": 100, "y": 50, "confidence": 0.9}]
    )

    result = await ensure_tiktok_account(
        controller=controller,
        device_id="dev-1",
        tiktok_handle="@myuser",
        navigation=nav,
        brand="labely",
        clear_popups=clear_popups,
    )

    assert result is True
    profile_taps = [
        call
        for call in controller.tap.await_args_list
        if call.args[1:] == profile
    ]
    assert len(profile_taps) == 4


@pytest.mark.asyncio
async def test_switches_to_dashboard_handle_when_on_other_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    _mock_plus_visible(controller)
    find_calls = {"n": 0}

    async def find_text(*_args, **_kwargs):
        find_calls["n"] += 1
        if find_calls["n"] <= 2:
            return []
        if find_calls["n"] == 3:
            return [{"text": "@myuser", "confidence": 0.9}]
        return [{"x": 200, "y": 300, "confidence": 0.8}]

    controller.find_text_on_device = find_text
    controller.ocr_on_device = AsyncMock(return_value="")

    other_profile = {"tiktok_handle": "@valcoinuser", "brand": "valcoin"}

    def fake_get_profile(_device_id: str, _user_name: str, *, brand: str = "labely"):
        if brand == "valcoin":
            return other_profile
        return {"tiktok_handle": "@myuser", "brand": "labely"}

    monkeypatch.setattr(
        "imouse_farm.workflows.account_switch.get_profile_for_device",
        fake_get_profile,
    )

    nav = _navigation()
    result = await ensure_tiktok_account(
        controller=controller,
        device_id="dev-1",
        tiktok_handle="@myuser",
        navigation=nav,
        brand="labely",
    )
    assert result is True
    controller.tap.assert_any_await("dev-1", 301, 288)
    controller.tap.assert_any_await("dev-1", 200, 300)
    assert controller.tap.await_count >= 4


@pytest.mark.asyncio
async def test_full_switch_toggles_to_opposite_when_on_dashboard_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    _mock_plus_visible(controller)
    find_calls = {"n": 0}

    async def find_text(*_args, **_kwargs):
        find_calls["n"] += 1
        if find_calls["n"] <= 2:
            return []
        if find_calls["n"] == 3:
            return [{"text": "@valcoinuser", "confidence": 0.9}]
        return [{"x": 210, "y": 310, "confidence": 0.8}]

    controller.find_text_on_device = find_text
    controller.ocr_on_device = AsyncMock(return_value="@myuser on profile")

    other_profile = {"tiktok_handle": "@valcoinuser", "brand": "valcoin"}

    def fake_get_profile(_device_id: str, _user_name: str, *, brand: str = "labely"):
        if brand == "valcoin":
            return other_profile
        return {"tiktok_handle": "@myuser", "brand": "labely"}

    monkeypatch.setattr(
        "imouse_farm.workflows.account_switch.get_profile_for_device",
        fake_get_profile,
    )

    nav = _navigation()
    result = await ensure_tiktok_account(
        controller=controller,
        device_id="dev-1",
        tiktok_handle="@myuser",
        navigation=nav,
        brand="labely",
        toggle_to_opposite=True,
    )
    assert result is True
    controller.tap.assert_any_await("dev-1", 301, 288)
    controller.tap.assert_any_await("dev-1", 210, 310)
    assert controller.tap.await_count >= 4


@pytest.mark.asyncio
async def test_screen_shows_handle_ignores_bare_name_in_bio() -> None:
    controller = MagicMock()
    controller.find_text_on_device = AsyncMock(return_value=[])
    controller.ocr_on_device = AsyncMock(return_value="Labely iOS app @valcoinuser")
    shown = await _screen_shows_handle(
        controller,
        "dev-1",
        ["@myuser", "myuser"],
        [0, 0, 400, 300],
    )
    assert shown is False


@pytest.mark.asyncio
async def test_opener_tries_alt_coordinate_when_primary_misses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    checks = {"n": 0}

    async def fake_switcher_shows(*_args, **_kwargs) -> bool:
        checks["n"] += 1
        return checks["n"] >= 2

    monkeypatch.setattr(
        "imouse_farm.workflows.account_switch._switcher_shows_account",
        fake_switcher_shows,
    )

    nav = _navigation()
    opened = await _open_account_switcher(
        controller, "dev-1", nav, ["@valcoinuser", "valcoinuser"]
    )

    assert opened is True
    assert controller.tap.await_args_list[0].args[1:] == (301, 288)
    assert controller.tap.await_args_list[1].args[1:] == (293, 249)


@pytest.mark.asyncio
async def test_opener_dismisses_likes_then_uses_fallback_ui() -> None:
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    visible = {"n": 0}

    async def find_text(*_args, **_kwargs):
        visible["n"] += 1
        if visible["n"] <= 4:
            return []
        return [{"x": 120, "y": 180, "confidence": 0.9}]

    controller.find_text_on_device = find_text
    controller.ocr_on_device = AsyncMock(return_value="")

    nav = _navigation()
    opened = await _open_account_switcher(
        controller, "dev-1", nav, ["@valcoinuser", "valcoinuser"]
    )
    assert opened is True
    controller.tap.assert_any_await("dev-1", 301, 288)
    controller.tap.assert_any_await("dev-1", 293, 249)
    controller.tap.assert_any_await("dev-1", 308, 766)
    controller.tap.assert_any_await("dev-1", 136, 156)


def test_opposite_brand() -> None:
    assert opposite_brand("labely") == "valcoin"
    assert opposite_brand("valcoin") == "labely"
