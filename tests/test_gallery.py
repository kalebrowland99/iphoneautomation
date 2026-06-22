"""Tests for gallery folder resolution."""

from pathlib import Path

from imouse_farm.utils.gallery import list_media_files, phone_gallery_folder


def test_phone_gallery_folder_uses_slot() -> None:
    path = phone_gallery_folder("gallery", "12", "iPhone 12")
    assert path.name == "12"
    assert path.parent.name == "gallery"
    assert path.is_absolute()


def test_list_media_files_returns_absolute_paths() -> None:
    folder = Path(__file__).parent / "_fixtures" / "gallery_sample"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "a.mp4").write_bytes(b"x")
    (folder / "b.txt").write_text("nope")
    files = list_media_files(folder, [".mp4"])
    assert any(f.endswith("a.mp4") for f in files)
    assert not any(f.endswith("b.txt") for f in files)
    assert all(Path(f).is_absolute() for f in files)
