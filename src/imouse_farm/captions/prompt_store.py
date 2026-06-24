"""In-memory AI caption prompt and hashtag settings (dashboard-editable)."""

from __future__ import annotations

DEFAULT_AI_PROMPT = """\
each post has a video filename that names the food. underscores and hyphens in the filename separate words. read the raw filename first, then identify the food.

write a health conscious tiktok caption that feels viral and drives engagement. all lowercase. no title case. sound like a real person sharing a short personal anecdote, not a brand.

use statements and facts only. never ask questions. no question marks. tell it like something you noticed, scanned, or realized about this specific food.

open with a hook. talk about what hides in everyday foods: sketchy ingredients, microplastics, carcinogens, stuff labels bury in tiny print. curious, relatable, slightly unsettling, not preachy.

do not use hyphens or dashes anywhere in the caption. use commas and periods instead.

work in one soft, natural mention of labely, what you use to scan barcodes and see what's really in products before you eat. never use words like app, download, free, link, promo, sponsored, ad, or sale. just name labely once like you're telling a friend what helped you figure it out.

each caption must be unique. tie it directly to the food from that post's filename."""

DEFAULT_AI_HASHTAGS = "#fyp #foodtok #health #cleaneating #ingredients #labely"

_settings: dict[str, str] = {
    "prompt": DEFAULT_AI_PROMPT,
    "hashtags": DEFAULT_AI_HASHTAGS,
}


def get_ai_prompt() -> str:
    return _settings["prompt"]


def get_ai_hashtags() -> str:
    return _settings["hashtags"]


def set_ai_prompt(text: str) -> None:
    _settings["prompt"] = text or ""


def set_ai_hashtags(text: str) -> None:
    _settings["hashtags"] = text or ""


def get_ai_settings() -> dict[str, str]:
    return {"prompt": get_ai_prompt(), "hashtags": get_ai_hashtags()}
