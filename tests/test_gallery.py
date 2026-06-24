"""Tests for gallery folder resolution."""

from pathlib import Path

from imouse_farm.utils.gallery import (
    list_media_files,
    list_media_files_for_upload,
    list_media_stems_for_posts,
    phone_gallery_folder,
)


def test_phone_gallery_folder_uses_slot() -> None:
    path = phone_gallery_folder("gallery", "12", "iPhone 12")
    assert path.name == "12"
    assert path.parent.name == "gallery"
    assert path.is_absolute()


def test_list_media_files_returns_absolute_paths(tmp_path: Path) -> None:
    folder = tmp_path / "gallery_sample"
    folder.mkdir(parents=True)
    (folder / "a.mp4").write_bytes(b"x")
    (folder / "b.txt").write_text("nope")
    files = list_media_files(folder, [".mp4"])
    assert any(f.endswith("a.mp4") for f in files)
    assert not any(f.endswith("b.txt") for f in files)
    assert all(Path(f).is_absolute() for f in files)


def test_list_media_files_natural_order(tmp_path: Path) -> None:
    folder = tmp_path / "slot"
    folder.mkdir()
    for name in ("video10.mp4", "video2.mp4", "video1.mp4"):
        (folder / name).write_bytes(b"x")
    files = list_media_files(folder, [".mp4"])
    names = [Path(f).name for f in files]
    assert names == ["video1.mp4", "video2.mp4", "video10.mp4"]


def test_list_media_stems_for_posts(tmp_path: Path) -> None:
    folder = tmp_path / "slot"
    folder.mkdir()
    (folder / "clip_a.mp4").write_bytes(b"a")
    (folder / "clip_b.mp4").write_bytes(b"b")
    stems = list_media_stems_for_posts(folder, [".mp4"], post_count=3)
    assert stems == ["clip_a", "clip_b", ""]


def test_list_media_files_for_upload_reverses_post_order(tmp_path: Path) -> None:
    folder = tmp_path / "slot"
    folder.mkdir()
    for name in ("video1.mp4", "video2.mp4", "video3.mp4"):
        (folder / name).write_bytes(b"x")
    post_order = [Path(f).name for f in list_media_files(folder, [".mp4"])]
    upload_order = [Path(f).name for f in list_media_files_for_upload(folder, [".mp4"])]
    assert post_order == ["video1.mp4", "video2.mp4", "video3.mp4"]
    assert upload_order == ["video3.mp4", "video2.mp4", "video1.mp4"]
