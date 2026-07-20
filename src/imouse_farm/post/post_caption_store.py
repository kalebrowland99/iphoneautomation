"""Per-device, per-brand TikTok post text (onscreen overlay + final caption)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from imouse_farm.post.brand_keys import (
    VALID_BRANDS,
    base_profile_key,
    brand_profile_key,
    device_storage_key,
    text_key_for_device,
)

POST_COUNT = 3
POST_TEXTS_PATH = Path("data/post_texts.json")
_LEGACY_SLOT_RE = re.compile(r"^slot:\d+$")

GALLERY_ITEM_COORDS: dict[int, tuple[int, int]] = {
    1: (95, 295),     # left / newest in Recents (post 3)
    2: (305, 291),    # middle (post 2)
    3: (513, 267),    # right / oldest (post 1)
}

_GALLERY_LEFT_XY = GALLERY_ITEM_COORDS[1]
_GALLERY_RIGHT_XY = GALLERY_ITEM_COORDS[3]


def gallery_coords_for_post(post: int, total: int = POST_COUNT) -> tuple[int, int]:
    """Map workflow post 1..N to Recents tile among ``total`` videos (1–3).

    Recents fills left→right (newest on the left). With 3 videos, post 1 is
    rightmost and post 3 leftmost. With 1 video, the only tile is leftmost —
    not the middle (old single-item coords missed the thumb).
    """
    n = max(1, min(POST_COUNT, int(total)))
    p = max(1, min(n, int(post)))
    if n == 1:
        return _GALLERY_LEFT_XY
    if n == POST_COUNT:
        slot = POST_COUNT + 1 - p
        return GALLERY_ITEM_COORDS[slot]
    slot_from_left = n - p + 1
    t = (slot_from_left - 1) / (n - 1)
    x0, y0 = _GALLERY_LEFT_XY
    x1, y1 = _GALLERY_RIGHT_XY
    return (
        int(round(x0 + (x1 - x0) * t)),
        int(round(y0 + (y1 - y0) * t)),
    )

_store: dict[str, dict[int, dict[str, str]]] = {}


def _resolve_text_key(device_key: str, *, brand: str | None = None) -> str:
    key = str(device_key or "").strip()
    if brand is not None:
        base = base_profile_key(key) if key else "unknown"
        return brand_profile_key(base, brand)
    if not key:
        return brand_profile_key("unknown", "labely")
    parts = key.split(":")
    if parts and parts[-1] in VALID_BRANDS:
        return key
    return brand_profile_key(key, "labely")


def _default_posts() -> dict[int, dict[str, str]]:
    return {i: {"onscreen": "", "final": ""} for i in range(1, POST_COUNT + 1)}


def _load_store() -> None:
    global _store
    if not POST_TEXTS_PATH.exists():
        _store = {}
        return
    try:
        raw = json.loads(POST_TEXTS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _store = {}
        return
    loaded: dict[str, dict[int, dict[str, str]]] = {}
    for device_key, posts in raw.items():
        if not isinstance(posts, dict):
            continue
        slot: dict[int, dict[str, str]] = _default_posts()
        for post_key, fields in posts.items():
            try:
                post_num = int(post_key)
            except (TypeError, ValueError):
                continue
            if post_num < 1 or post_num > POST_COUNT or not isinstance(fields, dict):
                continue
            slot[post_num] = {
                "onscreen": str(fields.get("onscreen", "")),
                "final": str(fields.get("final", "")),
            }
        str_key = str(device_key)
        if _LEGACY_SLOT_RE.match(str_key) or (
            ":" in str_key and str_key.split(":")[-1] not in VALID_BRANDS
        ):
            loaded[brand_profile_key(str_key, "labely")] = slot
        else:
            loaded[str_key] = slot
    _store = loaded


def _save_store() -> None:
    serializable: dict[str, dict[str, dict[str, str]]] = {}
    for device_key, posts in _store.items():
        serializable[device_key] = {
            str(post): {"onscreen": data["onscreen"], "final": data["final"]}
            for post, data in posts.items()
        }
    POST_TEXTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    POST_TEXTS_PATH.write_text(
        json.dumps(serializable, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _slot(device_key: str, post: int, *, brand: str | None = None) -> dict[str, str]:
    if post < 1 or post > POST_COUNT:
        raise ValueError(f"post must be 1..{POST_COUNT}, got {post}")
    key = _resolve_text_key(device_key, brand=brand)
    if key not in _store:
        _store[key] = _default_posts()
    return _store[key][post]


def get_final_caption(device_key: str, post: int, *, brand: str | None = None) -> str:
    return _slot(device_key, post, brand=brand)["final"]


def get_onscreen_text(device_key: str, post: int, *, brand: str | None = None) -> str:
    return _slot(device_key, post, brand=brand)["onscreen"]


def set_onscreen_text(
    device_key: str,
    post: int,
    text: str,
    *,
    brand: str | None = None,
) -> None:
    _slot(device_key, post, brand=brand)["onscreen"] = text or ""
    _save_store()


def set_final_caption(
    device_key: str,
    post: int,
    text: str,
    *,
    brand: str | None = None,
) -> None:
    _slot(device_key, post, brand=brand)["final"] = text or ""
    _save_store()


def clear_all_post_texts(device_key: str, *, brand: str | None = None) -> None:
    key = _resolve_text_key(device_key, brand=brand)
    _store[key] = _default_posts()
    _save_store()


def copy_onscreen_to_all_slots(source_key: str, *, brand: str | None = None) -> int:
    """Copy onscreen text from one slot to every other slot for the same brand."""
    source_resolved = _resolve_text_key(source_key, brand=brand)
    if source_resolved not in _store:
        return 0
    source_brand = source_resolved.rsplit(":", 1)[-1]
    source = _store[source_resolved]
    onscreen_by_post = {post: data["onscreen"] for post, data in source.items()}
    updated = 0
    for device_key, posts in _store.items():
        if device_key == source_resolved:
            continue
        if not str(device_key).endswith(f":{source_brand}"):
            continue
        if base_profile_key(device_key) == base_profile_key(source_resolved):
            continue
        for post, text in onscreen_by_post.items():
            if text and posts.get(post, {}).get("onscreen") != text:
                posts[post]["onscreen"] = text
                updated += 1
    if updated:
        _save_store()
    return updated


def list_device_keys() -> list[str]:
    return list(_store.keys())


def gallery_slot_for_post(post: int) -> int:
    """Map workflow post 1..N to Recents picker slot (post 1 → rightmost / media 3)."""
    if post < 1 or post > POST_COUNT:
        raise ValueError(f"post must be 1..{POST_COUNT}, got {post}")
    return POST_COUNT + 1 - post


def media_index_for_post(post: int, total: int = POST_COUNT) -> int:
    """0-based gallery file index for workflow post N among ``total`` files.

    With 3 videos: post 1 → third file (rightmost). With 1 video: post 1 → only file.
    """
    n = max(1, min(POST_COUNT, int(total)))
    if post < 1 or post > n:
        raise ValueError(f"post must be 1..{n}, got {post}")
    return n - post


def post_media_stem(stems: list[str], post: int, *, total: int | None = None) -> str:
    """Gallery filename stem bound to workflow post N."""
    n = int(total) if total is not None else POST_COUNT
    idx = media_index_for_post(post, n)
    if idx < 0 or idx >= len(stems):
        return ""
    return stems[idx]


def stems_in_post_order(stems: list[str], post_count: int = POST_COUNT) -> list[str]:
    """Return gallery stems ordered by workflow post (index 0 = post 1)."""
    padded = list(stems)
    while len(padded) < post_count:
        padded.append("")
    return [post_media_stem(padded, post) for post in range(1, post_count + 1)]


def foods_post_order_to_file_order(
    foods: list[str],
    post_count: int = POST_COUNT,
) -> list[str]:
    """Map post-ordered food labels to gallery file index order."""
    out = [""] * post_count
    for post in range(1, post_count + 1):
        idx = media_index_for_post(post)
        if post - 1 < len(foods):
            out[idx] = foods[post - 1]
    return out


def get_gallery_coords(post: int) -> tuple[int, int]:
    return gallery_coords_for_post(post, POST_COUNT)


def list_post_texts(device_key: str, *, brand: str | None = None) -> list[dict[str, str | int]]:
    return [
        {
            "post": post,
            "onscreen": get_onscreen_text(device_key, post, brand=brand),
            "final": get_final_caption(device_key, post, brand=brand),
        }
        for post in range(1, POST_COUNT + 1)
    ]


def validate_post_texts(
    device_key: str,
    *,
    from_post: int = 1,
    to_post: int | None = None,
    brand: str | None = None,
    require_onscreen: bool = True,
) -> list[str]:
    """Return errors for empty onscreen/final fields required before a pipeline run."""
    end = POST_COUNT if to_post is None else int(to_post)
    end = max(1, min(POST_COUNT, end))
    if from_post < 1 or from_post > POST_COUNT:
        raise ValueError(f"from_post must be 1..{POST_COUNT}, got {from_post}")
    if from_post > end:
        raise ValueError(f"from_post {from_post} is after to_post {end}")
    errors: list[str] = []
    for post in range(from_post, end + 1):
        if require_onscreen and not get_onscreen_text(device_key, post, brand=brand).strip():
            errors.append(f"Post {post}: onscreen text is empty")
        if not get_final_caption(device_key, post, brand=brand).strip():
            errors.append(f"Post {post}: final caption is empty")
    return errors


_load_store()
