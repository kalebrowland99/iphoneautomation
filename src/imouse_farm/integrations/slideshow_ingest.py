"""Download / save slideshow MP4s into per-slot gallery folders."""

from __future__ import annotations

import re
from pathlib import Path

import httpx

from imouse_farm.utils.gallery import phone_gallery_folder
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

_SLOT_RE = re.compile(r"^\d+$")


def normalize_slot(slot: str | int) -> str:
    label = str(slot or "").strip()
    if not _SLOT_RE.match(label):
        raise ValueError(f"Invalid slot label: {slot!r} (use farm slot number, e.g. 12)")
    return label


def slot_gallery_dir(base_directory: str, slot: str | int) -> Path:
    return phone_gallery_folder(base_directory, normalize_slot(slot))


def list_slot_media(
    base_directory: str,
    slot: str | int,
    extensions: list[str],
) -> list[Path]:
    from imouse_farm.utils.gallery import list_media_files

    folder = slot_gallery_dir(base_directory, slot)
    return list_media_files(folder, extensions)


async def download_url_to_slot(
    url: str,
    *,
    base_directory: str,
    slot: str | int,
    filename: str | None = None,
    timeout_seconds: float = 600.0,
) -> Path:
    """Download a remote MP4/image into gallery/<slot>/."""
    slot_label = normalize_slot(slot)
    folder = slot_gallery_dir(base_directory, slot_label)
    folder.mkdir(parents=True, exist_ok=True)
    name = str(filename or "").strip() or _filename_from_url(url)
    if not name:
        name = "slideshow.mp4"
    dest = (folder / name).resolve()
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    logger.info(
        "slideshow_ingested_url",
        slot=slot_label,
        path=str(dest),
        bytes=len(resp.content),
    )
    return dest


def save_bytes_to_slot(
    data: bytes,
    *,
    base_directory: str,
    slot: str | int,
    filename: str,
) -> Path:
    slot_label = normalize_slot(slot)
    folder = slot_gallery_dir(base_directory, slot_label)
    folder.mkdir(parents=True, exist_ok=True)
    safe = _safe_filename(filename) or "slideshow.mp4"
    dest = (folder / safe).resolve()
    dest.write_bytes(data)
    logger.info(
        "slideshow_ingested_upload",
        slot=slot_label,
        path=str(dest),
        bytes=len(data),
    )
    return dest


def clear_slot_media(
    base_directory: str,
    slot: str | int,
    extensions: list[str],
) -> int:
    """Remove existing media in slot folder before a fresh ingest."""
    removed = 0
    folder = slot_gallery_dir(base_directory, slot)
    if not folder.is_dir():
        return 0
    ext_set = {e.lower() for e in extensions}
    for path in folder.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in ext_set:
            continue
        path.unlink(missing_ok=True)
        removed += 1
    return removed


def _filename_from_url(url: str) -> str:
    tail = str(url or "").split("?", 1)[0].rstrip("/").split("/")[-1]
    return _safe_filename(tail)


def _safe_filename(name: str) -> str:
    base = str(name or "").strip().replace("\\", "/").split("/")[-1]
    base = re.sub(r'[<>:"|?*]', "_", base)
    return base[:180]
