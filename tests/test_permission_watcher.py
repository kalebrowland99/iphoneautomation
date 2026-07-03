"""Tests for iOS permission dialog classification."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.actions.permission_prompts import (
    is_permission_dialog_text,
    should_allow_permission,
    button_texts_for_permission,
)


def test_detects_ios_permission_dialog() -> None:
    text = '"TikTok" Would Like to Access Your Contacts\nDon\'t Allow\nAllow'
    assert is_permission_dialog_text(text)


def test_allows_camera_microphone_photos() -> None:
    assert should_allow_permission('"TikTok" Would Like to Access the Camera')
    assert should_allow_permission('"TikTok" Would Like to Access Your Microphone')
    assert should_allow_permission('"TikTok" Would Like to Access Your Photos')


def test_denies_contacts_location_notifications() -> None:
    assert not should_allow_permission('"TikTok" Would Like to Access Your Contacts')
    assert not should_allow_permission('"TikTok" Would Like to Access Your Location')
    assert not should_allow_permission('"TikTok" Would Like to Send You Notifications')
    assert not should_allow_permission(
        'Allow "TikTok" to track your activity across other companies\' apps and websites?'
    )


def test_button_texts_for_deny_vs_allow() -> None:
    assert "Don't Allow" in button_texts_for_permission(False)
    assert "Allow" in button_texts_for_permission(True)


def test_detects_tiktok_email_confirm_dialog() -> None:
    from imouse_farm.actions.permission_prompts import is_tiktok_email_confirm_dialog

    text = "Confirm use of email\nAdd your email to your account\nNot Now\nConfirm"
    assert is_tiktok_email_confirm_dialog(text)


def test_detects_tiktok_save_login_dialog() -> None:
    from imouse_farm.actions.permission_prompts import is_tiktok_save_login_dialog

    assert is_tiktok_save_login_dialog("Save login for next time?\nNot now")
    assert is_tiktok_save_login_dialog("Saveloginfornexttime Notnow")


@pytest.mark.asyncio
async def test_permission_watcher_dismisses_save_login() -> None:
    from imouse_farm.permissions.watcher import PermissionWatcher

    controller = MagicMock()
    controller.ocr_on_device = AsyncMock(
        return_value="Save login for next time?\nNot now"
    )
    controller.find_text_on_device = AsyncMock(
        return_value=[{"text": "Not now", "x": 210, "y": 580, "confidence": 0.95}]
    )
    controller.tap = AsyncMock(return_value=True)
    watcher = PermissionWatcher(controller, "phone-1", poll_interval_seconds=0.25)

    assert await watcher._check_once() is True
    controller.tap.assert_awaited_once_with("phone-1", 210, 580)


def test_not_now_label() -> None:
    from imouse_farm.actions.permission_prompts import is_not_now_label

    assert is_not_now_label("Not Now")
    assert is_not_now_label("NOT NOW")
    assert not is_not_now_label("Confirm")


def test_detects_tiktok_post_notify_dialog() -> None:
    from imouse_farm.actions.permission_prompts import is_tiktok_post_notify_dialog

    text = "Get notified of post interactions?\nGet notified\nNot now"
    assert is_tiktok_post_notify_dialog(text)
    assert is_tiktok_post_notify_dialog("Get notified\nNot now")
    assert is_tiktok_post_notify_dialog("Get notified")
    assert is_tiktok_post_notify_dialog("GET NOTIFIED")
    assert is_tiktok_post_notify_dialog("get Notified of stuff")


def test_post_notify_dismiss_coords() -> None:
    from imouse_farm.actions.permission_prompts import tiktok_post_notify_dismiss_coords

    assert tiktok_post_notify_dismiss_coords() == (203, 63)


def test_detects_ios_passkeys_passcode_dialog() -> None:
    from imouse_farm.actions.permission_prompts import is_ios_passkeys_passcode_dialog

    text = "Passkeys require a passcode and work best with Touch ID"
    assert is_ios_passkeys_passcode_dialog(text)


def test_detects_tiktok_security_checkup_dialog() -> None:
    from imouse_farm.actions.permission_prompts import (
        is_tiktok_security_checkup_dialog,
        tiktok_security_checkup_dismiss_coords,
    )

    text = "Let's do a quick security checkup?"
    assert is_tiktok_security_checkup_dialog(text)
    assert tiktok_security_checkup_dismiss_coords() == (570, 501)


@pytest.mark.asyncio
async def test_detect_security_checkup_uses_find_text_fallback() -> None:
    from imouse_farm.permissions.watcher import detect_tiktok_security_checkup_on_device

    controller = MagicMock()
    controller.ocr_on_device = AsyncMock(return_value="Tony.r12 Edit profile")
    controller.ocr_items_on_device = AsyncMock(return_value=[])
    controller.find_text_on_device = AsyncMock(
        return_value=[{"text": "security checkup", "x": 200, "y": 300, "confidence": 0.9}]
    )
    visible, sample = await detect_tiktok_security_checkup_on_device(
        controller,
        "phone-10",
        screen="Tony.r12 Edit profile",
    )
    assert visible is True
    assert "security checkup" in sample.lower()
    controller.find_text_on_device.assert_awaited()


@pytest.mark.asyncio
async def test_detect_security_checkup_uses_modal_ocr() -> None:
    from imouse_farm.permissions.watcher import detect_tiktok_security_checkup_on_device

    controller = MagicMock()
    controller.ocr_on_device = AsyncMock(return_value="Tony.r12 Edit profile")
    controller.find_text_on_device = AsyncMock(return_value=[])

    async def _ocr_items(device_id, *, is_ex=False, rect=None):
        if is_ex and rect is not None:
            return [{"text": "Let's do a quick security checkup", "x": 200, "y": 300}]
        return []

    controller.ocr_items_on_device = _ocr_items
    visible, sample = await detect_tiktok_security_checkup_on_device(
        controller,
        "phone-10",
        screen="Tony.r12 Edit profile",
    )
    assert visible is True
    assert "security checkup" in sample.lower()


@pytest.mark.asyncio
async def test_permission_watcher_dismisses_security_checkup() -> None:
    from imouse_farm.permissions.watcher import PermissionWatcher

    controller = MagicMock()
    controller.ocr_on_device = AsyncMock(
        return_value="Let's do a quick security checkup?"
    )
    controller.ocr_items_on_device = AsyncMock(return_value=[])
    controller.find_text_on_device = AsyncMock(return_value=[])
    controller.tap = AsyncMock(return_value=True)
    watcher = PermissionWatcher(controller, "phone-1", poll_interval_seconds=0.25)

    assert await watcher._check_once() is True
    controller.tap.assert_awaited_once_with("phone-1", 570, 501)


def test_detects_tiktok_add_phone_dialog() -> None:
    from imouse_farm.actions.permission_prompts import (
        is_tiktok_add_phone_dialog,
        tiktok_add_phone_dismiss_coords,
    )

    assert is_tiktok_add_phone_dialog("Add phone")
    assert tiktok_add_phone_dismiss_coords() == (564, 260)


@pytest.mark.asyncio
async def test_detect_add_phone_uses_find_text_fallback() -> None:
    from imouse_farm.permissions.watcher import detect_tiktok_add_phone_on_device

    controller = MagicMock()
    controller.ocr_on_device = AsyncMock(return_value="Tony.r12 Edit profile")
    controller.ocr_items_on_device = AsyncMock(return_value=[])
    controller.find_text_on_device = AsyncMock(
        return_value=[{"text": "Add phone", "x": 200, "y": 300, "confidence": 0.9}]
    )
    visible, sample = await detect_tiktok_add_phone_on_device(
        controller,
        "phone-10",
        screen="Tony.r12 Edit profile",
    )
    assert visible is True
    assert "add phone" in sample.lower()
    controller.find_text_on_device.assert_awaited()


@pytest.mark.asyncio
async def test_permission_watcher_dismisses_add_phone() -> None:
    from imouse_farm.permissions.watcher import PermissionWatcher

    controller = MagicMock()
    controller.ocr_on_device = AsyncMock(return_value="Add phone")
    controller.ocr_items_on_device = AsyncMock(return_value=[])
    controller.find_text_on_device = AsyncMock(return_value=[])
    controller.tap = AsyncMock(return_value=True)
    watcher = PermissionWatcher(controller, "phone-1", poll_interval_seconds=0.25)

    assert await watcher._check_once() is True
    controller.tap.assert_awaited_once_with("phone-1", 564, 260)


@pytest.mark.asyncio
async def test_permission_watcher_dismisses_passkeys_passcode() -> None:
    from imouse_farm.permissions.watcher import PermissionWatcher

    controller = MagicMock()
    controller.ocr_on_device = AsyncMock(
        return_value="Passkeys require a passcode and work best with Touch ID"
    )
    controller.ocr_items_on_device = AsyncMock(return_value=[])
    controller.find_text_on_device = AsyncMock(return_value=[])
    controller.press_home = AsyncMock(return_value=True)
    watcher = PermissionWatcher(controller, "phone-1", poll_interval_seconds=0.25)

    assert await watcher._check_once() is True
    controller.press_home.assert_awaited_once_with("phone-1")


@pytest.mark.asyncio
async def test_permission_watcher_taps_viewer_history_save() -> None:
    from imouse_farm.permissions.watcher import PermissionWatcher

    controller = MagicMock()
    controller.ocr_on_device = AsyncMock(return_value="Viewer history turned on")
    controller.find_text_on_device = AsyncMock(
        return_value=[
            {"text": "Cancel", "x": 100, "y": 500, "confidence": 0.9},
            {"text": "Save", "x": 300, "y": 500, "confidence": 0.95},
        ]
    )
    controller.capture_screenshot = AsyncMock(return_value=None)
    controller.tap = AsyncMock(return_value=True)
    watcher = PermissionWatcher(controller, "phone-1", poll_interval_seconds=0.25)

    assert await watcher._check_once() is True
    controller.tap.assert_awaited_once_with("phone-1", 300, 500)


@pytest.mark.asyncio
async def test_permission_watcher_dismisses_avatar_style() -> None:
    from imouse_farm.permissions.watcher import PermissionWatcher

    controller = MagicMock()
    controller.ocr_on_device = AsyncMock(return_value="Your avatar, your style")
    controller.tap = AsyncMock(return_value=True)
    watcher = PermissionWatcher(controller, "phone-1", poll_interval_seconds=0.25)

    assert await watcher._check_once() is True
    controller.tap.assert_awaited_once_with("phone-1", 563, 92)


@pytest.mark.asyncio
async def test_permission_watcher_dismisses_ai_pick() -> None:
    from imouse_farm.permissions.watcher import PermissionWatcher

    controller = MagicMock()
    controller.ocr_on_device = AsyncMock(return_value="Recents")
    controller.ocr_items_on_device = AsyncMock(
        return_value=[{"text": "Let AI pick for you"}]
    )
    controller.find_text_on_device = AsyncMock(return_value=[])
    controller.tap = AsyncMock(return_value=True)
    watcher = PermissionWatcher(controller, "phone-1", poll_interval_seconds=0.25)

    assert await watcher._check_once() is True
    controller.tap.assert_awaited_once_with("phone-1", 184, 972)


@pytest.mark.asyncio
async def test_permission_watcher_taps_virtual_items_got_it() -> None:
    from imouse_farm.permissions.watcher import PermissionWatcher

    controller = MagicMock()
    controller.ocr_on_device = AsyncMock(
        return_value="Virtual Items and Rewards Policies update"
    )
    controller.find_text_on_device = AsyncMock(
        return_value=[{"text": "Got it", "x": 210, "y": 620, "confidence": 0.95}]
    )
    controller.tap = AsyncMock(return_value=True)
    watcher = PermissionWatcher(controller, "phone-1", poll_interval_seconds=0.25)

    assert await watcher._check_once() is True
    controller.tap.assert_awaited_once_with("phone-1", 210, 620)


def test_detects_tiktok_continue_editing_dialog() -> None:
    from imouse_farm.actions.permission_prompts import (
        is_tiktok_continue_editing_dialog,
        tiktok_continue_editing_swipe_coords,
    )

    assert is_tiktok_continue_editing_dialog("Continue editing this post?")
    assert tiktok_continue_editing_swipe_coords() == (65, 151, 65, 0)


@pytest.mark.asyncio
async def test_permission_watcher_dismisses_continue_editing() -> None:
    from imouse_farm.permissions.watcher import PermissionWatcher

    controller = MagicMock()
    controller.ocr_on_device = AsyncMock(return_value="Continue editing this post?")
    controller.swipe = AsyncMock(return_value=True)
    watcher = PermissionWatcher(controller, "phone-1", poll_interval_seconds=0.25)

    assert await watcher._check_once() is True
    controller.swipe.assert_awaited_once_with(
        "phone-1",
        direction="up",
        sx=65,
        sy=151,
        ex=65,
        ey=0,
    )


@pytest.mark.asyncio
async def test_permission_watcher_manager_run_watcher_cycle() -> None:
    from imouse_farm.permissions.watcher import PermissionWatcherManager

    controller = MagicMock()
    manager = PermissionWatcherManager(controller, poll_interval_seconds=0.25)
    manager._watchers["phone-1"] = MagicMock()
    manager._watchers["phone-1"].run_full_cycle = AsyncMock(return_value=True)

    assert await manager.run_watcher_cycle("phone-1") is True
    manager._watchers["phone-1"].run_full_cycle.assert_awaited_once()


@pytest.mark.asyncio
async def test_permission_watcher_manager_try_dismiss() -> None:
    from imouse_farm.permissions.watcher import PermissionWatcherManager

    controller = MagicMock()
    manager = PermissionWatcherManager(controller, poll_interval_seconds=0.25)
    manager._watchers["phone-1"] = MagicMock()
    manager._watchers["phone-1"]._check_once = AsyncMock(return_value=True)

    assert await manager.try_dismiss("phone-1") is True
    manager._watchers["phone-1"]._check_once.assert_awaited_once()


@pytest.mark.asyncio
async def test_release_does_not_stop_watcher() -> None:
    from imouse_farm.permissions.watcher import PermissionWatcher, PermissionWatcherManager

    controller = MagicMock()
    manager = PermissionWatcherManager(controller)
    watcher = MagicMock(spec=PermissionWatcher)
    watcher.start = AsyncMock()
    watcher.stop = AsyncMock()
    manager._watchers["phone-1"] = watcher

    await manager.release("phone-1")

    watcher.stop.assert_not_awaited()
    assert "phone-1" in manager._watchers


@pytest.mark.asyncio
async def test_contacts_fast_loop_taps_dont_allow() -> None:
    from imouse_farm.permissions.watcher import PermissionWatcher

    controller = MagicMock()
    controller.find_text_on_device = AsyncMock(
        return_value=[
            {"text": "Find contacts", "x": 200, "y": 300, "confidence": 0.9},
            {"text": "Don't allow", "x": 210, "y": 560, "confidence": 0.95},
        ]
    )
    controller.tap = AsyncMock(return_value=True)
    watcher = PermissionWatcher(controller, "phone-1", poll_interval_seconds=0.25)

    assert await watcher._check_contacts_once() is True
    controller.tap.assert_awaited_once_with("phone-1", 210, 560)


@pytest.mark.asyncio
async def test_contacts_fast_loop_ignores_deny_without_contacts_context() -> None:
    from imouse_farm.permissions.watcher import PermissionWatcher

    controller = MagicMock()
    controller.find_text_on_device = AsyncMock(
        return_value=[{"text": "Don't Allow", "x": 210, "y": 560, "confidence": 0.95}]
    )
    controller.tap = AsyncMock(return_value=True)
    watcher = PermissionWatcher(controller, "phone-1", poll_interval_seconds=0.25)

    assert await watcher._check_contacts_once() is False
    controller.tap.assert_not_awaited()


def test_detects_tiktok_contacts_dialog_from_glued_ocr() -> None:
    from imouse_farm.actions.permission_prompts import (
        analyze_popup_screen,
        is_tiktok_in_app_deny_dialog,
    )

    ocr = (
        "Find contacts Toconnectwithpeopleyouknowon TikTok,allowaccesstoyourcontacts "
        "in your device settings. Turnon TikTok Contacts Don'tallow Opensettings"
    )
    assert is_tiktok_in_app_deny_dialog(ocr)
    result = analyze_popup_screen(ocr)
    assert result["dialog"] == "tiktok_in_app_deny"
    assert result["watcher_action"] == "tap_dont_allow"
    assert "Don't allow" in result["button_labels"]
