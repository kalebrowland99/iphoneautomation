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


def test_post_notify_dismiss_coords() -> None:
    from imouse_farm.actions.permission_prompts import tiktok_post_notify_dismiss_coords

    assert tiktok_post_notify_dismiss_coords() == (196, 193)


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
