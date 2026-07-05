"""Per-slot TikTok account (@ handle), brand, and last-run status for dashboard stickers."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from imouse_farm.post.brand_keys import (
    VALID_BRANDS,
    base_profile_key,
    brand_profile_key,
    device_storage_key,
    normalize_brand,
)

ACCOUNT_PROFILES_PATH = Path("data/account_profiles.json")
VALID_STATUSES = frozenset({"idle", "running", "success", "failed"})
_LEGACY_SLOT_RE = re.compile(r"^slot:\d+$")
_24H_SECONDS = 86_400

_store: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_within_24h(ts: str | None) -> bool:
    """Return True if *ts* is a valid ISO timestamp recorded within the last 24 hours."""
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        return 0 <= age < _24H_SECONDS
    except (ValueError, TypeError):
        return False


def _default_profile(brand: str = "labely") -> dict[str, Any]:
    b = str(brand or "labely").strip().lower()
    if b not in VALID_BRANDS:
        b = "labely"
    return {
        "tiktok_handle": "",
        "brand": b,
        "warmup_enabled": False,
        "warmup_days_completed": 0,
        "last_warmup_at": None,
        "last_run_status": "idle",
        "posts_completed": 0,
        "posts_target": 3,
        "last_run_at": None,
        "last_error": "",
        "prep_completed_at": None,
        "cant_cast_imouse": False,
    }


def _normalize_brand(brand: str) -> str:
    return normalize_brand(brand)


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
    # Any profile still marked "running" at load time was interrupted by a
    # server restart — no run survives a reload, so mark them failed.
    for profile in loaded.values():
        if profile.get("last_run_status") == "running":
            profile["last_run_status"] = "failed"
            profile["last_error"] = "interrupted by server restart"
    _store = loaded


def _normalize_profile(data: dict[str, Any], brand: str) -> dict[str, Any]:
    base = _default_profile(brand)
    handle = str(data.get("tiktok_handle", "") or "").strip()
    if handle and not handle.startswith("@"):
        handle = f"@{handle}"
    status = str(data.get("last_run_status", "idle") or "idle").strip().lower()
    if status not in VALID_STATUSES:
        status = "idle"
    # Migrate legacy bool prep_completed → prep_completed_at
    prep_at = data.get("prep_completed_at") or (
        _now_iso() if data.get("prep_completed") else None
    )
    base.update({
        "tiktok_handle": handle,
        "brand": _normalize_brand(brand),
        "warmup_enabled": bool(data.get("warmup_enabled", False)),
        "warmup_days_completed": max(0, int(data.get("warmup_days_completed", 0) or 0)),
        "last_warmup_at": data.get("last_warmup_at") or None,
        "last_run_status": status,
        "posts_completed": max(0, int(data.get("posts_completed", 0) or 0)),
        "posts_target": max(1, int(data.get("posts_target", 3) or 3)),
        "last_run_at": data.get("last_run_at"),
        "last_error": str(data.get("last_error", "") or ""),
        "prep_completed_at": prep_at or None,
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
    if "warmup_enabled" in fields:
        current["warmup_enabled"] = bool(fields["warmup_enabled"])
    current["brand"] = b
    _store[key] = current
    _save_store()
    return dict(current)


def increment_warmup_days(device_id: str, user_name: str = "", *, brand: str = "labely") -> int:
    """Increment warmup_days_completed only if >= 24 h have passed since the last warmup.

    Always records the current time in last_warmup_at.
    Returns the (possibly unchanged) day count.
    """
    key = brand_profile_key(device_storage_key(device_id, user_name), brand)
    profile = get_profile(key, brand=brand)
    current_day = int(profile.get("warmup_days_completed", 0) or 0)
    last_warmup_at = profile.get("last_warmup_at")
    if not _is_within_24h(last_warmup_at):
        # First warmup of the day — increment the counter.
        current_day += 1
        profile["warmup_days_completed"] = current_day
    profile["last_warmup_at"] = _now_iso()
    _store[key] = profile
    _save_store()
    return current_day


def is_prep_valid(device_key: str, *, brand: str = "labely") -> bool:
    """Return True if prep was completed within the last 24 hours."""
    key = brand_profile_key(device_key, brand)
    profile = get_profile(key, brand=brand)
    return _is_within_24h(profile.get("prep_completed_at"))


def mark_prep_completed(device_key: str, *, brand: str = "labely") -> None:
    """Record that tiktok_prep uploaded videos to the device — safe to skip on restart."""
    key = brand_profile_key(device_key, brand)
    profile = get_profile(key, brand=brand)
    profile["prep_completed_at"] = _now_iso()
    _store[key] = profile
    _save_store()


def clear_prep_completed(device_key: str, *, brand: str = "labely") -> None:
    """Invalidate the prep-done flag so the next run re-uploads videos."""
    key = brand_profile_key(device_key, brand)
    profile = get_profile(key, brand=brand)
    profile["prep_completed_at"] = None
    _store[key] = profile
    _save_store()


def reset_last_run_state(device_key: str, *, brand: str = "labely") -> None:
    """Clear last-run sticker fields so the dashboard shows Never / idle."""
    key = brand_profile_key(device_key, brand)
    profile = get_profile(key, brand=brand)
    profile["last_run_status"] = "idle"
    profile["last_run_at"] = None
    profile["last_error"] = ""
    profile["posts_completed"] = 0
    _store[key] = profile
    _save_store()


def reset_session_for_slot(base_key: str, *, brand: str = "labely") -> None:
    """Clear prep + last-run state for one slot profile."""
    clear_prep_completed(base_key, brand=brand)
    reset_last_run_state(base_key, brand=brand)


def reset_all_session_states(*, farm_slots: int = 20) -> list[str]:
    """Reset prep, last-run, and cant-cast tags for every farm slot (both brands)."""
    cleared: list[str] = []
    for slot in range(1, max(1, int(farm_slots)) + 1):
        base_key = f"slot:{slot}"
        for brand in VALID_BRANDS:
            reset_session_for_slot(base_key, brand=brand)
        clear_cant_cast_imouse(base_key)
        cleared.append(str(slot))
    return cleared


def mark_run_started(device_key: str, *, brand: str = "labely") -> None:
    key = brand_profile_key(device_key, brand)
    profile = get_profile(key, brand=brand)
    profile["last_run_status"] = "running"
    profile["posts_completed"] = 0
    profile["last_error"] = ""
    profile["last_run_at"] = _now_iso()
    # Preserve prep_completed — if videos were already uploaded before this run
    # started (e.g. a restart), the flag stays True so the next batch can skip prep.
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
    profile["prep_completed_at"] = None  # full run done; next run should upload fresh videos
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


# ── Device-level cast tag (not brand-specific) ────────────────────────────────

def set_cant_cast_imouse(base_key: str) -> None:
    """Mark a device slot as unable to cast. Persists across runs until cleared."""
    changed = False
    for brand in VALID_BRANDS:
        key = brand_profile_key(base_key, brand)
        if key in _store:
            _store[key]["cant_cast_imouse"] = True
            changed = True
    if not changed:
        # Ensure at least one profile exists with the flag set.
        for brand in VALID_BRANDS:
            key = brand_profile_key(base_key, brand)
            profile = get_profile(key, brand=brand)
            profile["cant_cast_imouse"] = True
            _store[key] = profile
    _save_store()


def clear_cant_cast_imouse(base_key: str) -> None:
    """Clear the cant_cast_imouse tag so the device will be attempted again."""
    for brand in VALID_BRANDS:
        key = brand_profile_key(base_key, brand)
        if key in _store:
            _store[key]["cant_cast_imouse"] = False
    _save_store()


def is_cant_cast_imouse(base_key: str) -> bool:
    """Return True if ANY brand profile for this slot has cant_cast_imouse=True."""
    for brand in VALID_BRANDS:
        key = brand_profile_key(base_key, brand)
        if _store.get(key, {}).get("cant_cast_imouse"):
            return True
    return False


_load_store()
