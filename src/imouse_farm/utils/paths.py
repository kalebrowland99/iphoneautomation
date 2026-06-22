"""Filesystem path helpers."""

from __future__ import annotations


def safe_device_dir_name(device_id: str) -> str:
    """Return a filesystem-safe directory name for a device id (MAC addresses contain ':')."""
    return device_id.replace(":", "-").replace("/", "_").replace("\\", "_")
