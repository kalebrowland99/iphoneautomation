"""Gallery upload folder resolution."""

from __future__ import annotations

from pathlib import Path


def phone_gallery_folder(base_directory: str, user_name: str, phone_name: str = "") -> Path:
    """Map a device to ``gallery/<slot>/`` using iMouse slot label (e.g. ``12``)."""
    label = (user_name or phone_name or "default").strip().lower()
    return (Path(base_directory) / label).resolve()


def list_media_files(folder: Path, extensions: list[str]) -> list[str]:
    folder = folder.resolve()
    allowed = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions}
    return sorted(
        str(p.resolve())
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in allowed
    )
