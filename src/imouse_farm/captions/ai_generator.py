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
    """Turn a filename stem like ``chicken_tikka_masala`` into readable text."""
    text = re.sub(r"[_\-]+", " ", stem.strip())
    text = re.sub(r"\s+", " ", text)
    return text.title() if text else ""


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
    """Return ``[{final}, ...]`` for each post slot (onscreen text is manual)."""
    api_key = _resolve_api_key(config)
    if not api_key:
        raise ValueError("OpenAI API key not configured (set openai.api_key or OPENAI_API_KEY)")

    from openai import AsyncOpenAI

    labels = [stem_to_food_name(n) or f"Post {i + 1}" for i, n in enumerate(food_names)]
    raw_stems = list(food_names)
    while len(labels) < 3:
        labels.append(f"Post {len(labels) + 1}")
        raw_stems.append("")

    client = AsyncOpenAI(api_key=api_key)
    system = (
        "You write TikTok post descriptions for health conscious food content. "
        "Respond with valid JSON only: {\"posts\": [{\"final\": \"...\"}, ...]} "
        "with exactly 3 objects. "
        'Each "final" must be 120-280 words, all lowercase, viral hooks, line breaks, '
        "light emoji ok; do NOT include hashtags. "
        "Read each post's raw video filename to identify the food. "
        "Write statements and facts only with a personal anecdote tone. "
        "Never ask questions. No question marks. "
        "Never use hyphens or dashes in the caption text. "
        "Never use promotional language: app, download, free, link in bio, promo, "
        "sponsored, ad, sale, discount."
    )
    user = (
        f"Caption style instructions:\n{user_prompt.strip()}\n\n"
        "Video filenames and parsed food names (one row per post — use the filename "
        "as the source of truth for which food this post is about):\n"
        f"- Post 1 — filename: {raw_stems[0] or '(missing)'} → food: {labels[0]}\n"
        f"- Post 2 — filename: {raw_stems[1] or '(missing)'} → food: {labels[1]}\n"
        f"- Post 3 — filename: {raw_stems[2] or '(missing)'} → food: {labels[2]}\n\n"
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
                "content": user + '\n\nReturn JSON: {"posts": [{"final": "..."}, ...]}',
            },
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    posts = _parse_posts_json(raw)
    tag_line = normalize_hashtags(hashtags)
    result: list[dict[str, str]] = []
    for i in range(3):
        item = posts[i] if i < len(posts) else {}
        final = append_hashtags(str(item.get("final", "")).strip(), tag_line)
        result.append({"final": final})
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
