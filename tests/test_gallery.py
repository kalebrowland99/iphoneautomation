"""Tests for gallery folder resolution."""

from pathlib import Path

from imouse_farm.utils.gallery import (
    list_media_files,
    list_media_stems_for_posts,
    phone_gallery_folder,
    slots_with_media,
)


def test_slots_with_media(tmp_path: Path) -> None:
    base = tmp_path / "gallery"
    slot6 = base / "6" / "labely"
    slot6.mkdir(parents=True)
    slot99 = base / "99" / "labely"
    slot99.mkdir(parents=True)
    (slot99 / "output.mp4").write_bytes(b"x")
    found = slots_with_media(str(base), [".mp4"], brand="labely")
    assert len(found) == 1
    assert found[0]["slot"] == "99"
    assert found[0]["file_count"] == 1


def test_phone_gallery_folder_default_brand_target(tmp_path: Path) -> None:
    path = phone_gallery_folder(str(tmp_path / "gallery"), "12", "iPhone 12", brand="labely")
    assert path.name == "labely"
    assert path.parent.name == "12"
    assert path.is_absolute()


def test_phone_gallery_folder_brand_subfolder(tmp_path: Path) -> None:
    slot = tmp_path / "gallery" / "5"
    branded = slot / "valcoin"
    branded.mkdir(parents=True)
    (branded / "a.mp4").write_bytes(b"x")
    path = phone_gallery_folder(str(tmp_path / "gallery"), "5", brand="valcoin")
    assert path == branded.resolve()


def test_phone_gallery_folder_legacy_labely_flat(tmp_path: Path) -> None:
    slot = tmp_path / "gallery" / "7"
    slot.mkdir(parents=True)
    (slot / "a.mp4").write_bytes(b"x")
    path = phone_gallery_folder(str(tmp_path / "gallery"), "7", brand="labely")
    assert path == slot.resolve()


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


def test_list_media_files_missing_folder(tmp_path: Path) -> None:
    missing = tmp_path / "gallery" / "99" / "valcoin"
    assert not missing.exists()
    assert list_media_files(missing, [".mp4"]) == []
    assert list_media_stems_for_posts(missing, [".mp4"], post_count=3) == ["", "", ""]


def test_list_media_stems_for_posts(tmp_path: Path) -> None:
    folder = tmp_path / "slot"
    folder.mkdir()
    (folder / "clip_a.mp4").write_bytes(b"a")
    (folder / "clip_b.mp4").write_bytes(b"b")
    stems = list_media_stems_for_posts(folder, [".mp4"], post_count=3)
    assert stems == ["clip_a", "clip_b", ""]
