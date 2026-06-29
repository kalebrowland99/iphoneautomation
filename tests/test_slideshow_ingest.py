"""Tests for slideshow gallery ingest."""

from pathlib import Path

import pytest

from imouse_farm.integrations.slideshow_ingest import (
    clear_slot_media,
    normalize_slot,
    save_bytes_to_slot,
    slot_gallery_dir,
)


def test_normalize_slot() -> None:
    assert normalize_slot("12") == "12"
    assert normalize_slot(3) == "3"
    with pytest.raises(ValueError):
        normalize_slot("iPhone 12")


def test_save_and_clear_slot(tmp_path: Path) -> None:
    base = str(tmp_path / "gallery")
    save_bytes_to_slot(b"video-a", base_directory=base, slot="5", filename="a.mp4")
    save_bytes_to_slot(b"video-b", base_directory=base, slot="5", filename="b.mp4")
    folder = slot_gallery_dir(base, "5")
    assert (folder / "a.mp4").is_file()
    assert (folder / "b.mp4").is_file()
    removed = clear_slot_media(base, "5", [".mp4"])
    assert removed == 2
    assert list(folder.iterdir()) == []
