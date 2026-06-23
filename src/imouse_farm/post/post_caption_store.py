"""Shared TikTok post caption text (set from dashboard, read by tiktok_post workflow)."""

from __future__ import annotations

_caption: str = ""


def get_post_caption() -> str:
    return _caption


def set_post_caption(text: str) -> None:
    global _caption
    _caption = text or ""
