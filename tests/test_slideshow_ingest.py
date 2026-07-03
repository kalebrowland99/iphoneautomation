"""Tests for slideshow gallery ingest."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from imouse_farm.integrations.slideshow_ingest import (
    SlideshowVideoRejected,
    clear_all_slot_media,
    clear_slot_media,
    normalize_slot,
    save_bytes_to_slot,
    slot_gallery_dir,
    slot_gallery_status,
    validate_slideshow_video,
)


def test_normalize_slot() -> None:
    assert normalize_slot("12") == "12"
    assert normalize_slot(3) == "3"
    with pytest.raises(ValueError):
        normalize_slot("iPhone 12")


def test_save_and_clear_slot(tmp_path: Path) -> None:
    base = str(tmp_path / "gallery")
    save_bytes_to_slot(b"video-a", base_directory=base, slot="5", filename="a.mp4", validate=False)
    save_bytes_to_slot(b"video-b", base_directory=base, slot="5", filename="b.mp4", validate=False)
    folder = slot_gallery_dir(base, "5")
    assert (folder / "a.mp4").is_file()
    assert (folder / "b.mp4").is_file()
    removed = clear_slot_media(base, "5", [".mp4"])
    assert removed == 2
    assert list(folder.iterdir()) == []


def test_clear_all_slot_media(tmp_path: Path) -> None:
    base = str(tmp_path / "gallery")
    save_bytes_to_slot(b"a", base_directory=base, slot="1", filename="a.mp4", validate=False, brand="labely")
    save_bytes_to_slot(b"b", base_directory=base, slot="1", filename="b.mp4", validate=False, brand="valcoin")
    save_bytes_to_slot(b"c", base_directory=base, slot="2", filename="c.mp4", validate=False, brand="labely")

    removed = clear_all_slot_media(base, [".mp4"], farm_slots=2)

    assert removed == 3
    assert list(slot_gallery_dir(base, "1", brand="labely").iterdir()) == []
    assert list(slot_gallery_dir(base, "1", brand="valcoin").iterdir()) == []
    assert list(slot_gallery_dir(base, "2", brand="labely").iterdir()) == []


def _write_test_video(path: Path, *, luma: float, frames: int = 120) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    value = int(max(0, min(255, luma)))
    frame = np.full((480, 640, 3), value, dtype=np.uint8)
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        10.0,
        (640, 480),
    )
    try:
        for _ in range(frames):
            writer.write(frame)
    finally:
        writer.release()


def _write_multisegment_video(path: Path, segment_lumas: list[float], frames_per_segment: int = 40) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        10.0,
        (640, 480),
    )
    try:
        for luma in segment_lumas:
            value = int(max(0, min(255, luma)))
            frame = np.full((480, 640, 3), value, dtype=np.uint8)
            for _ in range(frames_per_segment):
                writer.write(frame)
    finally:
        writer.release()


def test_validate_slideshow_video_rejects_black(tmp_path: Path) -> None:
    path = tmp_path / "black.mp4"
    _write_test_video(path, luma=5.0)
    ok, reason = validate_slideshow_video(path)
    assert not ok
    assert "blank slide" in reason or "blank video" in reason


def test_save_bytes_rejects_black_video(tmp_path: Path) -> None:
    path = tmp_path / "black.mp4"
    _write_test_video(path, luma=5.0)
    data = path.read_bytes()
    base = str(tmp_path / "gallery")
    with pytest.raises(SlideshowVideoRejected, match="blank"):
        save_bytes_to_slot(data, base_directory=base, slot="2", filename="bad.mp4")
    folder = slot_gallery_dir(base, "2")
    assert not (folder / "bad.mp4").exists()


def test_slot_gallery_status_prunes_invalid(tmp_path: Path) -> None:
    base = str(tmp_path / "gallery")
    folder = slot_gallery_dir(base, "7")
    _write_test_video(folder / "bad.mp4", luma=5.0)
    _write_test_video(folder / "good.mp4", luma=180.0)
    ok, issues = slot_gallery_status(base, "7", [".mp4"], min_count=1, prune_invalid=True)
    assert ok
    assert not issues
    assert not (folder / "bad.mp4").exists()
    assert (folder / "good.mp4").exists()


def test_slot_gallery_status_missing_valid(tmp_path: Path) -> None:
    base = str(tmp_path / "gallery")
    folder = slot_gallery_dir(base, "8")
    _write_test_video(folder / "bad.mp4", luma=5.0)
    ok, issues = slot_gallery_status(base, "8", [".mp4"], min_count=1, prune_invalid=True)
    assert not ok
    assert any("need 1 valid" in issue for issue in issues)


def test_validate_rejects_blank_first_slide_in_multisegment_video(tmp_path: Path) -> None:
    path = tmp_path / "mixed.mp4"
    _write_multisegment_video(path, [5.0, 180.0, 180.0])
    ok, reason = validate_slideshow_video(path, expected_slides=3)
    assert not ok
    assert "blank slide 1" in reason


def test_validate_rejects_blank_middle_slide(tmp_path: Path) -> None:
    path = tmp_path / "mixed.mp4"
    _write_multisegment_video(path, [180.0, 5.0, 180.0])
    ok, reason = validate_slideshow_video(path, expected_slides=3)
    assert not ok
    assert "blank slide" in reason


def test_validate_accepts_all_good_slides(tmp_path: Path) -> None:
    path = tmp_path / "mixed.mp4"
    _write_multisegment_video(path, [180.0, 190.0, 200.0])
    ok, reason = validate_slideshow_video(path, expected_slides=3)
    assert ok
    assert reason == ""
