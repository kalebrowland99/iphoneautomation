"""Generate TikTok captions from gallery filenames via OpenAI."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from imouse_farm.config.models import OpenAICaptionConfig
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


def stem_to_food_name(stem: str) -> str:
    """Food name is the second hyphen-separated segment of the gallery filename stem."""
    parts = stem.strip().split("-")
    if len(parts) < 2:
        return ""
    text = re.sub(r"[_\-]+", " ", parts[1].strip())
    text = re.sub(r"\s+", " ", text)
    return text.title() if text else ""


def food_to_hashtag_slug(food_name: str) -> str:
    """Lowercase alphanumeric slug for TikTok hashtags."""
    return re.sub(r"[^a-z0-9]", "", food_name.lower())


def resolve_hashtag_template(template: str, food_name: str) -> str:
    """Fill ``#______`` and ``#toxic_____`` placeholders from a food name."""
    slug = food_to_hashtag_slug(food_name)
    text = template.strip()
    if slug:
        text = re.sub(r"#toxic_+", f"#toxic{slug}", text, flags=re.IGNORECASE)
        text = re.sub(r"#_+", f"#{slug}", text)
    else:
        text = re.sub(r"#toxic_+\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"#_+\s*", "", text)
    return normalize_hashtags(text)


def normalize_hashtags(raw: str) -> str:
    """Ensure hashtags are space-separated and start with #."""
    tags: list[str] = []
    for part in re.split(r"[\s,]+", raw.strip()):
        if not part:
            continue
        tag = part if part.startswith("#") else f"#{part.lstrip('#')}"
        if len(tag) > 1:
            tags.append(tag)
    return " ".join(tags)


def append_hashtags(caption: str, hashtags: str) -> str:
    """Append user hashtags to a final caption if not already present."""
    tags = normalize_hashtags(hashtags)
    if not tags:
        return caption.strip()
    body = caption.strip()
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
    user_prompt: str,
    hashtags: str,
    config: OpenAICaptionConfig,
) -> list[dict[str, str]]:
    """Return ``[{food, final}, ...]`` for each post slot."""
    api_key = _resolve_api_key(config)
    if not api_key:
        raise ValueError("OpenAI API key not configured (set openai.api_key or OPENAI_API_KEY)")

    from openai import AsyncOpenAI

    raw_stems = list(food_names)
    while len(raw_stems) < 3:
        raw_stems.append("")

    client = AsyncOpenAI(api_key=api_key)
    system = (
        "You write TikTok post descriptions for health conscious food content. "
        "Respond with valid JSON only: {\"posts\": [{\"food\": \"...\", \"final\": \"...\"}, ...]} "
        "with exactly 3 objects. "
        "For each post, \"food\" is the Title Case food name extracted from that post's video filename. "
        'Each "final" must be 120-280 words, all lowercase, viral hooks, line breaks, '
        "light emoji ok; do NOT include hashtags. "
        "Sound like a real Gen Z person typing the caption on their phone: casual, punchy, "
        "internet cadence, imperfect grammar ok, never corporate or essay-like. "
        "Read each post's raw video filename to identify the food. "
        "Write statements and facts only with a personal anecdote tone. "
        "Never ask questions. No question marks. "
        "Never use hyphens or dashes in the caption text. "
        "Never use promotional language: app, download, free, link in bio, promo, "
        "sponsored, ad, sale, discount."
    )
    user = (
        f"Caption style instructions:\n{user_prompt.strip()}\n\n"
        "Video filenames (one row per post — use each filename as the source of truth "
        "for which food that post is about; put the parsed food in the \"food\" field):\n"
        f"- Post 1 — filename: {raw_stems[0] or '(missing)'}\n"
        f"- Post 2 — filename: {raw_stems[1] or '(missing)'}\n"
        f"- Post 3 — filename: {raw_stems[2] or '(missing)'}\n\n"
        "Make each caption unique. Base every caption on that post's filename/food."
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
        food = _food_label_from_response(item, raw_stems[i], post_num)
        tag_line = resolve_hashtag_template(hashtags, food)
        final = append_hashtags(str(item.get("final", "")).strip(), tag_line)
        result.append({"food": food, "final": final})
    logger.info("ai_captions_generated", posts=len(result), model=config.model)
    return result


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
    food = str(item.get("food", "")).strip()
    if not food:
        food = stem_to_food_name(stem)
    if not food:
        food = f"Post {post_index}"
    return food


async def extract_food_names_from_stems(
    stems: list[str],
    *,
    config: OpenAICaptionConfig,
) -> list[str]:
    """Use OpenAI to read each gallery filename and return Title Case food names."""
    api_key = _resolve_api_key(config)
    if not api_key:
        raise ValueError("OpenAI API key not configured (set openai.api_key or OPENAI_API_KEY)")

    from openai import AsyncOpenAI

    padded = list(stems)
    while len(padded) < 3:
        padded.append("")

    client = AsyncOpenAI(api_key=api_key)
    system = (
        "You extract food names from TikTok video filenames for health content. "
        "Respond with valid JSON only: {\"foods\": [\"...\", \"...\", \"...\"]} "
        "with exactly 3 strings in post order. "
        "Each string is the human readable food name in Title Case "
        "(e.g. 'Chicken Tikka Masala') parsed from that post's filename. "
        "Filenames often look like '1-chicken_tikka_masala' or 'post-mac_and_cheese' "
        "where the food is after the first hyphen. Use the filename as source of truth. "
        "If a filename is missing or has no food, return an empty string for that slot."
    )
    user = (
        "Extract the food name from each filename:\n"
        f"- Post 1 filename: {padded[0] or '(missing)'}\n"
        f"- Post 2 filename: {padded[1] or '(missing)'}\n"
        f"- Post 3 filename: {padded[2] or '(missing)'}\n"
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
    foods = _parse_foods_json(raw)
    logger.info("ai_food_names_extracted", stems=padded[:3], foods=foods, model=config.model)
    return foods
