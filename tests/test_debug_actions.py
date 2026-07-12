"""Tests for dashboard debug test registry."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.dashboard.test_actions import (
    FLOW_DEBUG_STEPS,
    MANUAL_DEBUG_TESTS,
    debug_test_skips_media,
    get_debug_registry,
    list_debug_tests,
    run_debug_test,
)


def test_debug_test_skips_media() -> None:
    registry = get_debug_registry()
    assert debug_test_skips_media("clear-album", registry["clear-album"])
    assert debug_test_skips_media("upload-gallery", registry["upload-gallery"])
    assert debug_test_skips_media("tap-post", registry["tap-post"])
    assert debug_test_skips_media("post-go-home", registry["post-go-home"])
    assert not debug_test_skips_media("tap-plus", registry["tap-plus"])
    assert not debug_test_skips_media("prep-home", registry["prep-home"])


@pytest.mark.asyncio
async def test_run_debug_test_skip_media() -> None:
    app = MagicMock()
    app.db.log_activity = AsyncMock()
    result = await run_debug_test(
        app,
        "phone-1",
        "flow:006:clear-album",
        skip_media=True,
    )
    assert result["success"] is True
    assert result["skipped"] is True
    assert "Skipped (UI-only)" in result["message"]
    app.db.log_activity.assert_awaited_once()

def test_list_debug_tests() -> None:
    registry = get_debug_registry()
    flow_tests = list_debug_tests()
    all_tests = list_debug_tests("all")
    assert len(flow_tests) == 147
    assert len(all_tests) == len(registry)
    assert flow_tests[0]["id"].startswith("flow:001:")
    assert flow_tests[0]["test_id"] == "tap-lock_screen"
    assert flow_tests[0]["label"].startswith("A. ")
    assert all(t["label"] for t in flow_tests)


def test_template_taps_auto_registered_from_screen_states() -> None:
    registry = get_debug_registry()
    assert "tap-tiktok" in registry
    assert registry["tap-tiktok"]["kind"] == "tap_xy"
    assert registry["tap-tiktok"]["x"] == 507
    assert registry["tap-tiktok"]["y"] == 1011


def test_debug_tests_have_required_fields() -> None:
    for test_id, spec in get_debug_registry().items():
        assert spec["label"]
        assert spec["offline_hint"]
        kind = spec.get("kind", "tap")
        if kind == "tap":
            assert spec["detection"]
            assert spec["hint"]
            assert test_id.startswith("tap-") or test_id.startswith("end-tap-") or test_id.startswith("valcoin-prep-tap-")
        elif kind == "upload_gallery":
            assert test_id in {
                "upload-gallery",
                "slideshow-upload-gallery",
                "valcoin-prep-upload-gallery",
            }
        elif kind == "slideshow_generate":
            assert spec.get("brand") in {"labely", "valcoin"}
            assert spec["hint"]
        elif kind == "album_clear":
            assert test_id in {"clear-album", "valcoin-prep-clear-album"}
        elif kind == "album_list":
            assert test_id == "list-album"
        elif kind == "tap_ocr":
            assert spec["texts"]
            assert spec["hint"]
        elif kind == "open_photos_spotlight":
            assert test_id == "open-photos-spotlight"
        elif kind == "detect":
            assert spec["detection"]
            assert spec["hint"]
        elif kind == "detect_ocr":
            assert spec["texts"]
            assert spec["hint"]
        elif kind == "final_caption_production":
            assert spec.get("post_num")
        elif kind == "media_then_next":
            assert "x" in spec and "y" in spec
            assert spec.get("texts")
            assert spec["hint"]
        elif kind == "gallery_then_recents":
            assert "x" in spec and "y" in spec
            assert spec.get("texts")
            assert spec.get("fallback_tap")
            assert spec["hint"]
        elif kind == "hvitserk_after_favorites":
            assert spec.get("texts")
            assert spec["hint"]
        elif kind == "tiktok_popup_scan":
            assert spec["hint"]
        elif kind == "home":
            assert test_id in {"prep-home", "post-go-home"}
        elif kind == "vpn_shortcut":
            assert spec.get("mode") in {"on", "off", "toggle", "open"}
            assert spec["hint"]
        elif kind == "vpn_off_before_album":
            assert test_id == "prep-vpn-off-before-album"
            assert spec["hint"]
        elif kind == "account_switch_step":
            assert spec["step"]
            assert spec["hint"]


def test_list_account_switch_debug_tests() -> None:
    tests = list_debug_tests("account_switch")
    ids = [t["id"] for t in tests]
    assert ids[:6] == [
        "account-tap-profile-tab",
        "account-switcher-tap-primary",
        "account-switcher-tap-alt",
        "account-switcher-verify-handle",
        "account-pick-handle",
        "account-tap-home-tab",
    ]
    assert ids[-3:] == [
        "account-open-switcher",
        "account-ensure-current",
        "account-ensure-full",
    ]
    assert "account-switcher-tap-primary" in ids
    assert "account-switcher-tap-alt" in ids
    assert "account-switcher-verify-handle" in ids
    assert "account-dismiss-security-checkup" in ids
    assert "account-dismiss-add-phone" in ids
    assert all(t["group"] == "account_switch" for t in tests)
    assert tests[0]["label"].startswith("1. ")


def test_security_checkup_debug_tests_registered() -> None:
    registry = get_debug_registry()
    for test_id in ("post-dismiss-security-checkup", "account-dismiss-security-checkup"):
        spec = registry[test_id]
        assert spec["kind"] == "tap_xy"
        assert spec["x"] == 570
        assert spec["y"] == 501


def test_add_phone_debug_tests_registered() -> None:
    registry = get_debug_registry()
    for test_id in ("post-dismiss-add-phone", "account-dismiss-add-phone"):
        spec = registry[test_id]
        assert spec["kind"] == "tap_xy"
        assert spec["x"] == 564
        assert spec["y"] == 260


def test_permission_watcher_run_debug_registered() -> None:
    registry = get_debug_registry()
    assert registry["run-permission-watcher"]["kind"] == "permission_watcher_run"
    assert registry["account-run-permission-watcher"]["kind"] == "permission_watcher_run"


def test_list_slideshow_debug_tests() -> None:
    tests = list_debug_tests("slideshow")
    ids = {t["id"] for t in tests}
    assert "slideshow-generate-labely" in ids
    assert "slideshow-generate-valcoin" in ids
    assert "slideshow-upload-gallery" in ids
    assert all(t["group"] == "slideshow" for t in tests)


def test_list_valcoin_prep_debug_tests() -> None:
    tests = list_debug_tests("valcoin_prep")
    ids = {t["id"] for t in tests}
    assert "valcoin-prep-vpn-shortcut-off" in ids
    assert "valcoin-prep-clear-album" in ids
    assert all(t["group"] == "valcoin_prep" for t in tests)


def test_full_flow_debug_steps_ordered() -> None:
    tests = list_debug_tests("flow")
    assert len(tests) == len(FLOW_DEBUG_STEPS)
    assert tests[0]["test_id"] == FLOW_DEBUG_STEPS[0][1]
    assert tests[-1]["test_id"] == FLOW_DEBUG_STEPS[-1][1]
    assert tests[0]["label"].startswith("A. ")


def test_upload_gallery_is_first_in_all_group() -> None:
    tests = list_debug_tests("all")
    assert tests[0]["id"] == "upload-gallery"
    assert "prep-kill-apps" in {t["id"] for t in tests[:6]}


def test_manual_tests_override_template_ids() -> None:
    assert "upload-gallery" in MANUAL_DEBUG_TESTS
