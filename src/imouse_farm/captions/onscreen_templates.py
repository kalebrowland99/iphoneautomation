"""Onscreen text templates filled from gallery food names."""

from __future__ import annotations

from imouse_farm.post.post_caption_store import POST_COUNT, media_index_for_post, post_media_stem

ONSCREEN_TEMPLATES: dict[str, str] = {
    "toxic_walmart": "The MOST Toxic {food} you should avoid\nWalmart Edition",
    "america_sick": "This Is Why AMERICA IS SICK\n{food} Edition",
    "valcoin_receipt": "The REAL Cost of {food}\nValCoin Edition",
}


def _format_food_edition(food_name: str) -> str:
    """Capitalize the food name's first letter and append `` Edition``."""
    food = food_name.strip()
    if not food:
        return ""
    return f"{food[0].upper()}{food[1:]} Edition"


def build_onscreen_text(template_key: str, food_name: str) -> str:
    food = food_name.strip()
    if not food:
        return ""
    if template_key == "america_sick":
        return f"This Is Why AMERICA IS SICK\n{_format_food_edition(food)}"
    if template_key == "valcoin_receipt":
        return f"The REAL Cost of {food}\nValCoin Edition"
    pattern = ONSCREEN_TEMPLATES.get(template_key)
    if not pattern:
        return ""
    return pattern.format(food=food)


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
