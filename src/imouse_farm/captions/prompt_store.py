"""In-memory AI caption prompt and hashtag settings (dashboard-editable)."""

from __future__ import annotations

DEFAULT_AI_PROMPT = """\
each post has a video filename that names the food. underscores and hyphens in the filename separate words. read the raw filename first, then grab the food from the second hyphen chunk.

voice: write like gen z is literally typing the caption on their phone. all lowercase. no title case. not polished. not essay voice. short punchy lines, run on thoughts, internet cadence. casual, a little chaotic, relatable, like ur venting to a friend in the comments. imperfect grammar is fine. light slang when it fits (ngl, lowkey, literally, tbh, idk, fr) but dont force it every sentence or it sounds fake.

health conscious tiktok that still goes viral. hook first. talk about sketchy ingredients, microplastics, carcinogens, stuff labels bury in tiny print. curious, slightly unsettling, not preachy.

use statements and facts only. never ask questions. no question marks. tell it like something u noticed, scanned, or realized about this specific food.

do not use hyphens or dashes anywhere in the caption. use commas and periods instead.

work in one soft, natural mention of labely, what u use to scan barcodes and see whats really in products before u eat. never use words like app, download, free, link, promo, sponsored, ad, or sale. just name labely once like ur telling a friend what helped u figure it out.

each caption must be unique. tie it directly to the food from that posts filename."""

DEFAULT_AI_HASHTAGS = "#______ #toxic_____ #toxinfree #groceryshopping #cleaningredients"

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
