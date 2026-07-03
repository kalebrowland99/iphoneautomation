"""Download / save slideshow MP4s into per-slot gallery folders."""

from __future__ import annotations

import re
from pathlib import Path

import cv2
import httpx
import numpy as np

from imouse_farm.utils.gallery import phone_gallery_folder
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

_SLOT_RE = re.compile(r"^\d+$")
_MIN_VIDEO_BYTES = 32_768
_MAX_BLACK_FRAME_LUMA = 12.0


class SlideshowVideoRejected(ValueError):
    """Raised when an uploaded slideshow MP4 fails quality checks."""

    def __init__(self, reason: str, *, retry: bool = True) -> None:
        self.reason = reason
        self.retry = retry
        super().__init__(reason)


def is_retryable_rejection(reason: str) -> bool:
    lowered = str(reason or "").lower()
    return (
        "blank video" in lowered
        or "blank slide" in lowered
        or "too small" in lowered
        or "no video frames" in lowered
        or "unreadable video" in lowered
    )


def normalize_slot(slot: str | int) -> str:
    label = str(slot or "").strip()
    if not _SLOT_RE.match(label):
        raise ValueError(f"Invalid slot label: {slot!r} (use farm slot number, e.g. 12)")
    return label


def slot_gallery_dir(
    base_directory: str,
    slot: str | int,
    brand: str = "labely",
) -> Path:
    return phone_gallery_folder(base_directory, normalize_slot(slot), brand=brand)


def list_slot_media(
    base_directory: str,
    slot: str | int,
    extensions: list[str],
    *,
    brand: str = "labely",
) -> list[Path]:
    from imouse_farm.utils.gallery import list_media_files

    folder = slot_gallery_dir(base_directory, slot, brand=brand)
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


def _frame_luma(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(gray.mean())


def _validation_frame_indices(frame_count: int, expected_slides: int) -> list[int]:
    """Sample near the center of each equal segment — avoids swipe transitions at boundaries."""
    if frame_count <= 0:
        return []
    slides = max(1, int(expected_slides))
    indices: set[int] = set()
    for slide in range(slides):
        center = min(
            frame_count - 1,
            max(0, int((slide + 0.5) * frame_count / slides)),
        )
        indices.add(center)
    return sorted(indices)


def _slide_number_for_frame(frame_idx: int, frame_count: int, expected_slides: int) -> int:
    slides = max(1, int(expected_slides))
    if frame_count <= 0:
        return 1
    return min(slides, int(frame_idx / max(1, frame_count / slides)) + 1)


def validate_slideshow_video(path: Path, *, expected_slides: int = 1) -> tuple[bool, str]:
    """Reject tiny MP4s or any blank slide segment (failed Labely scan / empty export)."""
    if not path.is_file():
        return False, "missing file"
    size = path.stat().st_size
    if size < _MIN_VIDEO_BYTES:
        return False, f"too small ({size} bytes)"
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            return False, "unreadable video"
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        indices = _validation_frame_indices(frame_count, expected_slides) if frame_count > 1 else [0]
        for idx in indices:
            if frame_count > 1:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                return False, "no video frames"
            luma = _frame_luma(frame)
            if luma <= _MAX_BLACK_FRAME_LUMA:
                slide = _slide_number_for_frame(idx, frame_count, expected_slides)
                if slide == 1 and len(indices) == 1:
                    return False, f"blank video (luma {luma:.1f})"
                return False, f"blank slide {slide} (luma {luma:.1f} at frame {idx})"
        return True, ""
    finally:
        cap.release()


def slot_gallery_status(
    base_directory: str,
    slot: str | int,
    extensions: list[str],
    *,
    min_count: int = 1,
    expected_slides: int = 1,
    brand: str = "labely",
    prune_invalid: bool = True,
) -> tuple[bool, list[str]]:
    """Return whether the slot has enough valid videos; optionally delete bad files."""
    paths = list_slot_media(base_directory, slot, extensions, brand=brand)
    valid: list[Path] = []
    issues: list[str] = []
    for raw in paths:
        path = Path(raw)
        ok, reason = validate_slideshow_video(path, expected_slides=expected_slides)
        if ok:
            valid.append(path)
            continue
        issues.append(f"{path.name}: {reason}")
        if prune_invalid:
            path.unlink(missing_ok=True)
    needed = max(1, int(min_count))
    if len(valid) < needed:
        issues.append(f"need {needed} valid video(s), found {len(valid)}")
        return False, issues
    return True, []


def save_bytes_to_slot(
    data: bytes,
    *,
    base_directory: str,
    slot: str | int,
    filename: str,
    validate: bool = True,
    expected_slides: int = 1,
    brand: str = "labely",
) -> Path:
    slot_label = normalize_slot(slot)
    folder = slot_gallery_dir(base_directory, slot_label, brand=brand)
    folder.mkdir(parents=True, exist_ok=True)
    safe = _safe_filename(filename) or "slideshow.mp4"
    dest = (folder / safe).resolve()
    dest.write_bytes(data)
    if validate:
        ok, reason = validate_slideshow_video(dest, expected_slides=expected_slides)
        if not ok:
            dest.unlink(missing_ok=True)
            raise SlideshowVideoRejected(reason, retry=is_retryable_rejection(reason))
    logger.info(
        "slideshow_ingested_upload",
        slot=slot_label,
        path=str(dest),
        bytes=len(data),
    )
    # New video saved — the device's gallery is no longer the same as what was
    # uploaded during the last prep. Invalidate so the next batch re-runs prep.
    try:
        from imouse_farm.post.account_profile_store import clear_prep_completed
        clear_prep_completed(f"slot:{slot_label}", brand=brand)
    except Exception:  # noqa: BLE001
        pass
    return dest


def clear_slot_media(
    base_directory: str,
    slot: str | int,
    extensions: list[str],
    *,
    brand: str = "labely",
) -> int:
    """Remove existing media in slot folder before a fresh ingest."""
    removed = 0
    folder = slot_gallery_dir(base_directory, slot, brand=brand)
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


def clear_all_slot_media(
    base_directory: str,
    extensions: list[str],
    *,
    farm_slots: int = 20,
    brands: tuple[str, ...] = ("labely", "valcoin"),
) -> int:
    """Remove gallery media for every farm slot and brand."""
    removed = 0
    for slot in range(1, max(1, int(farm_slots)) + 1):
        for brand in brands:
            removed += clear_slot_media(
                base_directory,
                slot,
                extensions,
                brand=brand,
            )
    return removed


def _filename_from_url(url: str) -> str:
    tail = str(url or "").split("?", 1)[0].rstrip("/").split("/")[-1]
    return _safe_filename(tail)


def _safe_filename(name: str) -> str:
    base = str(name or "").strip().replace("\\", "/").split("/")[-1]
    base = re.sub(r'[<>:"|?*]', "_", base)
    return base[:180]
