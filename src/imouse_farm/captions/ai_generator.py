"""Generate TikTok captions from gallery filenames via OpenAI."""

from __future__ import annotations

import json
import os
import random
import re
from typing import Any

from imouse_farm.config.models import OpenAICaptionConfig
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


def stem_to_food_name(stem: str) -> str:
    """Best-effort food label from a gallery MP4 stem (see ``_food_tokens_from_stem``)."""
    tokens = _food_tokens_from_stem(stem)
    if not tokens:
        return ""
    text = re.sub(r"[_\-]+", " ", " ".join(tokens))
    text = re.sub(r"\s+", " ", text).strip()
    return text.title() if text else ""


def _food_tokens_from_stem(stem: str) -> list[str]:
    """Pull food word tokens out of farm/slideshow export filenames."""
    parts = [p for p in str(stem or "").strip().split("-") if p]
    if not parts:
        return []

    if parts[0].lower() == "slideshow" and len(parts) >= 4:
        # slideshow-02-cup-noodles-3 → cup, noodles
        body = parts[2:-1] if parts[-1].isdigit() else parts[2:]
    elif len(parts) >= 3 and parts[0].isdigit() and parts[-1].isdigit():
        # 02-cup-noodles-3 → cup, noodles
        body = parts[1:-1]
    elif len(parts) >= 4 and parts[0].isdigit() and parts[1].isdigit():
        # 1-2-cup-noodles-a1b2c3 (batch ZIP export)
        body = parts[2:-1] if re.fullmatch(r"[0-9a-f]+", parts[-1]) else parts[2:]
    elif len(parts) >= 2:
        # legacy 1-chicken_tikka_masala
        body = parts[1:]
    else:
        return []

    skip = {"slideshow", "food", "coins", "mp4"}
    out = [p for p in body if p and p.lower() not in skip and not re.fullmatch(r"\d+", p)]
    return out


def food_to_hashtag_slug(food_name: str) -> str:
    """Lowercase alphanumeric slug for TikTok hashtags."""
    return re.sub(r"[^a-z0-9]", "", food_name.lower())


_PLACEHOLDER_FOODS = frozenset({
    "unknown",
    "n/a",
    "na",
    "none",
    "missing",
    "food",
    "generic",
})


def sanitize_food_name(food: str, stem: str = "") -> str:
    """Drop slideshow/slot noise; fall back to parsing the filename stem."""
    cleaned = str(food or "").strip()
    if cleaned:
        lower = cleaned.lower()
        if lower in _PLACEHOLDER_FOODS or "slideshow" in lower or re.fullmatch(r"post\s+\d+", lower):
            cleaned = ""
        elif re.fullmatch(r"[\d\s\-]+", cleaned):
            cleaned = ""
    if not cleaned and stem:
        cleaned = stem_to_food_name(stem)
    if cleaned:
        lower = cleaned.lower()
        if (
            lower in _PLACEHOLDER_FOODS
            or "slideshow" in lower
            or re.fullmatch(r"post\s+\d+", lower)
            or re.fullmatch(r"[\d\s\-]+", lower)
        ):
            return ""
    return cleaned


def food_for_post(
    *,
    extracted: str,
    response_food: str,
    stem: str,
) -> str:
    """Best food label for captions/hashtags: extracted name, then GPT, then filename."""
    if str(extracted or "").strip():
        cleaned = sanitize_food_name(extracted, stem)
        if cleaned:
            return cleaned
    if str(response_food or "").strip():
        cleaned = sanitize_food_name(response_food, stem)
        if cleaned:
            return cleaned
    return sanitize_food_name("", stem)


def resolve_hashtag_template(template: str, food_name: str) -> str:
    """Fill ``#______`` and ``#toxic_____`` placeholders from a food name."""
    slug = food_to_hashtag_slug(food_name)
    if slug in _PLACEHOLDER_FOODS or re.fullmatch(r"post\d+", slug):
        slug = ""
    text = template.strip()
    if slug:
        text = re.sub(r"#toxic_+", f"#toxic{slug}", text, flags=re.IGNORECASE)
        text = re.sub(r"#_+", f"#{slug}", text)
    else:
        text = re.sub(r"#toxic_+\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"#_+\s*", "", text)
    return normalize_hashtags(text)


def normalize_hashtags(raw: str, *, shuffle: bool = False) -> str:
    """Ensure hashtags are space-separated and start with #."""
    tags: list[str] = []
    for part in re.split(r"[\s,]+", raw.strip()):
        if not part:
            continue
        tag = part if part.startswith("#") else f"#{part.lstrip('#')}"
        if len(tag) > 1:
            tags.append(tag)
    if shuffle and len(tags) > 1:
        random.shuffle(tags)
    return " ".join(tags)


def sanitize_caption_statements(text: str) -> str:
    """Strip questions — captions must be confident statements only."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return cleaned
    cleaned = cleaned.replace("?", ".")
    cleaned = re.sub(r"\.\s*\.", ".", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def append_hashtags(caption: str, hashtags: str) -> str:
    """Append user hashtags to a final caption if not already present."""
    tags = normalize_hashtags(hashtags, shuffle=True)
    if not tags:
        return sanitize_caption_statements(caption)
    body = sanitize_caption_statements(caption)
    if not body:
        return tags
    if tags.lower() in body.lower():
        return body
    return f"{body}\n\n{tags}"


def _resolve_api_key(config: OpenAICaptionConfig) -> str:
    return (os.environ.get("OPENAI_API_KEY") or config.api_key or "").strip()


async def generate_post_captions(
    food_names: list[str],
    *,
    media_stems: list[str] | None = None,
    user_prompt: str,
    hashtags: str,
    config: OpenAICaptionConfig,
) -> list[dict[str, str]]:
    """Return ``[{food, final}, ...]`` for each post slot."""
    api_key = _resolve_api_key(config)
    if not api_key:
        raise ValueError("OpenAI API key not configured (set openai.api_key or OPENAI_API_KEY)")

    from openai import AsyncOpenAI

    foods = list(food_names)
    while len(foods) < 3:
        foods.append("")
    from imouse_farm.post.post_caption_store import stems_in_post_order

    post_stems = stems_in_post_order(list(media_stems or food_names))

    client = AsyncOpenAI(api_key=api_key)
    system = (
        "You write TikTok post descriptions for health conscious food content. "
        "Respond with valid JSON only: {\"posts\": [{\"food\": \"...\", \"final\": \"...\"}, ...]} "
        "with exactly 3 objects. "
        'Each "final" must be at most 4 short lines, all lowercase. No commas. '
        "Write confident statements only. Never ask questions. No question marks. "
        "Do NOT include hashtags in \"final\" — they are appended separately. "
        "Follow the user caption style instructions exactly (voice, Labely mention placement, tone)."
    )
    user = (
        f"Caption style instructions:\n{user_prompt.strip()}\n\n"
        "Each post already has a parsed food name — use it for that caption's \"food\" field "
        "and write the caption about that specific product:\n"
        f"- Post 1 — filename: {post_stems[0] or '(missing)'} — food: {foods[0] or '(unknown)'}\n"
        f"- Post 2 — filename: {post_stems[1] or '(missing)'} — food: {foods[1] or '(unknown)'}\n"
        f"- Post 3 — filename: {post_stems[2] or '(missing)'} — food: {foods[2] or '(unknown)'}\n\n"
        "Make each caption unique and tied to its food."
    )

    response = await client.chat.completions.create(
        model=config.model,
        temperature=config.temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": user
                + '\n\nReturn JSON: {"posts": [{"food": "...", "final": "..."}, ...]}',
            },
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    posts = _parse_posts_json(raw)
    result: list[dict[str, str]] = []
    for i in range(3):
        item = posts[i] if i < len(posts) else {}
        post_num = i + 1
        stem = post_stems[i]
        food = food_for_post(
            extracted=foods[i],
            response_food=str(item.get("food", "")).strip(),
            stem=stem,
        )
        tag_line = resolve_hashtag_template(hashtags, food)
        final = append_hashtags(str(item.get("final", "")).strip(), tag_line)
        result.append({"food": food, "final": final})
    logger.info("ai_captions_generated", posts=len(result), model=config.model)
    return result


async def generate_valcoin_post_captions(
    *,
    user_prompt: str,
    hashtags: str,
    config: OpenAICaptionConfig,
) -> list[dict[str, str]]:
    """Return ``[{food, final}, ...]`` for ValCoin — filenames ignored."""
    api_key = _resolve_api_key(config)
    if not api_key:
        raise ValueError("OpenAI API key not configured (set openai.api_key or OPENAI_API_KEY)")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    system = (
        "You write TikTok post descriptions for coin collecting content promoting ValCoin. "
        "Respond with valid JSON only: {\"posts\": [{\"food\": \"...\", \"final\": \"...\"}, ...]} "
        "with exactly 3 objects. "
        "Ignore any video filenames. Write about rare coins, quarters, and collector finds. "
        'Each "final" must be 35-80 words, all lowercase, viral hooks, line breaks, '
        "light emoji ok; do NOT include hashtags. "
        "Sound like a real Gen Z coin collector typing on their phone. "
        "Write confident statements only. Never ask questions. No question marks. "
        "No rhetorical questions or call-to-action questions. "
        "Never use hyphens or dashes in the caption text. "
        "Never use the word rich. "
        "Subtly mention ValCoin once per caption as the app used to scan or value coins. "
        "Never use promotional language: download, free, link in bio, promo, "
        "sponsored, ad, sale, discount."
    )
    user = (
        f"Caption style instructions:\n{user_prompt.strip()}\n\n"
        "Write 3 completely unique captions about different coin collecting moments. "
        "Do not reference filenames. Put a short topic label in each \"food\" field "
        "(e.g. Rare Quarter Find)."
    )

    response = await client.chat.completions.create(
        model=config.model,
        temperature=config.temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": user
                + '\n\nReturn JSON: {"posts": [{"food": "...", "final": "..."}, ...]}',
            },
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    posts = _parse_posts_json(raw)
    tag_line = normalize_hashtags(hashtags)
    result: list[dict[str, str]] = []
    for i in range(3):
        item = posts[i] if i < len(posts) else {}
        food = str(item.get("food", "")).strip() or f"Coin Find {i + 1}"
        final = append_hashtags(str(item.get("final", "")).strip(), tag_line)
        result.append({"food": food, "final": final})
    logger.info("ai_valcoin_captions_generated", posts=len(result), model=config.model)
    return result


def _parse_onscreen_json(raw: str) -> list[str]:
    data = json.loads(raw)
    if isinstance(data, dict):
        for key in ("onscreen", "overlays", "texts", "posts"):
            value = data.get(key)
            if isinstance(value, list):
                return [str(item).strip() for item in value[:3]]
    if isinstance(data, list):
        return [str(item).strip() for item in data[:3]]
    raise ValueError("OpenAI response missing onscreen array")


async def generate_valcoin_onscreen_texts(
    *,
    user_prompt: str,
    config: OpenAICaptionConfig,
) -> list[str]:
    """Return 3 unique on-screen overlay strings for ValCoin posts."""
    api_key = _resolve_api_key(config)
    if not api_key:
        raise ValueError("OpenAI API key not configured (set openai.api_key or OPENAI_API_KEY)")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    system = (
        "You write short on-screen text burned onto TikTok coin collecting videos. "
        "Respond with valid JSON only: {\"onscreen\": [\"...\", \"...\", \"...\"]} "
        "with exactly 3 strings in post order. "
        "Each string is 1-2 lines (use \\n for a line break). "
        "Title Case is ok for emphasis. Never use the word rich. "
        "Each overlay must be a unique variation on coin finds that can set someone up / "
        "change their life / make them loaded (without saying rich)."
    )
    user = f"On-screen text instructions:\n{user_prompt.strip()}"

    response = await client.chat.completions.create(
        model=config.model,
        temperature=config.temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": user + '\n\nReturn JSON: {"onscreen": ["...", "...", "..."]}',
            },
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    lines = _parse_onscreen_json(raw)
    while len(lines) < 3:
        lines.append("")
    logger.info("ai_valcoin_onscreen_generated", count=len(lines), model=config.model)
    return lines[:3]


def _parse_posts_json(raw: str) -> list[dict[str, Any]]:
    data = json.loads(raw)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("posts", "captions", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    raise ValueError("OpenAI response missing posts array")


def _parse_foods_json(raw: str) -> list[str]:
    data = json.loads(raw)
    foods_raw: list[Any]
    if isinstance(data, dict) and isinstance(data.get("foods"), list):
        foods_raw = data["foods"]
    elif isinstance(data, list):
        foods_raw = data
    else:
        raise ValueError("OpenAI response missing foods array")
    foods = [str(item).strip() for item in foods_raw[:3]]
    while len(foods) < 3:
        foods.append("")
    return foods


def _food_label_from_response(item: dict[str, Any], stem: str, post_index: int) -> str:
    _ = post_index
    return food_for_post(
        extracted="",
        response_food=str(item.get("food", "")).strip(),
        stem=stem,
    )


async def extract_food_names_from_stems(
    stems: list[str],
    *,
    config: OpenAICaptionConfig,
) -> list[str]:
    """Use OpenAI to read each gallery filename and return Title Case food names (post order)."""
    api_key = _resolve_api_key(config)
    if not api_key:
        raise ValueError("OpenAI API key not configured (set openai.api_key or OPENAI_API_KEY)")

    from openai import AsyncOpenAI
    from imouse_farm.post.post_caption_store import stems_in_post_order

    post_stems = stems_in_post_order(stems)

    client = AsyncOpenAI(api_key=api_key)
    system = (
        "You extract food product names from TikTok video filenames for health content. "
        "Respond with valid JSON only: {\"foods\": [\"...\", \"...\", \"...\"]} "
        "with exactly 3 strings in workflow post order (post 1, post 2, post 3). "
        "Each string is a short food product or category in Title Case "
        "(e.g. 'Cup Noodles', 'Chips', 'Frozen Pizza', 'Mac And Cheese'). "
        "Filenames may look like:\n"
        "- 02-cup-noodles-3 (phone slot 02, food cup-noodles, video 3)\n"
        "- slideshow-02-doritos-nacho-cheese-3\n"
        "- 1-2-chips-a1b2c3 (batch export — food is between batch index and random hex)\n"
        "- 1-chicken_tikka_masala (legacy — food after first hyphen)\n"
        "Parse the FOOD segment only. Ignore phone slot numbers, video indices, batch numbers, "
        "random hex tails, and the words slideshow, batch, food, mp4, or coins. "
        "Never return slideshow labels, slot numbers, or placeholders like 'Post 1'. "
        "If a filename has no recognizable food, return an empty string for that post."
    )
    user = (
        "Extract the food name from each post's video filename:\n"
        f"- Post 1 filename: {post_stems[0] or '(missing)'}\n"
        f"- Post 2 filename: {post_stems[1] or '(missing)'}\n"
        f"- Post 3 filename: {post_stems[2] or '(missing)'}\n"
    )

    response = await client.chat.completions.create(
        model=config.model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user + '\nReturn JSON: {"foods": ["...", "...", "..."]}'},
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    foods_raw = _parse_foods_json(raw)
    foods = [
        sanitize_food_name(foods_raw[i] if i < len(foods_raw) else "", post_stems[i])
        for i in range(3)
    ]
    logger.info(
        "ai_food_names_extracted",
        stems=post_stems,
        foods=foods,
        model=config.model,
    )
    return foods


def _onscreen_template_instructions(template_key: str) -> str:
    if template_key == "america_sick":
        return (
            'Template "america_sick": exactly two lines separated by \\n. '
            'Line 1: "This Is Why AMERICA IS SICK". '
            'Line 2: "{Food Category} Edition" where Food Category is Title Case food parsed '
            "from that post's filename (e.g. \"Chips Edition\", \"Cup Noodles Edition\")."
        )
    if template_key == "toxic_walmart":
        return (
            'Template "toxic_walmart": exactly two lines separated by \\n. '
            'Line 1: "The MOST Toxic {food} you should avoid" using the food from the filename. '
            'Line 2: "Walmart Edition".'
        )
    if template_key == "valcoin_receipt":
        return (
            'Template "valcoin_receipt": exactly two lines separated by \\n. '
            'Line 1: "The REAL Cost of {food}". Line 2: "ValCoin Edition".'
        )
    pattern = (
        "Template {key}: follow the on-screen layout for {food} from the filename."
    )
    return pattern.format(key=template_key, food="{food}")


async def generate_labely_onscreen_texts(
    stems: list[str],
    *,
    template_key: str,
    config: OpenAICaptionConfig,
) -> list[str]:
    """Return 3 on-screen overlay strings from gallery filenames (post order)."""
    api_key = _resolve_api_key(config)
    if not api_key:
        raise ValueError("OpenAI API key not configured (set openai.api_key or OPENAI_API_KEY)")

    from openai import AsyncOpenAI
    from imouse_farm.post.post_caption_store import stems_in_post_order

    post_stems = stems_in_post_order(stems)
    template_help = _onscreen_template_instructions(template_key)

    client = AsyncOpenAI(api_key=api_key)
    system = (
        "You write short on-screen text burned onto TikTok health-food slideshow videos. "
        "Respond with valid JSON only: {\"onscreen\": [\"...\", \"...\", \"...\"]} "
        "with exactly 3 strings in workflow post order (post 1, post 2, post 3). "
        "Each string is 1-2 lines (use \\n between lines). "
        "Read the food product or category from that post's video filename only. "
        "Never use the word slideshow, slot numbers, batch numbers, or video indices in the text. "
        f"{template_help}"
    )
    user = (
        "Write on-screen overlay text for each post from its filename:\n"
        f"- Post 1 filename: {post_stems[0] or '(missing)'}\n"
        f"- Post 2 filename: {post_stems[1] or '(missing)'}\n"
        f"- Post 3 filename: {post_stems[2] or '(missing)'}\n"
    )

    response = await client.chat.completions.create(
        model=config.model,
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": user + '\nReturn JSON: {"onscreen": ["...", "...", "..."]}',
            },
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    lines = _parse_onscreen_json(raw)
    while len(lines) < 3:
        lines.append("")
    result: list[str] = []
    for i in range(3):
        line = lines[i].strip()
        if not line or "slideshow" in line.lower():
            fallback_food = sanitize_food_name("", post_stems[i])
            from imouse_farm.captions.onscreen_templates import build_onscreen_text

            line = build_onscreen_text(template_key, fallback_food)
        result.append(line)
    logger.info(
        "ai_labely_onscreen_generated",
        template=template_key,
        stems=post_stems,
        model=config.model,
    )
    return result[:3]
