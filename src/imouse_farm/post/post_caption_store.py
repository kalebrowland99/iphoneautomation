"""Per-device TikTok post text (onscreen overlay + final caption) for each post slot."""

from __future__ import annotations

from collections import defaultdict

POST_COUNT = 3

GALLERY_ITEM_COORDS: dict[int, tuple[int, int]] = {
    1: (82, 201),
    2: (191, 190),
    3: (321, 194),
}

_store: dict[str, dict[int, dict[str, str]]] = defaultdict(
    lambda: {i: {"onscreen": "", "final": ""} for i in range(1, POST_COUNT + 1)}
)


def _slot(device_id: str, post: int) -> dict[str, str]:
    if post < 1 or post > POST_COUNT:
        raise ValueError(f"post must be 1..{POST_COUNT}, got {post}")
    return _store[device_id][post]


def get_final_caption(device_id: str, post: int) -> str:
    return _slot(device_id, post)["final"]


def get_onscreen_text(device_id: str, post: int) -> str:
    return _slot(device_id, post)["onscreen"]


def set_onscreen_text(device_id: str, post: int, text: str) -> None:
    _slot(device_id, post)["onscreen"] = text or ""


def set_final_caption(device_id: str, post: int, text: str) -> None:
    _slot(device_id, post)["final"] = text or ""


def get_gallery_coords(post: int) -> tuple[int, int]:
    if post not in GALLERY_ITEM_COORDS:
        raise ValueError(f"no gallery coords for post {post}")
    return GALLERY_ITEM_COORDS[post]


def list_post_texts(device_id: str) -> list[dict[str, str | int]]:
    return [
        {
            "post": post,
            "onscreen": get_onscreen_text(device_id, post),
            "final": get_final_caption(device_id, post),
        }
        for post in range(1, POST_COUNT + 1)
    ]
