"""Tests for TikTok feed scroll coordinate helpers."""

from __future__ import annotations

from imouse_farm.workflows.feed_scroll import (
    random_center_double_tap_coords,
    random_feed_swipe_coords,
    screen_dimensions,
)


class _Device:
    screen_width = 390
    screen_height = 844


def test_screen_dimensions_from_device() -> None:
    sw, sh = screen_dimensions(_Device())
    assert sw == 390
    assert sh == 844


def test_screen_dimensions_defaults() -> None:
    sw, sh = screen_dimensions(None)
    assert sw == 406
    assert sh == 720


def test_random_feed_swipe_coords_in_bounds() -> None:
    sw, sh = 406, 720
    for _ in range(50):
        sx, sy, ex, ey = random_feed_swipe_coords(sw, sh)
        assert 5 <= sx <= sw - 5
        assert 5 <= sy <= sh - 5
        assert 5 <= ex <= sw - 5
        assert 5 <= ey < sy


def test_random_center_double_tap_in_center_band() -> None:
    sw, sh = 406, 720
    for _ in range(50):
        x, y = random_center_double_tap_coords(sw, sh)
        assert int(sw * 0.30) <= x <= int(sw * 0.70)
        assert int(sh * 0.30) <= y <= int(sh * 0.70)
