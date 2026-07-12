"""Per-brand AI caption prompt and hashtag settings (dashboard-editable, persisted)."""

from __future__ import annotations

import json
from pathlib import Path

from imouse_farm.post.brand_keys import VALID_BRANDS

CAPTION_AI_SETTINGS_PATH = Path("data/caption_ai_settings.json")

DEFAULT_AI_PROMPT = """\
each post has a video filename that names the food. underscores and hyphens in the filename separate words. read the raw filename first, then write about that specific food.

voice: health girly tiktok sales copy. feminine wellness energy, warm and real, but write as short persuasive copy that sells labely as the answer. sound like a friend who just found out what is really in her groceries and finally has a way to check before she buys.

sound human, not ai:
- be specific and concrete. name real label details (grams of sugar, red dye 40, seed oil, sodium, corn syrup, etc.) instead of vague hype.
- never use ai clichés or filler hype. banned phrases include: off the charts, game changer, let that sink in, it's giving, sneakily, hidden dangers, in today's world, wake up call, did you know, here's the thing, the truth is, blow your mind, absolutely wild, kinda crazy, lowkey (as empty filler), literally (as empty filler).
- use the word "like" at most once per caption. do not stack filler ("like literally", "like lowkey", etc.). prefer direct statements.

structure (pain → agitate → solution):
1. hook with a pain point tied to this exact food (hidden seed oils, dyes, preservatives, ultra-processed junk, misleading "healthy" labels, microplastics, etc.).
2. agitate: why it matters for your body, energy, gut, skin, or peace of mind. make the problem feel real without fear-mongering clichés.
3. solution: position labely as what you use to scan barcodes and see what is actually in products before you eat or buy. labely is the fix — clarity, truth, control at the store.
4. close with a confident benefit (you do not have to guess anymore, you can shop smarter, you know what you are putting in your body).

length: longer is fine. aim for about 5–10 sentences, or up to 6–8 short lines. not a wall of text, but enough room to sell.

punctuation: use correct punctuation. commas and periods are good. write clean, readable sentences.

rules:
- mention labely once, naturally, as the app you use / trust / scanned with — not a hard ad.
- never use: download, free, link in bio, promo, sponsored, ad, sale, or discount.
- statements only. never ask questions. no question marks.
- mostly lowercase tiktok cadence is fine, but prioritize clarity and readable sales copy.
- each caption must be unique and tied directly to the food from that post's filename."""

DEFAULT_AI_HASHTAGS = "#______ #toxic_____ #toxinfree #groceryshopping #cleaningredients"

DEFAULT_VALCOIN_AI_PROMPT = """\
ignore video filenames completely. do not reference or parse them.

voice: gen z, all lowercase, short punchy lines, internet cadence, not polished. casual and a little chaotic, like ur texting a friend who collects coins.

angle: coin collecting and rare finds. quarters, pocket change, coins worth way more than people think. hook first. hype energy without sounding like a scam. write variations on these coins can set u up, change ur whole month, blow up ur collection, etc. never use the word rich.

use confident statements only. never ask questions. no question marks. no rhetorical questions.

do not use hyphens or dashes in the caption. commas and periods only.

subtly promote valcoin once per caption, like the app u use to scan coins, check values, and spot hidden worth in ur change. name valcoin naturally like ur telling a friend what u use. never say download, free, link in bio, promo, sponsored, ad, or sale.

each caption must be unique. write about different coin finds, quarters, or collector moments. do not tie captions to any filename."""

DEFAULT_VALCOIN_ONSCREEN_PROMPT = """\
write 3 unique on screen overlay texts for coin collecting tiktoks.
each overlay is a short punchy variation on the vibe of these coin finds will make you rich.
never use the word rich. use loaded, set for life, change everything, life changing, etc. instead.
1 to 2 lines per overlay. use a newline between lines when needed.
coin collector energy. each post must be completely different."""

DEFAULT_VALCOIN_AI_HASHTAGS = "#coincollector #coincollection #quarter #coins"

_BRAND_DEFAULTS: dict[str, dict[str, str]] = {
    "labely": {"prompt": DEFAULT_AI_PROMPT, "hashtags": DEFAULT_AI_HASHTAGS},
    "valcoin": {
        "prompt": DEFAULT_VALCOIN_AI_PROMPT,
        "hashtags": DEFAULT_VALCOIN_AI_HASHTAGS,
    },
}

_settings: dict[str, dict[str, str]] = {
    brand: dict(values) for brand, values in _BRAND_DEFAULTS.items()
}


def _normalize_brand(brand: str) -> str:
    b = str(brand or "labely").strip().lower()
    return b if b in VALID_BRANDS else "labely"


def _brand_settings(brand: str) -> dict[str, str]:
    b = _normalize_brand(brand)
    if b not in _settings:
        _settings[b] = dict(_BRAND_DEFAULTS.get(b, _BRAND_DEFAULTS["labely"]))
    return _settings[b]


def _load_settings() -> None:
    global _settings
    if not CAPTION_AI_SETTINGS_PATH.exists():
        return
    try:
        raw = json.loads(CAPTION_AI_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(raw, dict):
        return
    if "prompt" in raw or "hashtags" in raw:
        _settings = {brand: dict(values) for brand, values in _BRAND_DEFAULTS.items()}
        _settings["labely"] = {
            "prompt": str(raw.get("prompt", DEFAULT_AI_PROMPT)).strip() or DEFAULT_AI_PROMPT,
            "hashtags": str(raw.get("hashtags", DEFAULT_AI_HASHTAGS)).strip() or DEFAULT_AI_HASHTAGS,
        }
        return
    loaded: dict[str, dict[str, str]] = {}
    for brand_id, values in raw.items():
        if brand_id not in VALID_BRANDS or not isinstance(values, dict):
            continue
        defaults = _BRAND_DEFAULTS.get(brand_id, _BRAND_DEFAULTS["labely"])
        prompt = str(values.get("prompt", defaults["prompt"])).strip()
        hashtags = str(values.get("hashtags", defaults["hashtags"])).strip()
        loaded[brand_id] = {
            "prompt": prompt or defaults["prompt"],
            "hashtags": hashtags or defaults["hashtags"],
        }
    if loaded:
        _settings = {**{b: dict(v) for b, v in _BRAND_DEFAULTS.items()}, **loaded}


def _save_settings() -> None:
    CAPTION_AI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        brand: {"prompt": data["prompt"], "hashtags": data["hashtags"]}
        for brand, data in _settings.items()
        if brand in VALID_BRANDS
    }
    CAPTION_AI_SETTINGS_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_ai_prompt(brand: str = "labely") -> str:
    return _brand_settings(brand)["prompt"]


def get_ai_hashtags(brand: str = "labely") -> str:
    return get_ai_settings(brand)["hashtags"]


def set_ai_prompt(text: str, brand: str = "labely") -> None:
    _brand_settings(brand)["prompt"] = text or ""
    _save_settings()


def set_ai_hashtags(text: str, brand: str = "labely") -> None:
    b = _normalize_brand(brand)
    defaults = _BRAND_DEFAULTS.get(b, _BRAND_DEFAULTS["labely"])
    _brand_settings(brand)["hashtags"] = str(text or "").strip() or defaults["hashtags"]
    _save_settings()


def get_ai_settings(brand: str = "labely") -> dict[str, str]:
    data = _brand_settings(brand)
    defaults = _BRAND_DEFAULTS.get(_normalize_brand(brand), _BRAND_DEFAULTS["labely"])
    prompt = str(data["prompt"]).strip() or defaults["prompt"]
    hashtags = str(data["hashtags"]).strip() or defaults["hashtags"]
    out = {"prompt": prompt, "hashtags": hashtags}
    if _normalize_brand(brand) == "valcoin":
        out["onscreen_prompt"] = DEFAULT_VALCOIN_ONSCREEN_PROMPT
    return out


def get_valcoin_onscreen_prompt() -> str:
    return DEFAULT_VALCOIN_ONSCREEN_PROMPT


_load_settings()
