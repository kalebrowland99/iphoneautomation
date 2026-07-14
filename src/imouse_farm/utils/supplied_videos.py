"""Brand-level supplied videos staged once, then copied to every phone gallery."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from imouse_farm.integrations.slideshow_ingest import (
    SlideshowVideoRejected,
    _safe_filename,
    clear_slot_media,
    validate_slideshow_video,
)
from imouse_farm.post.brand_keys import normalize_brand
from imouse_farm.post.post_caption_store import POST_COUNT
from imouse_farm.utils.gallery import list_media_files, natural_sort_key, phone_gallery_folder
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

SUPPLIED_DIR_NAME = "_supplied"
_VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v", ".webm")


def supplied_brand_dir(base_directory: str, brand: str = "labely") -> Path:
    brand_key = normalize_brand(brand)
    return (Path(base_directory).resolve() / SUPPLIED_DIR_NAME / brand_key)


def list_supplied_videos(
    base_directory: str,
    *,
    brand: str = "labely",
    extensions: list[str] | None = None,
) -> list[Path]:
    folder = supplied_brand_dir(base_directory, brand)
    exts = extensions or list(_VIDEO_EXTENSIONS)
    return [Path(p) for p in list_media_files(folder, exts)]


def supplied_videos_status(
    base_directory: str,
    *,
    brand: str = "labely",
    expected_count: int = POST_COUNT,
    extensions: list[str] | None = None,
) -> dict[str, Any]:
    paths = list_supplied_videos(base_directory, brand=brand, extensions=extensions)
    return {
        "brand": normalize_brand(brand),
        "folder": str(supplied_brand_dir(base_directory, brand)),
        "expected_count": int(expected_count),
        "count": len(paths),
        "ready": len(paths) >= int(expected_count),
        "files": [
            {
                "name": p.name,
                "bytes": p.stat().st_size if p.is_file() else 0,
                "path": str(p),
            }
            for p in paths
        ],
    }


def save_supplied_video(
    data: bytes,
    *,
    base_directory: str,
    brand: str = "labely",
    filename: str,
    max_count: int = POST_COUNT,
) -> Path:
    if len(data) < 1024:
        raise SlideshowVideoRejected("file too small", retry=False)
    folder = supplied_brand_dir(base_directory, brand)
    folder.mkdir(parents=True, exist_ok=True)
    existing = list_supplied_videos(base_directory, brand=brand)
    if len(existing) >= int(max_count):
        raise ValueError(
            f"Already have {len(existing)} video(s) for {normalize_brand(brand)} "
            f"(max {max_count}). Remove one before uploading more."
        )
    safe = _safe_filename(filename) or "video.mp4"
    if Path(safe).suffix.lower() not in _VIDEO_EXTENSIONS:
        safe = f"{Path(safe).stem or 'video'}.mp4"
    # Stable numbered names so Recents / gallery order stays predictable.
    index = len(existing) + 1
    dest_name = f"{index:02d}_{safe}"
    dest = (folder / dest_name).resolve()
    dest.write_bytes(data)
    ok, reason = validate_slideshow_video(dest, expected_slides=1)
    if not ok:
        dest.unlink(missing_ok=True)
        raise SlideshowVideoRejected(reason, retry=False)
    logger.info(
        "supplied_video_saved",
        brand=normalize_brand(brand),
        path=str(dest),
        bytes=len(data),
    )
    return dest


def delete_supplied_video(
    base_directory: str,
    filename: str,
    *,
    brand: str = "labely",
) -> bool:
    folder = supplied_brand_dir(base_directory, brand)
    safe = _safe_filename(filename)
    if not safe:
        return False
    path = (folder / safe).resolve()
    try:
        path.relative_to(folder.resolve())
    except ValueError:
        return False
    if not path.is_file():
        return False
    path.unlink(missing_ok=True)
    _renumber_supplied_videos(folder)
    return True


def clear_supplied_videos(base_directory: str, *, brand: str = "labely") -> int:
    folder = supplied_brand_dir(base_directory, brand)
    if not folder.is_dir():
        return 0
    removed = 0
    for path in list(folder.iterdir()):
        if path.is_file() and path.suffix.lower() in _VIDEO_EXTENSIONS:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def _renumber_supplied_videos(folder: Path) -> None:
    """Keep filenames as 01_*, 02_*, … after deletes."""
    if not folder.is_dir():
        return
    files = sorted(
        [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in _VIDEO_EXTENSIONS],
        key=lambda p: natural_sort_key(p.name),
    )
    for idx, path in enumerate(files, start=1):
        stem = path.name
        # Strip leading NN_ if present
        if len(stem) > 3 and stem[0:2].isdigit() and stem[2] == "_":
            remainder = stem[3:]
        else:
            remainder = stem
        new_name = f"{idx:02d}_{remainder}"
        if new_name == path.name:
            continue
        dest = path.with_name(new_name)
        if dest.exists():
            continue
        path.rename(dest)


def distribute_supplied_videos(
    base_directory: str,
    slots: list[str | int],
    *,
    brand: str = "labely",
    extensions: list[str] | None = None,
    expected_count: int = POST_COUNT,
) -> dict[str, Any]:
    """Copy staged brand videos into each selected phone gallery folder."""
    brand_key = normalize_brand(brand)
    sources = list_supplied_videos(base_directory, brand=brand_key, extensions=extensions)
    if len(sources) < int(expected_count):
        raise ValueError(
            f"Need {expected_count} supplied video(s) for {brand_key}, "
            f"found {len(sources)}. Upload them in Captions & settings."
        )
    sources = sources[: int(expected_count)]
    exts = extensions or list(_VIDEO_EXTENSIONS)
    distributed: list[dict[str, Any]] = []
    for slot in slots:
        label = str(slot).strip()
        if not label:
            continue
        clear_slot_media(base_directory, label, exts, brand=brand_key)
        dest_folder = phone_gallery_folder(base_directory, label, brand=brand_key)
        dest_folder.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        for src in sources:
            dest = dest_folder / src.name
            shutil.copy2(src, dest)
            copied.append(dest.name)
        try:
            from imouse_farm.post.account_profile_store import clear_prep_completed

            clear_prep_completed(f"slot:{label}", brand=brand_key)
        except Exception:  # noqa: BLE001
            pass
        distributed.append({"slot": label, "files": copied, "folder": str(dest_folder)})
        logger.info(
            "supplied_videos_distributed",
            brand=brand_key,
            slot=label,
            files=copied,
        )
    return {
        "brand": brand_key,
        "source_count": len(sources),
        "slots": distributed,
    }
