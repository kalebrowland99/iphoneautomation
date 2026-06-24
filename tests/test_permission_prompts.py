"""Tests for iOS permission / delete dialog label filtering."""

from imouse_farm.actions.permission_prompts import (
    delete_match_is_stable,
    filter_delete_confirm_matches,
    is_delete_confirm_label,
    is_delete_distractor_label,
    pick_delete_confirm_match,
)


def test_delete_label_accepts_real_delete_buttons() -> None:
    assert is_delete_confirm_label("Delete 12 Items")
    assert is_delete_confirm_label("Delete Photos")
    assert is_delete_confirm_label("Delete")


def test_delete_label_rejects_show_all() -> None:
    assert not is_delete_confirm_label("Show All")
    assert not is_delete_confirm_label("See All Photos")


def test_delete_label_rejects_cancel_variants() -> None:
    assert not is_delete_confirm_label("Don't Delete")
    assert not is_delete_confirm_label("Cancel")


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
