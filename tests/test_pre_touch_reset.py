"""Tests for TikTok pre-touch mouse reset hook."""

from imouse_farm.actions.pre_touch_reset import needs_pre_touch_reset
from imouse_farm.config.models import ActionType


def test_pre_touch_reset_for_tiktok_tap() -> None:
    assert needs_pre_touch_reset("tiktok_post", ActionType.TAP) is True


def test_pre_touch_reset_for_tiktok_text_input() -> None:
    assert needs_pre_touch_reset("tiktok_post", ActionType.TEXT_INPUT) is True


def test_pre_touch_reset_skips_non_tiktok() -> None:
    assert needs_pre_touch_reset("warmup", ActionType.TAP) is False


def test_pre_touch_reset_skips_mouse_reset_action() -> None:
    assert needs_pre_touch_reset("tiktok_post", ActionType.MOUSE_RESET) is False


def test_pre_touch_reset_skips_home() -> None:
    assert needs_pre_touch_reset("tiktok_post", ActionType.HOME) is False
