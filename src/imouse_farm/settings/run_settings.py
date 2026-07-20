"""Farm-wide run settings persisted to disk (dashboard toggles)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from imouse_farm.post.brand_keys import normalize_brand

RUN_SETTINGS_PATH = Path("data/run_settings.json")

_BRANDS = ("labely", "valcoin")
_MIN_BATCH_SIZE = 1
_MAX_BATCH_SIZE = 20
_DEFAULT_BATCH_SIZE = 2

_DEFAULTS: dict[str, Any] = {
    # Legacy flat flag — kept for older clients; prefer per-brand map.
    "use_supplied_videos": False,
    "use_supplied_videos_by_brand": {b: False for b in _BRANDS},
    "batch_size": _DEFAULT_BATCH_SIZE,
}

_store: dict[str, Any] = dict(_DEFAULTS)


def _empty_brand_map(default: bool = False) -> dict[str, bool]:
    return {b: bool(default) for b in _BRANDS}


def _normalize_brand_map(raw: Any, *, legacy: bool = False) -> dict[str, bool]:
    out = _empty_brand_map(legacy)
    if isinstance(raw, dict):
        for brand in _BRANDS:
            if brand in raw:
                out[brand] = bool(raw[brand])
    return out


def _clamp_batch_size(value: Any, *, default: int = _DEFAULT_BATCH_SIZE) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = int(default)
    return max(_MIN_BATCH_SIZE, min(_MAX_BATCH_SIZE, n))


def _default_store() -> dict[str, Any]:
    return {
        "use_supplied_videos": False,
        "use_supplied_videos_by_brand": _empty_brand_map(False),
        "batch_size": _DEFAULT_BATCH_SIZE,
    }


def _load() -> None:
    global _store
    if not RUN_SETTINGS_PATH.exists():
        _store = _default_store()
        return
    try:
        raw = json.loads(RUN_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _store = _default_store()
        return
    if not isinstance(raw, dict):
        _store = _default_store()
        return
    legacy = bool(raw.get("use_supplied_videos", False))
    by_brand = _normalize_brand_map(
        raw.get("use_supplied_videos_by_brand"),
        legacy=legacy if "use_supplied_videos_by_brand" not in raw else False,
    )
    # If only the legacy flag existed, seed both brands from it.
    if "use_supplied_videos_by_brand" not in raw and legacy:
        by_brand = _empty_brand_map(True)
    _store = {
        "use_supplied_videos": bool(by_brand.get("labely", False)),
        "use_supplied_videos_by_brand": by_brand,
        "batch_size": _clamp_batch_size(
            raw.get("batch_size", _DEFAULT_BATCH_SIZE),
            default=_DEFAULT_BATCH_SIZE,
        ),
    }


def _save() -> None:
    RUN_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_SETTINGS_PATH.write_text(
        json.dumps(_store, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_run_settings() -> dict[str, Any]:
    by_brand = dict(_store.get("use_supplied_videos_by_brand") or _empty_brand_map())
    return {
        "use_supplied_videos": bool(by_brand.get("labely", False)),
        "use_supplied_videos_by_brand": by_brand,
        "batch_size": get_batch_size(),
    }


def get_use_supplied_videos(brand: str = "labely") -> bool:
    brand_key = normalize_brand(brand)
    by_brand = _store.get("use_supplied_videos_by_brand") or {}
    if brand_key in by_brand:
        return bool(by_brand[brand_key])
    return bool(_store.get("use_supplied_videos", False))


def set_use_supplied_videos(enabled: bool, brand: str = "labely") -> None:
    brand_key = normalize_brand(brand)
    by_brand = dict(_store.get("use_supplied_videos_by_brand") or _empty_brand_map())
    by_brand[brand_key] = bool(enabled)
    _store["use_supplied_videos_by_brand"] = by_brand
    # Legacy mirror stays Labely so old readers still see a sensible value.
    _store["use_supplied_videos"] = bool(by_brand.get("labely", False))
    _save()


def get_batch_size() -> int:
    return _clamp_batch_size(_store.get("batch_size", _DEFAULT_BATCH_SIZE))


def set_batch_size(size: int) -> None:
    _store["batch_size"] = _clamp_batch_size(size)
    _save()


def set_run_settings(
    *,
    use_supplied_videos: bool | None = None,
    brand: str | None = None,
    batch_size: int | None = None,
) -> dict[str, Any]:
    if use_supplied_videos is not None:
        set_use_supplied_videos(use_supplied_videos, brand=brand or "labely")
    if batch_size is not None:
        set_batch_size(batch_size)
    return get_run_settings()


_load()
