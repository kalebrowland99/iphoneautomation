"""Gallery upload folder resolution."""

from __future__ import annotations

import re
from pathlib import Path

from imouse_farm.post.brand_keys import normalize_brand


def phone_gallery_folder(
    base_directory: str,
    user_name: str,
    phone_name: str = "",
    *,
    brand: str = "labely",
) -> Path:
    """Map a device to ``gallery/<slot>/`` or ``gallery/<slot>/<brand>/``."""
    label = (user_name or phone_name or "default").strip().lower()
    slot_path = (Path(base_directory) / label).resolve()
    brand_key = normalize_brand(brand)
    branded = slot_path / brand_key
    if branded.is_dir():
        return branded
    if brand_key == "labely" and slot_path.is_dir() and any(slot_path.iterdir()):
        return slot_path
    return branded


def natural_sort_key(name: str) -> tuple[str | int, ...]:
    """Sort filenames with numeric chunks in human order (e.g. 2 before 10)."""
    parts = re.split(r"(\d+)", name.lower())
    return tuple(int(p) if p.isdigit() else p for p in parts)


def list_media_files(folder: Path, extensions: list[str]) -> list[str]:
    """Return absolute media paths in stable natural-sorted order (post 1 → post N)."""
    folder = folder.resolve()
    if not folder.is_dir():
        return []
    allowed = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions}
    paths = [
        p.resolve()
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in allowed
    ]
    paths.sort(key=lambda p: natural_sort_key(p.name))
    return [str(p) for p in paths]


def media_stem_for_post(files: list[str], post: int) -> str:
    """Basename (no extension) for post slot 1..N from an ordered file list."""
    if post < 1 or post > len(files):
        return ""
    return Path(files[post - 1]).stem


def list_media_stems_for_posts(
    folder: Path, extensions: list[str], post_count: int = 3
) -> list[str]:
    """Ordered media stems for each post slot (empty string if no file for slot)."""
    files = list_media_files(folder, extensions)
    stems = [Path(f).stem for f in files[:post_count]]
    while len(stems) < post_count:
        stems.append("")
    return stems
