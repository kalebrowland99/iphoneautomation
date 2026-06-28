"""Per-slot TikTok account (@ handle), brand, and last-run status for dashboard stickers."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from imouse_farm.post.post_caption_store import device_storage_key

ACCOUNT_PROFILES_PATH = Path("data/account_profiles.json")
VALID_BRANDS = frozenset({"labely", "valcoin"})
VALID_STATUSES = frozenset({"idle", "running", "success", "failed"})
_LEGACY_SLOT_RE = re.compile(r"^slot:\d+$")

_store: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_profile(brand: str = "labely") -> dict[str, Any]:
    b = str(brand or "labely").strip().lower()
    if b not in VALID_BRANDS:
        b = "labely"
    return {
        "tiktok_handle": "",
        "brand": b,
        "last_run_status": "idle",
        "posts_completed": 0,
        "posts_target": 3,
        "last_run_at": None,
        "last_error": "",
    }


def _normalize_brand(brand: str) -> str:
    b = str(brand or "labely").strip().lower()
    return b if b in VALID_BRANDS else "labely"


def brand_profile_key(base_key: str, brand: str) -> str:
    """Storage key for a slot/device + brand, e.g. slot:3:valcoin."""
    base = str(base_key or "").strip()
    b = _normalize_brand(brand)
    if not base:
        return f"unknown:{b}"
    parts = base.split(":")
    if parts and parts[-1] in VALID_BRANDS:
        base = ":".join(parts[:-1])
    return f"{base}:{b}"


def base_profile_key(key: str) -> str:
    """Strip brand suffix from a storage key (slot:3:valcoin → slot:3)."""
    parts = str(key or "").split(":")
    if parts and parts[-1] in VALID_BRANDS:
        return ":".join(parts[:-1])
    return str(key or "")


def _load_store() -> None:
    global _store
    if not ACCOUNT_PROFILES_PATH.exists():
        _store = {}
        return
    try:
        raw = json.loads(ACCOUNT_PROFILES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _store = {}
        return
    loaded: dict[str, dict[str, Any]] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            str_key = str(key)
            if _LEGACY_SLOT_RE.match(str_key):
                migrated = brand_profile_key(str_key, value.get("brand", "labely"))
                loaded[migrated] = _normalize_profile(value, _normalize_brand(value.get("brand", "labely")))
            else:
                brand = _normalize_brand(value.get("brand", str_key.rsplit(":", 1)[-1]))
                loaded[str_key] = _normalize_profile(value, brand)
    _store = loaded


def _normalize_profile(data: dict[str, Any], brand: str) -> dict[str, Any]:
    base = _default_profile(brand)
    handle = str(data.get("tiktok_handle", "") or "").strip()
    if handle and not handle.startswith("@"):
        handle = f"@{handle}"
    status = str(data.get("last_run_status", "idle") or "idle").strip().lower()
    if status not in VALID_STATUSES:
        status = "idle"
    base.update({
        "tiktok_handle": handle,
        "brand": _normalize_brand(brand),
        "last_run_status": status,
        "posts_completed": max(0, int(data.get("posts_completed", 0) or 0)),
        "posts_target": max(1, int(data.get("posts_target", 3) or 3)),
        "last_run_at": data.get("last_run_at"),
        "last_error": str(data.get("last_error", "") or ""),
    })
    return base


def _save_store() -> None:
    ACCOUNT_PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACCOUNT_PROFILES_PATH.write_text(
        json.dumps(_store, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def opposite_brand(brand: str) -> str:
    b = _normalize_brand(brand)
    return "valcoin" if b == "labely" else "labely"


def normalize_handle(handle: str) -> str:
    text = str(handle or "").strip()
    if not text:
        return ""
    return text if text.startswith("@") else f"@{text}"


def handle_match_queries(handle: str) -> list[str]:
    """OCR search variants for a configured @ handle."""
    norm = normalize_handle(handle)
    if not norm:
        return []
    bare = norm.lstrip("@").strip()
    queries = [norm, bare, norm.upper(), bare.upper()]
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        key = q.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(q)
    return out


def get_profile(device_key: str, *, brand: str = "labely") -> dict[str, Any]:
    """Load profile for a storage key (with or without brand suffix)."""
    key = device_key if device_key.split(":")[-1] in VALID_BRANDS else brand_profile_key(device_key, brand)
    if key not in _store:
        _store[key] = _default_profile(_normalize_brand(brand))
    return dict(_store[key])


def get_brand_profile(base_key: str, brand: str) -> dict[str, Any]:
    return get_profile(brand_profile_key(base_key, brand), brand=brand)


def get_profile_for_device(
    device_id: str,
    user_name: str = "",
    *,
    brand: str = "labely",
) -> dict[str, Any]:
    return get_brand_profile(device_storage_key(device_id, user_name), brand)


def list_profiles(*, brand: str | None = None) -> dict[str, dict[str, Any]]:
    """Profiles keyed by base slot id (slot:N) for the requested brand."""
    brand_filter = _normalize_brand(brand) if brand else ""
    out: dict[str, dict[str, Any]] = {}
    suffix = f":{brand_filter}" if brand_filter else ""
    for key, profile in _store.items():
        if suffix and not str(key).endswith(suffix):
            continue
        if suffix:
            base = base_profile_key(key)
            out[base] = dict(profile)
        else:
            out[str(key)] = dict(profile)
    return out


def set_profile(device_key: str, *, brand: str = "labely", **fields: Any) -> dict[str, Any]:
    b = _normalize_brand(fields.get("brand", brand))
    key = device_key if device_key.split(":")[-1] in VALID_BRANDS else brand_profile_key(device_key, b)
    current = get_profile(key, brand=b)
    if "tiktok_handle" in fields:
        current["tiktok_handle"] = normalize_handle(str(fields["tiktok_handle"] or ""))
    current["brand"] = b
    _store[key] = current
    _save_store()
    return dict(current)


def mark_run_started(device_key: str, *, brand: str = "labely") -> None:
    key = brand_profile_key(device_key, brand)
    profile = get_profile(key, brand=brand)
    profile["last_run_status"] = "running"
    profile["posts_completed"] = 0
    profile["last_error"] = ""
    profile["last_run_at"] = _now_iso()
    _store[key] = profile
    _save_store()


def mark_post_completed(device_key: str, post_index: int, *, brand: str = "labely") -> None:
    key = brand_profile_key(device_key, brand)
    profile = get_profile(key, brand=brand)
    profile["posts_completed"] = max(int(profile.get("posts_completed", 0)), int(post_index))
    profile["last_run_status"] = "running"
    _store[key] = profile
    _save_store()


def mark_run_success(
    device_key: str,
    posts_completed: int | None = None,
    *,
    brand: str = "labely",
) -> None:
    key = brand_profile_key(device_key, brand)
    profile = get_profile(key, brand=brand)
    profile["last_run_status"] = "success"
    if posts_completed is not None:
        profile["posts_completed"] = max(0, int(posts_completed))
    profile["last_run_at"] = _now_iso()
    profile["last_error"] = ""
    _store[key] = profile
    _save_store()


def mark_run_failed(
    device_key: str,
    message: str = "",
    posts_completed: int | None = None,
    *,
    brand: str = "labely",
) -> None:
    key = brand_profile_key(device_key, brand)
    profile = get_profile(key, brand=brand)
    profile["last_run_status"] = "failed"
    profile["last_error"] = str(message or "")[:500]
    if posts_completed is not None:
        profile["posts_completed"] = max(0, int(posts_completed))
    profile["last_run_at"] = _now_iso()
    _store[key] = profile
    _save_store()


def mark_run_idle(device_key: str, *, brand: str = "labely") -> None:
    key = brand_profile_key(device_key, brand)
    profile = get_profile(key, brand=brand)
    profile["last_run_status"] = "idle"
    _store[key] = profile
    _save_store()


_load_store()
