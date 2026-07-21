"""Seed tiny sample MP4s into empty gallery slots for Run debug."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from imouse_farm.post.brand_keys import normalize_brand
from imouse_farm.post.post_caption_store import POST_COUNT
from imouse_farm.utils.gallery import list_media_files, phone_gallery_folder
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_PATH = PROJECT_ROOT / "assets" / "debug_sample.mp4"
_VIDEO_EXTENSIONS = [".mp4", ".mov", ".m4v", ".webm"]


def ensure_debug_sample_mp4() -> Path:
    """Return a small valid MP4, generating it with OpenCV if missing."""
    if SAMPLE_PATH.is_file() and SAMPLE_PATH.stat().st_size > 1024:
        return SAMPLE_PATH
    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)

    import cv2
    import numpy as np

    width, height, fps, frames = 320, 240, 10, 10
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(SAMPLE_PATH), fourcc, fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Could not create debug sample video at {SAMPLE_PATH}")
    try:
        for i in range(frames):
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            frame[:, :] = (40, 40, 40)
            cv2.putText(
                frame,
                f"debug {i + 1}",
                (40, 130),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (220, 220, 220),
                2,
                cv2.LINE_AA,
            )
            writer.write(frame)
    finally:
        writer.release()

    if not SAMPLE_PATH.is_file() or SAMPLE_PATH.stat().st_size < 1024:
        raise RuntimeError(f"Debug sample video was not written: {SAMPLE_PATH}")
    logger.info("debug_sample_mp4_created", path=str(SAMPLE_PATH), bytes=SAMPLE_PATH.stat().st_size)
    return SAMPLE_PATH


def seed_debug_gallery_slots(
    base_directory: str,
    slots: list[str | int],
    *,
    brand: str = "labely",
    count: int = POST_COUNT,
) -> dict[str, Any]:
    """Copy sample MP4s into empty (or short) gallery/<slot>/<brand>/ folders.

    Only fills missing posts — does not overwrite existing media.
    """
    brand_key = normalize_brand(brand)
    needed = max(1, min(POST_COUNT, int(count)))
    sample = ensure_debug_sample_mp4()
    seeded: list[dict[str, Any]] = []

    for slot in slots:
        label = str(slot).strip()
        if not label:
            continue
        # Force branded folder so upload always reads the same place.
        dest_folder = Path(base_directory).resolve() / label.lower() / brand_key
        dest_folder.mkdir(parents=True, exist_ok=True)
        # phone_gallery_folder prefers branded dir once it exists
        folder = phone_gallery_folder(base_directory, label, brand=brand_key)
        existing = list_media_files(folder, _VIDEO_EXTENSIONS)
        missing = needed - len(existing)
        if missing <= 0:
            continue
        added: list[str] = []
        start = len(existing) + 1
        for i in range(missing):
            name = f"debug-sample-{start + i:02d}.mp4"
            dest = Path(folder) / name
            if dest.exists():
                continue
            shutil.copy2(sample, dest)
            added.append(dest.name)
        if added:
            seeded.append(
                {
                    "slot": label,
                    "brand": brand_key,
                    "folder": str(folder),
                    "added": added,
                }
            )
            logger.info(
                "debug_gallery_seeded",
                slot=label,
                brand=brand_key,
                added=len(added),
                folder=str(folder),
            )
    return {
        "brand": brand_key,
        "sample": str(sample),
        "seeded": seeded,
        "slots_seeded": len(seeded),
    }
