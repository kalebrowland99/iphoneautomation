"""Per-device TikTok post text (onscreen overlay + final caption) for each post slot."""

from __future__ import annotations

import json
from pathlib import Path

POST_COUNT = 3
POST_TEXTS_PATH = Path("data/post_texts.json")

GALLERY_ITEM_COORDS: dict[int, tuple[int, int]] = {
    1: (95, 295),     # left / newest in Recents (post 3)
    2: (305, 291),    # middle (post 2)
    3: (513, 267),    # right / oldest (post 1)
}

_store: dict[str, dict[int, dict[str, str]]] = {}


def device_storage_key(device_id: str, user_name: str = "") -> str:
    """Stable key for post text (farm slot survives browser refresh / server restart)."""
    slot = str(user_name or "").strip().lower()
    return f"slot:{slot}" if slot else device_id


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
        loaded[str(device_key)] = slot
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


def _slot(device_key: str, post: int) -> dict[str, str]:
    if post < 1 or post > POST_COUNT:
        raise ValueError(f"post must be 1..{POST_COUNT}, got {post}")
    if device_key not in _store:
        _store[device_key] = _default_posts()
    return _store[device_key][post]


def get_final_caption(device_key: str, post: int) -> str:
    return _slot(device_key, post)["final"]


def get_onscreen_text(device_key: str, post: int) -> str:
    return _slot(device_key, post)["onscreen"]


def set_onscreen_text(device_key: str, post: int, text: str) -> None:
    _slot(device_key, post)["onscreen"] = text or ""
    _save_store()


def set_final_caption(device_key: str, post: int, text: str) -> None:
    _slot(device_key, post)["final"] = text or ""
    _save_store()


def clear_all_post_texts(device_key: str) -> None:
    _store[device_key] = _default_posts()
    _save_store()


def copy_onscreen_to_all_slots(source_key: str) -> int:
    """Copy onscreen text from one slot to every other slot in the store."""
    if source_key not in _store:
        return 0
    source = _store[source_key]
    onscreen_by_post = {post: data["onscreen"] for post, data in source.items()}
    updated = 0
    for device_key, posts in _store.items():
        if device_key == source_key:
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


def media_index_for_post(post: int) -> int:
    """0-based gallery file index for workflow post N (post 1 → third file)."""
    if post < 1 or post > POST_COUNT:
        raise ValueError(f"post must be 1..{POST_COUNT}, got {post}")
    return POST_COUNT - post


def post_media_stem(stems: list[str], post: int) -> str:
    """Gallery filename stem bound to workflow post N."""
    idx = media_index_for_post(post)
    if idx < 0 or idx >= len(stems):
        return ""
    return stems[idx]


def get_gallery_coords(post: int) -> tuple[int, int]:
    slot = gallery_slot_for_post(post)
    if slot not in GALLERY_ITEM_COORDS:
        raise ValueError(f"no gallery coords for slot {slot}")
    return GALLERY_ITEM_COORDS[slot]


def list_post_texts(device_key: str) -> list[dict[str, str | int]]:
    return [
        {
            "post": post,
            "onscreen": get_onscreen_text(device_key, post),
            "final": get_final_caption(device_key, post),
        }
        for post in range(1, POST_COUNT + 1)
    ]


def validate_post_texts(device_key: str, *, from_post: int = 1) -> list[str]:
    """Return errors for empty onscreen/final fields required before a pipeline run."""
    if from_post < 1 or from_post > POST_COUNT:
        raise ValueError(f"from_post must be 1..{POST_COUNT}, got {from_post}")
    errors: list[str] = []
    for post in range(from_post, POST_COUNT + 1):
        if not get_onscreen_text(device_key, post).strip():
            errors.append(f"Post {post}: onscreen text is empty")
        if not get_final_caption(device_key, post).strip():
            errors.append(f"Post {post}: final caption is empty")
    return errors


_load_store()
