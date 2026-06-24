"""Tests for iOS permission dialog classification."""

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
