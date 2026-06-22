"""Tests for dashboard debug test registry."""

from imouse_farm.dashboard.test_actions import (
    MANUAL_DEBUG_TESTS,
    get_debug_registry,
    list_debug_tests,
)


def test_list_debug_tests() -> None:
    registry = get_debug_registry()
    tests = list_debug_tests()
    assert len(tests) == len(registry)
    ids = {t["id"] for t in tests}
    assert "tap-vpntoggle" in ids
    assert "tap-ocr-allow" in ids
    assert all(t["label"] for t in tests)


def test_template_taps_auto_registered_from_screen_states() -> None:
    registry = get_debug_registry()
    assert "tap-tiktok" in registry
    assert registry["tap-tiktok"]["detection"] == "tiktok"


def test_debug_tests_have_required_fields() -> None:
    for test_id, spec in get_debug_registry().items():
        assert spec["label"]
        assert spec["offline_hint"]
        kind = spec.get("kind", "tap")
        if kind == "tap":
            assert spec["detection"]
            assert spec["hint"]
            assert test_id.startswith("tap-")
        elif kind == "upload_gallery":
            assert test_id == "upload-gallery"
        elif kind == "album_clear":
            assert test_id == "clear-album"
        elif kind == "album_list":
            assert test_id == "list-album"
        elif kind == "tap_ocr":
            assert spec["texts"]
            assert spec["hint"]
        elif kind == "open_photos_spotlight":
            assert test_id == "open-photos-spotlight"


def test_upload_gallery_is_first_debug_test() -> None:
    tests = list_debug_tests()
    assert tests[0]["id"] == "upload-gallery"
    assert tests[1]["id"] == "clear-album"


def test_manual_tests_override_template_ids() -> None:
    assert "upload-gallery" in MANUAL_DEBUG_TESTS
