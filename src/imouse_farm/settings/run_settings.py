"""Farm-wide run settings persisted to disk (dashboard toggles)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RUN_SETTINGS_PATH = Path("data/run_settings.json")

_DEFAULTS: dict[str, Any] = {
    "use_supplied_videos": False,
}

_store: dict[str, Any] = dict(_DEFAULTS)


def _load() -> None:
    global _store
    if not RUN_SETTINGS_PATH.exists():
        _store = dict(_DEFAULTS)
        return
    try:
        raw = json.loads(RUN_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _store = dict(_DEFAULTS)
        return
    if not isinstance(raw, dict):
        _store = dict(_DEFAULTS)
        return
    merged = dict(_DEFAULTS)
    merged["use_supplied_videos"] = bool(raw.get("use_supplied_videos", False))
    _store = merged


def _save() -> None:
    RUN_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_SETTINGS_PATH.write_text(
        json.dumps(_store, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_run_settings() -> dict[str, Any]:
    return dict(_store)


def get_use_supplied_videos() -> bool:
    return bool(_store.get("use_supplied_videos", False))


def set_use_supplied_videos(enabled: bool) -> None:
    _store["use_supplied_videos"] = bool(enabled)
    _save()


def set_run_settings(*, use_supplied_videos: bool | None = None) -> dict[str, Any]:
    if use_supplied_videos is not None:
        set_use_supplied_videos(use_supplied_videos)
    return get_run_settings()


_load()
