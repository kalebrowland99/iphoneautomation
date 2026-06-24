"""Per-device runtime settings (dashboard toggles, not persisted to disk)."""

from __future__ import annotations

from typing import Any

_store: dict[str, dict[str, Any]] = {}


def _slot(device_id: str) -> dict[str, Any]:
    if device_id not in _store:
        _store[device_id] = {"debug_skip_post": False}
    return _store[device_id]


def get_debug_skip_post(device_id: str) -> bool:
    return bool(_slot(device_id).get("debug_skip_post", False))


def set_debug_skip_post(device_id: str, enabled: bool) -> None:
    _slot(device_id)["debug_skip_post"] = bool(enabled)


def get_device_settings(device_id: str) -> dict[str, Any]:
    return dict(_slot(device_id))
