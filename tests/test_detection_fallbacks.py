"""Tests for template detection fallbacks."""

from imouse_farm.vision.fallbacks import (
    apply_detection_fallbacks,
    apply_exclusive_detections,
    apply_tap_offsets,
    detection_satisfied,
    expand_template_names,
    resolve_template_state_fallback,
)


def test_apply_exclusive_detections_keeps_higher_confidence() -> None:
    detections = apply_exclusive_detections(
        {
            "bluetoggle": {"x": 1, "y": 2, "confidence": 0.55},
            "vpntoggle": {"x": 3, "y": 4, "confidence": 0.82},
        }
    )
    assert "vpntoggle" in detections
    assert "bluetoggle" not in detections


def test_apply_exclusive_detections_prefers_vpntoggle_on_tie() -> None:
    detections = apply_exclusive_detections(
        {
            "bluetoggle": {"x": 1, "y": 2, "confidence": 0.70},
            "vpntoggle": {"x": 3, "y": 4, "confidence": 0.70},
        }
    )
    assert list(detections) == ["vpntoggle"]


def test_expand_template_names_continuearrow_includes_post() -> None:
    names = expand_template_names(["continuearrow"])
    assert "continuearrow" in names
    assert "post" in names


def test_apply_detection_fallbacks_maps_post_to_continuearrow() -> None:
    detections = apply_detection_fallbacks(
        {"post": {"x": 350, "y": 650, "confidence": 0.55, "matched_via": "post"}}
    )
    assert "continuearrow" in detections
    assert detections["continuearrow"]["matched_via"] == "post"


def test_detection_satisfied_via_fallback() -> None:
    detections = apply_detection_fallbacks(
        {"post": {"x": 1, "y": 2, "confidence": 0.5}}
    )
    assert detection_satisfied(detections, "continuearrow")


def test_apply_tap_offsets_shifts_gallery() -> None:
    detections = apply_tap_offsets(
        {"gallery": {"x": 39, "y": 20, "confidence": 0.5}},
        lambda name: (-29, 0) if name == "gallery" else (0, 0),
    )
    assert detections["gallery"]["x"] == 10
    assert detections["gallery"]["y"] == 20


def test_apply_detection_fallbacks_passthrough() -> None:
    detections = apply_detection_fallbacks(
        {"gallery": {"x": 10, "y": 20, "confidence": 0.5}}
    )
    assert detections["gallery"]["x"] == 10


def test_resolve_template_state_fallback_ignores_weak_vpntoggle() -> None:
    state_map = [
        {"template": "bluetoggle", "state": "ACTIVE", "min_confidence": 0.45},
        {"template": "vpntoggle", "state": "WAITING", "min_confidence": 0.55},
    ]
    winner, conf = resolve_template_state_fallback(
        {"vpntoggle": {"x": 1, "y": 2, "confidence": 0.48}},
        state_map,
    )
    assert winner is None
    assert conf == 0.0


def test_resolve_template_state_fallback_prefers_bluetoggle() -> None:
    state_map = [
        {"template": "bluetoggle", "state": "ACTIVE", "min_confidence": 0.45},
        {"template": "vpntoggle", "state": "WAITING", "min_confidence": 0.55},
    ]
    winner, conf = resolve_template_state_fallback(
        {
            "bluetoggle": {"x": 1, "y": 2, "confidence": 0.62},
            "vpntoggle": {"x": 3, "y": 4, "confidence": 0.58},
        },
        state_map,
    )
    assert winner == "bluetoggle"
    assert conf == 0.62


def test_resolve_template_state_fallback_vpntoggle_off() -> None:
    state_map = [
        {"template": "bluetoggle", "state": "ACTIVE", "min_confidence": 0.45},
        {"template": "vpntoggle", "state": "WAITING", "min_confidence": 0.55},
    ]
    winner, conf = resolve_template_state_fallback(
        {"vpntoggle": {"x": 3, "y": 4, "confidence": 0.68}},
        state_map,
    )
    assert winner == "vpntoggle"
    assert conf == 0.68
