"""Tests for TikTok feed scroll coordinate helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from imouse_farm.workflows.feed_scroll import (
    random_center_double_tap_coords,
    random_feed_swipe_coords,
    screen_dimensions,
    scroll_tiktok_feed,
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


@pytest.mark.asyncio
async def test_scroll_tiktok_feed_short_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    from imouse_farm.workflows import feed_scroll

    taps: list[tuple[int, int]] = []
    swipes = {"n": 0}

    class _Ctrl:
        async def tap(self, _device_id: str, x: int, y: int) -> bool:
            taps.append((x, y))
            return True

        async def swipe(self, *_a: object, **_k: object) -> bool:
            swipes["n"] += 1
            return True

        async def ocr_on_device(self, _device_id: str) -> str:
            return ""

    class _Dev:
        device_id = "dev-1"
        user_name = "1"
        screen_width = 406
        screen_height = 720

    monkeypatch.setattr(feed_scroll.random, "uniform", lambda _a, _b: 0.0)
    monkeypatch.setattr(feed_scroll.random, "random", lambda: 1.0)  # skip long watch
    monkeypatch.setattr(
        feed_scroll.random,
        "expovariate",
        lambda _rate: 0.05,
    )
    monkeypatch.setattr(feed_scroll.random, "randint", lambda a, _b: a)
    monkeypatch.setattr(feed_scroll.asyncio, "sleep", AsyncMock())

    await scroll_tiktok_feed(
        _Ctrl(),
        _Dev(),
        duration_seconds=0.2,
        home_tab_x=60,
        home_tab_y=1041,
        swipe_delay_min_seconds=0.01,
        swipe_delay_max_seconds=0.05,
        swipe_delay_mean_seconds=0.02,
        swipe_delay_long_watch_probability=0.0,
        tap_home_first=True,
        enable_double_tap=False,
    )

    assert taps and taps[0] == (60, 1041)
    assert swipes["n"] >= 1
