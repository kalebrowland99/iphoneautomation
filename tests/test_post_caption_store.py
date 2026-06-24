"""Tests for per-post onscreen and final caption storage."""

from imouse_farm.post.post_caption_store import (
    get_onscreen_text,
    set_final_caption,
    set_onscreen_text,
)


def test_onscreen_text_is_per_post() -> None:
    device_id = "test-device-per-post-onscreen"
    set_onscreen_text(device_id, 1, "overlay one")
    set_onscreen_text(device_id, 2, "overlay two\nline two")
    set_onscreen_text(device_id, 3, "overlay three")
    assert get_onscreen_text(device_id, 1) == "overlay one"
    assert get_onscreen_text(device_id, 2) == "overlay two\nline two"
    assert get_onscreen_text(device_id, 3) == "overlay three"


def test_final_captions_stay_per_post() -> None:
    device_id = "test-device-final-split"
    set_onscreen_text(device_id, 1, "Overlay 1")
    set_onscreen_text(device_id, 2, "Overlay 2")
    set_final_caption(device_id, 1, "Caption one")
    set_final_caption(device_id, 2, "Caption two")
    assert get_onscreen_text(device_id, 2) == "Overlay 2"
