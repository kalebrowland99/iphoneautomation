"""Per-brand AI caption prompt and hashtag settings (dashboard-editable, persisted)."""

from __future__ import annotations

import json
from pathlib import Path

from imouse_farm.post.brand_keys import VALID_BRANDS

CAPTION_AI_SETTINGS_PATH = Path("data/caption_ai_settings.json")

DEFAULT_AI_PROMPT = """\
each post has a video filename that names the food. underscores and hyphens in the filename separate words. read the raw filename first then grab the food from the second hyphen chunk.

voice: write like gen z is literally typing the caption on their phone. all lowercase. no title case. not polished. not essay voice. short punchy lines. run on thoughts. internet cadence. casual and a little chaotic. like ur venting to a friend in the comments. imperfect grammar is fine. light slang when it fits (ngl lowkey literally tbh idk fr) but dont force it every sentence or it sounds fake.

structure: at most 4 lines total. mention labely naturally within the first 2 lines. labely is what u use to scan barcodes and see whats really in products before u eat. name it once like ur telling a friend what helped u figure this out. never use words like app download free link promo sponsored ad or sale.

health conscious tiktok that still goes viral. hook first. talk about sketchy ingredients microplastics carcinogens stuff labels bury in tiny print. curious slightly unsettling not preachy.

use statements and facts only. never ask questions. no question marks. tell it like something u noticed scanned or realized about this specific food.

do not use hyphens dashes or commas anywhere in the caption. periods only.

each caption must be unique. tie it directly to the food from that posts filename."""

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
