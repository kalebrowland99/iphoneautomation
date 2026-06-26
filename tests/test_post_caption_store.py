"""Tests for per-post onscreen and final caption storage."""

from pathlib import Path

import pytest

import imouse_farm.post.post_caption_store as store
from imouse_farm.post.post_caption_store import (
    GALLERY_ITEM_COORDS,
    clear_all_post_texts,
    device_storage_key,
    get_gallery_coords,
    get_onscreen_text,
    gallery_slot_for_post,
    media_index_for_post,
    post_media_stem,
    set_final_caption,
    set_onscreen_text,
)


@pytest.fixture(autouse=True)
def isolated_post_text_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "post_texts.json"
    monkeypatch.setattr(store, "POST_TEXTS_PATH", path)
    monkeypatch.setattr(store, "_store", {})


def test_onscreen_text_is_per_post() -> None:
    device_key = "test-device-per-post-onscreen"
    set_onscreen_text(device_key, 1, "overlay one")
    set_onscreen_text(device_key, 2, "overlay two\nline two")
    set_onscreen_text(device_key, 3, "overlay three")
    assert get_onscreen_text(device_key, 1) == "overlay one"
    assert get_onscreen_text(device_key, 2) == "overlay two\nline two"
    assert get_onscreen_text(device_key, 3) == "overlay three"


def test_final_captions_stay_per_post() -> None:
    device_key = "test-device-final-split"
    set_onscreen_text(device_key, 1, "Overlay 1")
    set_onscreen_text(device_key, 2, "Overlay 2")
    set_final_caption(device_key, 1, "Caption one")
    set_final_caption(device_key, 2, "Caption two")
    assert get_onscreen_text(device_key, 2) == "Overlay 2"


def test_gallery_coords_map_posts_to_recents_right_to_left() -> None:
    assert gallery_slot_for_post(1) == 3
    assert gallery_slot_for_post(2) == 2
    assert gallery_slot_for_post(3) == 1
    assert get_gallery_coords(1) == GALLERY_ITEM_COORDS[3]
    assert get_gallery_coords(2) == GALLERY_ITEM_COORDS[2]
    assert get_gallery_coords(3) == GALLERY_ITEM_COORDS[1]


def test_post_media_stem_maps_post_one_to_third_file() -> None:
    stems = ["video1", "video2", "video3"]
    assert media_index_for_post(1) == 2
    assert media_index_for_post(2) == 1
    assert media_index_for_post(3) == 0
    assert post_media_stem(stems, 1) == "video3"
    assert post_media_stem(stems, 2) == "video2"
    assert post_media_stem(stems, 3) == "video1"


def test_device_storage_key_uses_farm_slot() -> None:
    assert device_storage_key("uuid-123", "12") == "slot:12"
    assert device_storage_key("uuid-123", "") == "uuid-123"


def test_clear_all_post_texts() -> None:
    device_key = "test-device-clear-all"
    set_onscreen_text(device_key, 1, "keep?")
    set_final_caption(device_key, 2, "caption")
    clear_all_post_texts(device_key)
    assert get_onscreen_text(device_key, 1) == ""
    assert get_onscreen_text(device_key, 2) == ""
    assert get_onscreen_text(device_key, 3) == ""


def test_post_texts_persist_to_disk(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "post_texts.json"
    monkeypatch.setattr(store, "POST_TEXTS_PATH", path)
    monkeypatch.setattr(store, "_store", {})
    device_key = "slot:99"
    store.set_onscreen_text(device_key, 1, "saved overlay")
    store.set_final_caption(device_key, 1, "saved caption")
    store._load_store()
    assert store.get_onscreen_text(device_key, 1) == "saved overlay"
    assert store.get_final_caption(device_key, 1) == "saved caption"


def test_validate_post_texts_requires_all_fields() -> None:
    from imouse_farm.post.post_caption_store import validate_post_texts

    device_key = "test-validate-post-texts"
    clear_all_post_texts(device_key)
    errors = validate_post_texts(device_key, from_post=1)
    assert len(errors) == 6

    set_onscreen_text(device_key, 1, "overlay")
    set_final_caption(device_key, 1, "caption")
    set_onscreen_text(device_key, 2, "overlay 2")
    set_final_caption(device_key, 2, "caption 2")
    set_onscreen_text(device_key, 3, "overlay 3")
    set_final_caption(device_key, 3, "caption 3")
    assert validate_post_texts(device_key, from_post=1) == []


def test_validate_post_texts_from_post_two() -> None:
    from imouse_farm.post.post_caption_store import validate_post_texts

    device_key = "test-validate-from-post-2"
    clear_all_post_texts(device_key)
    set_onscreen_text(device_key, 1, "only post 1")
    set_final_caption(device_key, 1, "only post 1")
    assert validate_post_texts(device_key, from_post=2) != []
    set_onscreen_text(device_key, 2, "p2")
    set_final_caption(device_key, 2, "p2")
    set_onscreen_text(device_key, 3, "p3")
    set_final_caption(device_key, 3, "p3")
    assert validate_post_texts(device_key, from_post=2) == []
