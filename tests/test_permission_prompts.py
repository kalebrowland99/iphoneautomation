"""Tests for iOS permission / delete dialog label filtering."""

from imouse_farm.actions.permission_prompts import (
    analyze_popup_screen,
    is_tiktok_live_feed_dialog,
    delete_match_is_stable,
    delete_sheet_is_visible,
    filter_delete_confirm_matches,
    is_delete_confirm_label,
    is_delete_distractor_label,
    known_popup_watcher_button_labels,
    pick_delete_confirm_match,
    resolve_delete_tap,
)


def test_known_popup_watcher_button_labels_includes_tiktok_and_ios() -> None:
    labels = known_popup_watcher_button_labels()
    assert "Not Now" in labels
    assert "Allow" in labels
    assert any(l.lower() == "don't allow" for l in labels)


def test_analyze_popup_screen_tiktok_email() -> None:
    result = analyze_popup_screen("Confirm use of email for your account\nNot Now")
    assert result["dialog"] == "tiktok_email_confirm"
    assert result["watcher_action"] == "tap_not_now"
    assert "Not Now" in result["button_labels"]


def test_analyze_popup_screen_tiktok_save_login() -> None:
    result = analyze_popup_screen("Save login for next time?\nNot now")
    assert result["dialog"] == "tiktok_save_login"
    assert result["watcher_action"] == "tap_not_now"
    assert "Not now" in result["button_labels"]


def test_analyze_popup_screen_tiktok_post_notify() -> None:
    result = analyze_popup_screen("Get notified of post interactions?")
    assert result["dialog"] == "tiktok_post_notify"
    assert result["watcher_action"] == "tap_coord"
    assert result["tap_x"] == 203
    assert result["tap_y"] == 63


def test_analyze_popup_screen_tiktok_security_checkup() -> None:
    result = analyze_popup_screen("Let's do a quick security checkup?")
    assert result["dialog"] == "tiktok_security_checkup"
    assert result["watcher_action"] == "tap_coord"
    assert result["tap_x"] == 570
    assert result["tap_y"] == 501


def test_analyze_popup_screen_tiktok_add_phone() -> None:
    result = analyze_popup_screen("Add phone")
    assert result["dialog"] == "tiktok_add_phone"
    assert result["watcher_action"] == "tap_coord"
    assert result["tap_x"] == 564
    assert result["tap_y"] == 260


def test_add_phone_detects_variants() -> None:
    from imouse_farm.actions.permission_prompts import is_tiktok_add_phone_dialog

    assert is_tiktok_add_phone_dialog("Add phone")
    assert is_tiktok_add_phone_dialog("Add your phone number")
    assert is_tiktok_add_phone_dialog("Addphonenumber")


def test_security_checkup_detects_unicode_apostrophe_and_body_copy() -> None:
    from imouse_farm.actions.permission_prompts import is_tiktok_security_checkup_dialog

    assert is_tiktok_security_checkup_dialog("Let\u2019s do a quick security checkup")
    assert is_tiktok_security_checkup_dialog(
        "Complete a few personalized security tips to strengthen the safety of your account"
    )
    assert is_tiktok_security_checkup_dialog(
        "Completeafewpersonalizedsecuritytipstostrengthenthesafetyofyouraccount"
    )
    assert is_tiktok_security_checkup_dialog("Continue checkup")


def test_analyze_popup_screen_tiktok_continue_editing() -> None:
    result = analyze_popup_screen("Continue editing this post?")
    assert result["dialog"] == "tiktok_continue_editing"
    assert result["watcher_action"] == "swipe_up"
    assert result["swipe_sx"] == 65
    assert result["swipe_sy"] == 151
    assert result["swipe_ey"] == 0


def test_is_tiktok_live_feed_dialog() -> None:
    assert is_tiktok_live_feed_dialog("LIVE now\nTap to watch LIVE")
    assert is_tiktok_live_feed_dialog("Tap to watch LIVE")
    assert is_tiktok_live_feed_dialog("LIVENOW overlay")
    assert not is_tiktok_live_feed_dialog("For You\nFollowing")


def test_analyze_popup_screen_tiktok_live_feed() -> None:
    result = analyze_popup_screen("LIVE now\nTap to watch LIVE")
    assert result["dialog"] == "tiktok_live_feed"
    assert result["watcher_action"] == "swipe_up_random"


def test_analyze_popup_screen_tiktok_post_notify_get_notified_button() -> None:
    result = analyze_popup_screen("Get notified\nNot now")
    assert result["dialog"] == "tiktok_post_notify"
    assert result["watcher_action"] == "tap_coord"

    assert analyze_popup_screen("Get notified")["dialog"] == "tiktok_post_notify"


def test_analyze_popup_screen_ios_passkeys_passcode() -> None:
    result = analyze_popup_screen(
        "Passkeys require a passcode and work best with Touch ID"
    )
    assert result["dialog"] == "ios_passkeys_passcode"
    assert result["watcher_action"] == "press_home"


def test_analyze_popup_screen_tiktok_viewer_history() -> None:
    result = analyze_popup_screen("Viewer history turned on\nSave")
    assert result["dialog"] == "tiktok_viewer_history"
    assert result["watcher_action"] == "tap_save_white"
    assert "Save" in result["button_labels"]


def test_analyze_popup_screen_tiktok_avatar_style() -> None:
    result = analyze_popup_screen("Your avatar, your style")
    assert result["dialog"] == "tiktok_avatar_style"
    assert result["watcher_action"] == "tap_coord"
    assert result["tap_x"] == 563
    assert result["tap_y"] == 92


def test_analyze_popup_screen_tiktok_ai_pick() -> None:
    result = analyze_popup_screen("Let AI pick for you")
    assert result["dialog"] == "tiktok_ai_pick"
    assert result["watcher_action"] == "tap_coord"
    assert result["tap_x"] == 184
    assert result["tap_y"] == 972

    body = analyze_popup_screen(
        "AI matches your photos and videos to different themes\nCancel\nAllow"
    )
    assert body["dialog"] == "tiktok_ai_pick"


def test_analyze_popup_screen_tiktok_virtual_items_policies() -> None:
    result = analyze_popup_screen("Virtual Items and Rewards Policies update\nGot it")
    assert result["dialog"] == "tiktok_virtual_items_policies"
    assert result["watcher_action"] == "tap_got_it"
    assert "Got it" in result["button_labels"]


def test_analyze_popup_screen_ios_permission_allow() -> None:
    result = analyze_popup_screen(
        "TikTok Would Like to Access Your Photos\nAllow\nDon't Allow"
    )
    assert result["dialog"] == "ios_permission"
    assert result["watcher_action"] == "tap_allow"
    assert result["allow_resource"] is True


def test_analyze_popup_screen_ios_local_network() -> None:
    result = analyze_popup_screen(
        '"Shadowrocket" Would Like to Find and Connect to Devices on Your Local Network.\n'
        "Local network access is needed to remotely manage your configuration files on your "
        "local network.\nDon't Allow\nOK"
    )
    assert result["dialog"] == "ios_local_network"
    assert result["watcher_action"] == "tap_ok"
    assert "OK" in result["button_labels"]


def test_analyze_popup_screen_ios_permission_deny_tracking() -> None:
    result = analyze_popup_screen(
        "Allow TikTok to track your activity across apps?\nAllow\nAsk App Not to Track"
    )
    assert result["dialog"] == "ios_permission"
    assert result["watcher_action"] == "tap_deny"
    assert result["allow_resource"] is False


def test_analyze_popup_screen_none() -> None:
    result = analyze_popup_screen("For You\nFollowing")
    assert result["dialog"] == "none"
    assert result["watcher_action"] == "none"


def test_analyze_popup_screen_tiktok_contacts_in_app() -> None:
    ocr = (
        "Find contacts Toconnectwithpeopleyouknowon TikTok,allowaccesstoyourcontacts "
        "Don'tallow Opensettings"
    )
    result = analyze_popup_screen(ocr)
    assert result["dialog"] == "tiktok_in_app_deny"
    assert result["watcher_action"] == "tap_dont_allow"


def test_delete_label_accepts_real_delete_buttons() -> None:
    assert is_delete_confirm_label("Delete 12 Items")
    assert is_delete_confirm_label("Delete All (20)")
    assert is_delete_confirm_label("Delete Photos")
    assert is_delete_confirm_label("Delete Always")
    assert is_delete_confirm_label("Delete All Photos")
    assert is_delete_confirm_label("Delete Everything")
    assert is_delete_confirm_label("Delete")


def test_delete_label_rejects_show_all() -> None:
    assert not is_delete_confirm_label("Show All")
    assert not is_delete_confirm_label("See All Photos")


def test_delete_label_rejects_cancel_variants() -> None:
    assert not is_delete_confirm_label("Don't Delete")
    assert not is_delete_confirm_label("Dont Delete")
    assert not is_delete_confirm_label("Cancel")


def test_is_deny_permission_label_trailing_period() -> None:
    from imouse_farm.actions.permission_prompts import is_deny_permission_label

    assert is_deny_permission_label("Don't allow.")
    assert is_deny_permission_label("Don't allow")
    assert not is_deny_permission_label("Don't Delete")
    assert not is_deny_permission_label("Delete 12 Items")
    assert is_deny_permission_label("Don't Allow")
    assert is_deny_permission_label("Ask App Not to Track")


def test_is_open_external_app_allow_label() -> None:
    from imouse_farm.actions.permission_prompts import is_open_external_app_allow_label

    assert is_open_external_app_allow_label("Allow")
    assert is_open_external_app_allow_label("Open")
    assert not is_open_external_app_allow_label("Don't Allow")
    assert not is_open_external_app_allow_label("Dont Allow")


def test_photo_delete_sheet_skips_permission_watcher_logic() -> None:
    from imouse_farm.actions.permission_prompts import is_photo_delete_sheet_text

    assert is_photo_delete_sheet_text("Delete 12 Photos from Library\nDon't Delete\nDelete")
    assert is_photo_delete_sheet_text("Delete Always\nRemove from library")
    assert is_photo_delete_sheet_text(
        "Privacy Allow 'Shortcuts' to delete 3 photos?\nDon't Delete\nDelete"
    )
    assert not is_photo_delete_sheet_text("TikTok Would Like to Access Your Photos")


def test_distractor_labels_include_show_all() -> None:
    assert is_delete_distractor_label("Show All")
    assert is_delete_distractor_label("Show All 3")
    assert is_delete_distractor_label("ShowAll3")
    assert not is_delete_distractor_label("Delete 12 Items")


def test_pick_delete_rejects_show_all_with_count() -> None:
    matches = [
        {"text": "Show All 3", "x": 200, "y": 655, "confidence": 0.95},
        {"text": "Don't Delete", "x": 200, "y": 600, "confidence": 0.9},
        {"text": "Delete 12 Photos", "x": 200, "y": 670, "confidence": 0.88},
    ]
    picked = pick_delete_confirm_match(matches)
    assert picked is not None
    assert picked["text"] == "Delete 12 Photos"


def test_delete_sheet_not_visible_for_lone_high_delete() -> None:
    matches = [{"text": "Delete", "x": 200, "y": 400, "confidence": 0.99}]
    assert not delete_sheet_is_visible(matches)


def test_pick_delete_ignores_show_all_and_low_y() -> None:
    matches = [
        {"text": "Show All", "x": 200, "y": 650, "confidence": 0.95},
        {"text": "Delete 12 Items", "x": 200, "y": 680, "confidence": 0.9},
        {"text": "Delete", "x": 200, "y": 400, "confidence": 0.99},
    ]
    picked = pick_delete_confirm_match(matches)
    assert picked is not None
    assert picked["text"] == "Delete 12 Items"


def test_pick_delete_prefers_delete_always() -> None:
    matches = [
        {"text": "Delete Always", "x": 200, "y": 670, "confidence": 0.9},
        {"text": "Delete", "x": 200, "y": 680, "confidence": 0.95},
    ]
    picked = pick_delete_confirm_match(matches)
    assert picked is not None
    assert picked["text"] == "Delete Always"


def test_pick_delete_everything_over_bare_delete() -> None:
    matches = [
        {"text": "Delete", "x": 200, "y": 690, "confidence": 0.98},
        {"text": "Delete Everything", "x": 200, "y": 650, "confidence": 0.85},
    ]
    picked = pick_delete_confirm_match(matches)
    assert picked is not None
    assert picked["text"] == "Delete Everything"


def test_pick_delete_all_count_over_bare_delete() -> None:
    matches = [
        {"text": "Delete", "x": 200, "y": 690, "confidence": 0.98},
        {"text": "Delete All (20)", "x": 200, "y": 650, "confidence": 0.82},
    ]
    picked = pick_delete_confirm_match(matches)
    assert picked is not None
    assert picked["text"] == "Delete All (20)"


def test_enrich_merge_delete_all_and_count() -> None:
    from imouse_farm.actions.permission_prompts import enrich_delete_sheet_matches

    matches = [
        {"text": "Delete All", "x": 200, "y": 660, "confidence": 0.9},
        {"text": "(20)", "x": 280, "y": 662, "confidence": 0.88},
        {"text": "Delete", "x": 200, "y": 690, "confidence": 0.98},
    ]
    enriched = enrich_delete_sheet_matches(matches)
    picked = pick_delete_confirm_match(enriched)
    assert picked is not None
    assert picked["text"] == "Delete All (20)"


def test_is_final_bulk_delete_label() -> None:
    from imouse_farm.actions.permission_prompts import is_final_bulk_delete_label

    assert is_final_bulk_delete_label("Delete All (20)")
    assert is_final_bulk_delete_label("Delete Everything")
    assert not is_final_bulk_delete_label("Delete")


def test_pick_delete_all_over_bare_delete() -> None:
    matches = [
        {"text": "Delete", "x": 200, "y": 690, "confidence": 0.98},
        {"text": "Delete All", "x": 200, "y": 650, "confidence": 0.85},
    ]
    picked = pick_delete_confirm_match(matches)
    assert picked is not None
    assert picked["text"] == "Delete All"


def test_pick_delete_uses_relaxed_min_y() -> None:
    matches = [
        {"text": "Show All", "x": 200, "y": 620, "confidence": 0.95},
        {"text": "Delete 3 Items", "x": 200, "y": 480, "confidence": 0.9},
    ]
    assert pick_delete_confirm_match(matches) is None
    assert pick_delete_confirm_match(matches, min_y=460)["text"] == "Delete 3 Items"


def test_delete_sheet_not_visible_for_show_all_only() -> None:
    matches = [{"text": "Show All", "x": 200, "y": 650, "confidence": 0.95}]
    assert not delete_sheet_is_visible(matches)


def test_delete_sheet_visible_for_dont_delete() -> None:
    matches = [{"text": "Don't Delete", "x": 200, "y": 620, "confidence": 0.95}]
    assert delete_sheet_is_visible(matches)


def test_delete_tap_ready_in_one_scan() -> None:
    from imouse_farm.actions.permission_prompts import delete_tap_ready_in_one_scan

    matches = [
        {"text": "Don't Delete", "x": 200, "y": 600, "confidence": 0.9},
        {"text": "Show All 3", "x": 200, "y": 655, "confidence": 0.95},
        {"text": "Delete", "x": 200, "y": 690, "confidence": 0.88},
    ]
    assert delete_tap_ready_in_one_scan(matches)


def test_delete_confirmation_sheet_present() -> None:
    from imouse_farm.actions.permission_prompts import delete_confirmation_sheet_present

    assert delete_confirmation_sheet_present(
        [{"text": "Don't Delete", "x": 200, "y": 600}]
    )
    assert not delete_confirmation_sheet_present(
        [{"text": "Show All 3", "x": 200, "y": 655}]
    )


def test_resolve_delete_tap_no_blind_fallback_on_show_all() -> None:
    matches = [{"text": "Show All", "x": 200, "y": 650, "confidence": 0.95}]
    assert resolve_delete_tap(matches) is None


def test_resolve_delete_tap_waits_for_delete_ocr_not_coords() -> None:
    matches = [{"text": "Don't Delete", "x": 180, "y": 600, "confidence": 0.95}]
    assert resolve_delete_tap(matches) is None


def test_resolve_delete_tap_three_button_sheet_picks_delete() -> None:
    matches = [
        {"text": "Don't Delete", "x": 200, "y": 600, "confidence": 0.9},
        {"text": "Show All 3", "x": 200, "y": 655, "confidence": 0.95},
        {"text": "Delete", "x": 200, "y": 690, "confidence": 0.88},
    ]
    result = resolve_delete_tap(matches)
    assert isinstance(result, dict)
    assert result["text"] == "Delete"
    assert result["y"] == 690


def test_resolve_delete_tap_three_button_sheet_without_delete_is_none() -> None:
    matches = [
        {"text": "Don't Delete", "x": 200, "y": 600, "confidence": 0.9},
        {"text": "Show All 3", "x": 200, "y": 655, "confidence": 0.95},
    ]
    assert resolve_delete_tap(matches) is None


def test_pick_delete_prefers_lowest_below_show_all() -> None:
    matches = [
        {"text": "Don't Delete", "x": 200, "y": 600, "confidence": 0.9},
        {"text": "Show All 3", "x": 200, "y": 655, "confidence": 0.95},
        {"text": "Delete", "x": 200, "y": 690, "confidence": 0.88},
    ]
    picked = pick_delete_confirm_match(matches)
    assert picked is not None
    assert picked["text"] == "Delete"
    assert picked["y"] == 690


def test_resolve_delete_tap_none_when_sheet_not_visible() -> None:
    assert resolve_delete_tap([]) is None


def test_delete_match_stable_within_tolerance() -> None:
    first = {"x": 200, "y": 680}
    second = {"x": 210, "y": 690}
    assert delete_match_is_stable(first, second)
    assert not delete_match_is_stable(first, {"x": 300, "y": 680})


def test_filter_delete_confirm_matches() -> None:
    matches = [
        {"text": "Show All", "x": 1, "y": 700, "confidence": 1.0},
        {"text": "Delete Photos", "x": 2, "y": 690, "confidence": 0.8},
    ]
    assert len(filter_delete_confirm_matches(matches)) == 1
    assert filter_delete_confirm_matches(matches)[0]["text"] == "Delete Photos"
