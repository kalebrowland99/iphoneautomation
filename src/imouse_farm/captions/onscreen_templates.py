"""Onscreen text templates filled from gallery food names."""

from __future__ import annotations

import random
import re

from imouse_farm.post.post_caption_store import POST_COUNT, media_index_for_post, post_media_stem

ONSCREEN_TEMPLATES: dict[str, str] = {
    "toxic_walmart": "MOST Toxic {food} you should avoid\nWalmart Edition",
    "america_sick": "This Is Why AMERICA IS SICK\n{food} Edition",
    "valcoin_receipt": "REAL Cost of {food}\nValCoin Edition",
}

# Line-1 hook families — same recognizable hook each batch, slight wording shift per run.
_HOOK_LINE1_VARIATIONS: dict[str, list[str]] = {
    "america_sick": [
        "This Is Why AMERICA IS SICK",
        "This Is Why America Is SO Sick",
        "Why AMERICA Is SICK",
        "This Is Why AMERICA Got SICK",
        "This Is How AMERICA Got SICK",
        "This Is Why America Keeps Getting SICK",
    ],
    "toxic_walmart": [
        "MOST Toxic {food} you should avoid",
        "Most Toxic {food} To Avoid",
        "Avoid MOST Toxic {food}",
        "MOST Toxic {food} At Walmart",
        "Stop Buying This Toxic {food}",
    ],
    "valcoin_receipt": [
        "REAL Cost of {food}",
        "True Cost of {food}",
        "What {food} Really Costs",
        "HIDDEN Cost of {food}",
    ],
}

_LINE2_FIXED: dict[str, str] = {
    "toxic_walmart": "Walmart Edition",
    "valcoin_receipt": "ValCoin Edition",
}

# Line-2 edition suffixes for america_sick — negative framing, slight wording shift per post.
_FOOD_EDITION_VARIATIONS: list[str] = [
    "Toxic {food} Edition",
    "Super Toxic {food} Edition",
    "Unhealthy {food} Edition",
    "Dangerous {food} Edition",
    "Seriously Unhealthy {food} Edition",
    "Harmful {food} Edition",
    "Fake {food} Edition",
    "Sketchy {food} Edition",
    "Worst {food} Edition",
    "Ultra Processed {food} Edition",
]

_NEGATIVE_EDITION_MARKERS = (
    "toxic",
    "unhealthy",
    "dangerous",
    "harmful",
    "fake",
    "sketchy",
    "worst",
    "processed",
)


def _strip_the_word(text: str) -> str:
    """Remove standalone ``the`` from on-screen overlay copy."""
    cleaned = re.sub(r"\b[Tt]he\b", "", text)
    cleaned = re.sub(r"  +", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    return cleaned.strip()


def _title_case_food(food_name: str) -> str:
    food = food_name.strip()
    if not food:
        return ""
    return f"{food[0].upper()}{food[1:]}"


def _format_food_edition(food_name: str) -> str:
    """Capitalize the food name and append a negative edition label."""
    food = _title_case_food(food_name)
    if not food:
        return ""
    return f"Toxic {food} Edition"


def _edition_has_negative_wording(edition_line: str) -> bool:
    lower = edition_line.lower()
    return any(marker in lower for marker in _NEGATIVE_EDITION_MARKERS)


def _format_food_edition_varied(
    food_name: str,
    *,
    rng: random.Random | None = None,
) -> str:
    food = _title_case_food(food_name)
    if not food:
        return ""
    pattern = (rng or random.Random()).choice(_FOOD_EDITION_VARIATIONS)
    return _strip_the_word(pattern.format(food=food))


def build_onscreen_text(template_key: str, food_name: str) -> str:
    food = food_name.strip()
    if not food:
        return ""
    if template_key == "america_sick":
        return _strip_the_word(f"This Is Why AMERICA IS SICK\n{_format_food_edition(food)}")
    if template_key == "valcoin_receipt":
        return _strip_the_word(f"REAL Cost of {food}\nValCoin Edition")
    pattern = ONSCREEN_TEMPLATES.get(template_key)
    if not pattern:
        return ""
    return _strip_the_word(pattern.format(food=food))


def pick_hook_line1(template_key: str, *, rng: random.Random | None = None) -> str:
    """Pick one hook pattern for a template (shared across posts in a batch)."""
    options = _HOOK_LINE1_VARIATIONS.get(template_key)
    if not options:
        pattern = ONSCREEN_TEMPLATES.get(template_key, "")
        return pattern.split("\n", 1)[0] if pattern else ""
    return (rng or random.Random()).choice(options)


def build_varied_onscreen_text(
    template_key: str,
    food_name: str,
    *,
    hook_line1: str | None = None,
    rng: random.Random | None = None,
) -> str:
    """Build on-screen text using a canonical hook with a slight variation."""
    food = food_name.strip()
    if not food:
        return ""

    hook = (hook_line1 or pick_hook_line1(template_key, rng=rng)).strip()
    if not hook:
        return build_onscreen_text(template_key, food)

    if template_key == "america_sick":
        return _strip_the_word(f"{hook}\n{_format_food_edition_varied(food, rng=rng)}")

    line2 = _LINE2_FIXED.get(template_key)
    if line2:
        return _strip_the_word(f"{hook.format(food=food)}\n{line2}")

    return build_onscreen_text(template_key, food)


def build_varied_onscreen_texts(
    template_key: str,
    food_names: list[str],
    *,
    rng: random.Random | None = None,
) -> list[str]:
    """Return one varied overlay per food, sharing the same hook pattern in the batch."""
    rng = rng or random.Random()
    hook = pick_hook_line1(template_key, rng=rng)
    texts: list[str] = []
    for food in food_names:
        texts.append(build_varied_onscreen_text(template_key, food, hook_line1=hook, rng=rng))
    while len(texts) < POST_COUNT:
        texts.append("")
    return texts[:POST_COUNT]


def apply_onscreen_for_foods(
    template_key: str,
    food_names_by_file: list[str],
    device_key: str,
    *,
    set_onscreen_text,
) -> int:
    """Fill onscreen text using food names in gallery file order (maps to workflow posts)."""
    applied = 0
    for post in range(1, POST_COUNT + 1):
        idx = media_index_for_post(post)
        food = food_names_by_file[idx] if idx < len(food_names_by_file) else ""
        text = build_onscreen_text(template_key, food)
        if not text:
            continue
        set_onscreen_text(device_key, post, text)
        applied += 1
    return applied


def apply_onscreen_for_stems(
    template_key: str,
    stems: list[str],
    device_key: str,
    *,
    set_onscreen_text,
    food_names: list[str] | None = None,
) -> int:
    """Fill onscreen text for each post. Prefer ``food_names`` when provided."""
    if food_names is not None:
        return apply_onscreen_for_foods(
            template_key, food_names, device_key, set_onscreen_text=set_onscreen_text
        )
    from imouse_farm.captions.ai_generator import stem_to_food_name
    from imouse_farm.post.post_caption_store import foods_post_order_to_file_order

    names_by_post: list[str] = []
    for post in range(1, POST_COUNT + 1):
        stem = post_media_stem(stems, post)
        names_by_post.append(stem_to_food_name(stem) if stem else "")
    names = foods_post_order_to_file_order(names_by_post)
    return apply_onscreen_for_foods(
        template_key, names, device_key, set_onscreen_text=set_onscreen_text
    )
