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
        account_switcher_opener=TabCoord(x=293, y=249),
        account_switcher_opener_alt=TabCoord(x=301, y=288),
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
async def test_ensure_current_only_taps_home_when_handle_matches() -> None:
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    plus_checks = {"n": 0}

    async def find_template(*_args, **_kwargs):
        plus_checks["n"] += 1
        if plus_checks["n"] <= 1:
            return {"x": 203, "y": 680, "confidence": 0.92}
        return None

    controller.find_template_on_device = find_template
    nav = _navigation()
    opener_x = nav.account_switcher_opener_x

    async def find_text(_device_id, queries, **kwargs):
        if kwargs.get("rect") is not None:
            return [{"text": "@myuser", "confidence": 0.9}]
        return []

    controller.find_text_on_device = find_text
    controller.ocr_on_device = AsyncMock(return_value="")

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
    switcher_taps = [
        call for call in controller.tap.await_args_list if call.args[1:] == (opener_x, nav.account_switcher_opener_y)
    ]
    assert not switcher_taps


@pytest.mark.asyncio
async def test_already_on_account_taps_home_only() -> None:
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    plus_checks = {"n": 0}

    async def find_template(*_args, **_kwargs):
        plus_checks["n"] += 1
        if plus_checks["n"] <= 1:
            return {"x": 203, "y": 680, "confidence": 0.92}
        return None

    controller.find_template_on_device = find_template
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
    assert controller.tap.await_count == 2


@pytest.mark.asyncio
async def test_ensure_current_runs_full_switch_only_after_scan_miss() -> None:
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    plus_checks = {"n": 0}

    async def find_template(*_args, **_kwargs):
        plus_checks["n"] += 1
        if plus_checks["n"] <= 2:
            return {"x": 203, "y": 680, "confidence": 0.92}
        return None

    controller.find_template_on_device = find_template

    async def find_text(_device_id, queries, **kwargs):
        if kwargs.get("rect") is not None:
            return []
        return [{"x": 200, "y": 300, "confidence": 0.9}]

    controller.find_text_on_device = find_text
    controller.ocr_on_device = AsyncMock(return_value="")

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
    controller.tap.assert_any_await("dev-1", nav.account_switcher_opener_x, nav.account_switcher_opener_y)


@pytest.mark.asyncio
async def test_clear_popups_runs_on_home_profile_and_switcher() -> None:
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    plus_checks = {"n": 0}

    async def find_template(*_args, **_kwargs):
        plus_checks["n"] += 1
        if plus_checks["n"] <= 1:
            return {"x": 203, "y": 680, "confidence": 0.92}
        return None

    controller.find_template_on_device = find_template
    cleared: list[str] = []

    async def clear_popups(context: str) -> bool:
        cleared.append(context)
        return False

    async def find_text(_device_id, queries, **kwargs):
        if kwargs.get("rect") is not None:
            return []
        if any("myuser" in str(q).lower() for q in queries):
            return [{"x": 200, "y": 300, "confidence": 0.9}]
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
    assert "account_switcher" in cleared


@pytest.mark.asyncio
async def test_profile_retap_after_popup_dismissed() -> None:
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    nav = _navigation()
    profile = (nav.profile_tab_x, nav.profile_tab_y)
    plus_checks = {"n": 0}

    async def find_template(*_args, **_kwargs):
        plus_checks["n"] += 1
        if plus_checks["n"] <= 2:
            return {"x": 203, "y": 680, "confidence": 0.92}
        return None

    controller.find_template_on_device = find_template

    cleared_once = {"done": False}

    async def clear_popups(context: str) -> bool:
        if context == "account_profile_tab_after_tap" and not cleared_once["done"]:
            cleared_once["done"] = True
            return True
        return False

    find_calls = {"n": 0}

    async def find_text(_device_id, queries, **kwargs):
        if kwargs.get("rect") is not None:
            find_calls["n"] += 1
            if find_calls["n"] >= 2:
                return [{"text": "@myuser", "confidence": 0.9}]
            return []
        return []

    controller.find_text_on_device = find_text
    controller.ocr_on_device = AsyncMock(return_value="")

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
    assert len(profile_taps) >= 1


@pytest.mark.asyncio
async def test_profile_tab_retries_while_home_plus_still_visible() -> None:
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    nav = _navigation()
    profile = (nav.profile_tab_x, nav.profile_tab_y)
    plus_checks = {"n": 0}

    async def find_template(*_args, **_kwargs):
        plus_checks["n"] += 1
        if plus_checks["n"] <= 3:
            return {"x": 203, "y": 680, "confidence": 0.92}
        return None

    controller.find_template_on_device = find_template

    async def find_text(_device_id, queries, **kwargs):
        if kwargs.get("rect") is not None:
            if plus_checks["n"] >= 4:
                return [{"text": "@myuser", "confidence": 0.9}]
            return []
        return []

    controller.find_text_on_device = find_text
    controller.ocr_on_device = AsyncMock(return_value="")

    result = await ensure_tiktok_account(
        controller=controller,
        device_id="dev-1",
        tiktok_handle="@myuser",
        navigation=nav,
        brand="labely",
    )

    assert result is True
    profile_taps = [
        call for call in controller.tap.await_args_list if call.args[1:] == profile
    ]
    assert len(profile_taps) >= 2


@pytest.mark.asyncio
async def test_switches_to_dashboard_handle_when_on_other_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    plus_checks = {"n": 0}

    async def find_template(*_args, **_kwargs):
        plus_checks["n"] += 1
        if plus_checks["n"] <= 1:
            return {"x": 203, "y": 680, "confidence": 0.92}
        return None

    controller.find_template_on_device = find_template
    find_calls = {"n": 0}

    async def find_text(_device_id, queries, **kwargs):
        if kwargs.get("rect") is not None:
            return []
        if any("myuser" in str(q).lower() for q in queries):
            return [{"x": 200, "y": 300, "confidence": 0.8}]
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
    controller.tap.assert_any_await("dev-1", 293, 249)
    controller.tap.assert_any_await("dev-1", 200, 300)
    assert controller.tap.await_count >= 4


@pytest.mark.asyncio
async def test_full_switch_toggles_to_opposite_when_on_dashboard_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    plus_checks = {"n": 0}

    async def find_template(*_args, **_kwargs):
        plus_checks["n"] += 1
        if plus_checks["n"] <= 1:
            return {"x": 203, "y": 680, "confidence": 0.92}
        return None

    controller.find_template_on_device = find_template
    find_calls = {"n": 0}

    async def find_text(_device_id, queries, **kwargs):
        if kwargs.get("rect") is not None:
            if any("valcoin" in str(q).lower() for q in queries):
                return []
            if any("myuser" in str(q).lower() for q in queries):
                return [{"text": "@myuser", "confidence": 0.9}]
            return []
        if any("valcoin" in str(q).lower() for q in queries):
            return [{"x": 210, "y": 310, "confidence": 0.8}]
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
    controller.tap.assert_any_await("dev-1", 293, 249)
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
async def test_slot_16_uses_alternate_switcher_opener_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from imouse_farm.config.models import AppConfig, TikTokDeviceUiConfig, TikTokDeviceUiSlotConfig, TabCoord

    cfg = AppConfig(
        tiktok_device_ui=TikTokDeviceUiConfig(
            slots={
                "16": TikTokDeviceUiSlotConfig(
                    ui_label="Different UI",
                    account_switcher_opener=TabCoord(x=101, y=147),
                    use_alternate_account_switcher=True,
                )
            }
        )
    )
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)

    async def find_text(*_args, **_kwargs):
        return [{"x": 120, "y": 180, "confidence": 0.9}]

    controller.find_text_on_device = find_text
    controller.ocr_on_device = AsyncMock(return_value="")

    nav = _navigation()
    opened = await _open_account_switcher(
        controller,
        "dev-1",
        nav,
        ["@otheruser"],
        app_config=cfg,
        device_user_name="16",
    )

    assert opened is True
    controller.tap.assert_awaited_once_with("dev-1", 101, 147)


@pytest.mark.asyncio
async def test_opener_tries_primary_coordinate_when_alt_misses(
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
    assert controller.tap.await_args_list[0].args[1:] == (293, 249)
    assert controller.tap.await_args_list[1].args[1:] == (301, 288)


def test_opposite_brand() -> None:
    assert opposite_brand("labely") == "valcoin"
    assert opposite_brand("valcoin") == "labely"


@pytest.mark.asyncio
async def test_no_vision_when_wrong_account_on_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Profile opened but wrong @ — switch via dropdown, not vision on profile tab."""
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    plus_checks = {"n": 0}

    async def find_template(*_args, **_kwargs):
        plus_checks["n"] += 1
        if plus_checks["n"] <= 1:
            return {"x": 203, "y": 680, "confidence": 0.92}
        return None

    controller.find_template_on_device = find_template
    vision = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "imouse_farm.workflows.account_switch._vision_dismiss_profile_error",
        vision,
    )

    async def find_text(_device_id, queries, **kwargs):
        if kwargs.get("rect") is not None:
            return []
        return [{"x": 200, "y": 300, "confidence": 0.9}]

    controller.find_text_on_device = find_text
    controller.ocr_on_device = AsyncMock(return_value="")

    result = await ensure_tiktok_account(
        controller=controller,
        device_id="dev-1",
        tiktok_handle="@myuser",
        navigation=_navigation(),
        brand="labely",
        app_config=MagicMock(),
    )

    assert result is True
    assert vision.await_count == 0


@pytest.mark.asyncio
async def test_profile_tab_uses_vision_when_switcher_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MagicMock()
    controller.tap = AsyncMock(return_value=True)
    plus_checks = {"n": 0}

    async def find_template(*_args, **_kwargs):
        plus_checks["n"] += 1
        if plus_checks["n"] <= 1:
            return {"x": 203, "y": 680, "confidence": 0.92}
        return None

    controller.find_template_on_device = find_template

    open_calls = {"n": 0}

    async def flaky_open(*args, **kwargs):
        open_calls["n"] += 1
        return open_calls["n"] >= 2

    monkeypatch.setattr(
        "imouse_farm.workflows.account_switch._open_account_switcher",
        flaky_open,
    )
    vision = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "imouse_farm.workflows.account_switch._vision_dismiss_profile_error",
        vision,
    )
    find_calls = {"n": 0}

    async def find_text(_device_id, queries, **kwargs):
        if kwargs.get("rect") is not None:
            return []
        if any("myuser" in str(q).lower() for q in queries):
            return [{"x": 200, "y": 300, "confidence": 0.9}]
        return [{"x": 200, "y": 300, "confidence": 0.9}]

    controller.find_text_on_device = find_text
    controller.ocr_on_device = AsyncMock(return_value="")

    result = await ensure_tiktok_account(
        controller=controller,
        device_id="dev-1",
        tiktok_handle="@myuser",
        navigation=_navigation(),
        brand="labely",
        app_config=MagicMock(),
    )

    assert result is True
    assert vision.await_count >= 1
    assert any(
        call.kwargs.get("context") == "account switcher did not open"
        for call in vision.await_args_list
    )
    assert open_calls["n"] == 2
