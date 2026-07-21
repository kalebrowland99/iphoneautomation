"""Tests for Run-debug sample gallery seeding."""

from __future__ import annotations

from pathlib import Path

from imouse_farm.utils.debug_sample_media import (
    ensure_debug_sample_mp4,
    seed_debug_gallery_slots,
)
from imouse_farm.utils.gallery import list_media_files


def test_ensure_debug_sample_mp4_creates_file(tmp_path: Path, monkeypatch) -> None:
    sample = tmp_path / "assets" / "debug_sample.mp4"
    monkeypatch.setattr(
        "imouse_farm.utils.debug_sample_media.SAMPLE_PATH",
        sample,
    )
    path = ensure_debug_sample_mp4()
    assert path == sample
    assert path.is_file()
    assert path.stat().st_size > 1024
    # Second call reuses existing file
    again = ensure_debug_sample_mp4()
    assert again == path


def test_seed_debug_gallery_fills_empty_slot(tmp_path: Path, monkeypatch) -> None:
    sample = tmp_path / "assets" / "debug_sample.mp4"
    monkeypatch.setattr(
        "imouse_farm.utils.debug_sample_media.SAMPLE_PATH",
        sample,
    )
    gallery = tmp_path / "gallery"
    result = seed_debug_gallery_slots(str(gallery), [1, "2"], brand="labely", count=3)
    assert result["slots_seeded"] == 2
    for slot in ("1", "2"):
        folder = gallery / slot / "labely"
        files = list_media_files(folder, [".mp4"])
        assert len(files) == 3


def test_seed_debug_gallery_skips_when_full(tmp_path: Path, monkeypatch) -> None:
    sample = tmp_path / "assets" / "debug_sample.mp4"
    monkeypatch.setattr(
        "imouse_farm.utils.debug_sample_media.SAMPLE_PATH",
        sample,
    )
    ensure_debug_sample_mp4()
    gallery = tmp_path / "gallery"
    dest = gallery / "5" / "labely"
    dest.mkdir(parents=True)
    for i in range(3):
        (dest / f"existing-{i}.mp4").write_bytes(b"x" * 2048)
    result = seed_debug_gallery_slots(str(gallery), [5], brand="labely", count=3)
    assert result["slots_seeded"] == 0
    assert len(list_media_files(dest, [".mp4"])) == 3
