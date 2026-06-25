"""Tests for iOS permission / delete dialog label filtering."""

from imouse_farm.actions.permission_prompts import (
    delete_match_is_stable,
    delete_sheet_is_visible,
    filter_delete_confirm_matches,
    is_delete_confirm_label,
    is_delete_distractor_label,
    pick_delete_confirm_match,
    resolve_delete_tap,
)


def test_delete_label_accepts_real_delete_buttons() -> None:
    assert is_delete_confirm_label("Delete 12 Items")
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


def test_is_deny_permission_label_rejects_dont_delete() -> None:
    from imouse_farm.actions.permission_prompts import is_deny_permission_label

    assert not is_deny_permission_label("Don't Delete")
    assert not is_deny_permission_label("Delete 12 Items")
    assert is_deny_permission_label("Don't Allow")
    assert is_deny_permission_label("Ask App Not to Track")


def test_photo_delete_sheet_skips_permission_watcher_logic() -> None:
    from imouse_farm.actions.permission_prompts import is_photo_delete_sheet_text

    assert is_photo_delete_sheet_text("Delete 12 Photos from Library\nDon't Delete\nDelete")
    assert is_photo_delete_sheet_text("Delete Always\nRemove from library")
    assert not is_photo_delete_sheet_text("TikTok Would Like to Access Your Photos")


def test_distractor_labels_include_show_all() -> None:
    assert is_delete_distractor_label("Show All")
    assert not is_delete_distractor_label("Delete 12 Items")


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


def test_resolve_delete_tap_no_blind_fallback_on_show_all() -> None:
    matches = [{"text": "Show All", "x": 200, "y": 650, "confidence": 0.95}]
    assert resolve_delete_tap(matches) is None


def test_resolve_delete_tap_infers_below_dont_delete() -> None:
    matches = [{"text": "Don't Delete", "x": 180, "y": 600, "confidence": 0.95}]
    result = resolve_delete_tap(matches)
    assert result == ("fallback", (180, 665))


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
