"""Tests for multi-sample template scan helpers."""

from imouse_farm.vision.template_scan import (
    ocr_rect_from_pct,
    pick_detection_hit,
    stronger_hit,
)


def test_ocr_rect_from_pct() -> None:
    rect = ocr_rect_from_pct(400, 800, [0.5, 0.0, 1.0, 0.25])
    assert rect == [200, 0, 400, 200]


def test_pick_detection_hit_uses_fallback() -> None:
    detections = {"vpntoggle": {"x": 1, "y": 2, "confidence": 0.6}}
    assert pick_detection_hit(detections, "missing") is None


def test_stronger_hit_prefers_higher_confidence() -> None:
    a = {"x": 1, "y": 2, "confidence": 0.4}
    b = {"x": 3, "y": 4, "confidence": 0.7}
    winner = stronger_hit(a, b)
    assert winner is not None
    assert winner["confidence"] == 0.7
