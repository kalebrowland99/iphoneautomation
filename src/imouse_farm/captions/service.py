"""Generate and apply captions for one or all farm devices."""

from __future__ import annotations

from typing import Any

from imouse_farm.captions.ai_generator import (
    extract_food_names_from_stems,
    generate_labely_onscreen_texts,
    generate_post_captions,
    generate_valcoin_onscreen_texts,
    generate_valcoin_post_captions,
    stem_to_food_name,
)
from imouse_farm.captions.prompt_store import get_ai_settings, get_valcoin_onscreen_prompt
from imouse_farm.config.models import AppConfig, OpenAICaptionConfig
from imouse_farm.post.post_caption_store import (
    POST_COUNT,
    get_final_caption,
    get_onscreen_text,
    post_media_stem,
    set_final_caption,
    set_onscreen_text,
    text_key_for_device,
)
from imouse_farm.utils.gallery import list_media_stems_for_posts, phone_gallery_folder
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


def _gallery_stems(config: AppConfig, device: Any, brand: str = "labely") -> list[str]:
    gallery = config.gallery
    folder = phone_gallery_folder(
        gallery.base_directory,
        device.user_name,
        device.phone_name,
        brand=brand,
    )
    return list_media_stems_for_posts(folder, gallery.media_extensions, POST_COUNT)


async def generate_captions_for_device(
    config: AppConfig,
    device: Any,
    *,
    prompt: str | None = None,
    hashtags: str | None = None,
    onscreen_template: str | None = None,
    brand: str = "labely",
    persist: bool = True,
) -> dict[str, Any]:
    """Generate unique final captions per post; optional onscreen template per device."""
    openai_cfg = config.openai
    if not openai_cfg.enabled:
        raise ValueError("OpenAI caption generation is disabled in config")

    brand_key = str(brand or "labely").strip().lower()
    settings = get_ai_settings(brand_key)
    prompt_text = (prompt if prompt is not None else settings["prompt"]).strip()
    if not prompt_text:
        prompt_text = settings["prompt"]
    explicit_hashtags = (hashtags if hashtags is not None else "").strip()
    hashtags_text = explicit_hashtags or settings["hashtags"]

    media_stems = _gallery_stems(config, device, brand_key)
    if not any(media_stems):
        raise ValueError(
            f"No media files in gallery for Phone {device.user_name or device.device_id}"
        )

    text_key = text_key_for_device(device.device_id, device.user_name, brand=brand_key)
    food_names: list[str] = []

    if brand_key == "valcoin":
        generated = await generate_valcoin_post_captions(
            user_prompt=prompt_text,
            hashtags=hashtags_text,
            config=openai_cfg,
        )
        onscreen_lines = await generate_valcoin_onscreen_texts(
            user_prompt=get_valcoin_onscreen_prompt(),
            config=openai_cfg,
        )
    else:
        food_names = await extract_food_names_from_stems(media_stems, config=openai_cfg)
        generated = await generate_post_captions(
            food_names,
            media_stems=media_stems,
            user_prompt=prompt_text,
            hashtags=hashtags_text,
            config=openai_cfg,
        )
        onscreen_lines = []

    template_key = (onscreen_template or "").strip()
    if template_key and brand_key == "labely":
        onscreen_lines = await generate_labely_onscreen_texts(
            media_stems,
            template_key=template_key,
            config=openai_cfg,
            food_names=food_names,
        )
        if persist:
            for post_num, line in enumerate(onscreen_lines, start=1):
                if line.strip():
                    set_onscreen_text(text_key, post_num, line, brand=brand_key)

    def _onscreen_for_post(post_num: int, cap_index: int) -> str:
        if brand_key == "valcoin":
            idx = cap_index - 1
            return onscreen_lines[idx] if idx < len(onscreen_lines) else ""
        if onscreen_lines and post_num - 1 < len(onscreen_lines):
            return str(onscreen_lines[post_num - 1] or "")
        if persist:
            return get_onscreen_text(text_key, post_num, brand=brand_key)
        return ""

    posts: list[dict[str, Any]] = []
    for i, cap in enumerate(generated, start=1):
        post_num = POST_COUNT + 1 - i
        onscreen = _onscreen_for_post(post_num, i)
        if persist:
            set_final_caption(text_key, post_num, cap["final"], brand=brand_key)
            if brand_key == "valcoin" and onscreen.strip():
                set_onscreen_text(text_key, post_num, onscreen, brand=brand_key)
        stem = post_media_stem(media_stems, post_num)
        posts.append({
            "post": post_num,
            "onscreen": onscreen if not persist else get_onscreen_text(text_key, post_num, brand=brand_key),
            "final": cap["final"],
            "media_file": stem,
            "food_name": (
                cap.get("food")
                or (food_names[post_num - 1] if post_num - 1 < len(food_names) else "")
                or stem_to_food_name(stem)
            ),
        })

    return {
        "device_id": device.device_id,
        "slot": device.user_name,
        "label": device.display_label,
        "text_key": text_key,
        "brand": brand_key,
        "posts": sorted(posts, key=lambda row: int(row["post"])),
        "media_files": media_stems,
        "preview": not persist,
    }


def default_onscreen_template_for_brand(brand: str, template: str | None = None) -> str | None:
    explicit = str(template or "").strip()
    if explicit:
        return explicit
    b = str(brand or "").strip().lower()
    if b == "labely":
        return "america_sick"
    if b == "valcoin":
        return None
    return None


async def generate_captions_for_devices(
    config: AppConfig,
    devices: list[Any],
    *,
    prompt: str | None = None,
    hashtags: str | None = None,
    onscreen_template: str | None = None,
    brand: str = "labely",
) -> dict[str, Any]:
    """Generate AI captions for many farm phones (continues past individual failures)."""
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    template = default_onscreen_template_for_brand(brand, onscreen_template)

    for device in devices:
        try:
            result = await generate_captions_for_device(
                config,
                device,
                prompt=prompt,
                hashtags=hashtags,
                onscreen_template=template,
                brand=brand,
            )
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "caption_generate_device_failed",
                slot=str(device.user_name),
                error=str(exc),
            )
            errors.append({
                "slot": str(device.user_name),
                "device_id": device.device_id,
                "error": str(exc),
            })

    return {
        "success": len(results) > 0,
        "generated": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
    }


def farm_devices_sorted(device_manager: Any) -> list[Any]:
    """Registered devices with a farm slot (user_name), sorted numerically."""

    def _slot_key(device: Any) -> tuple[int, str]:
        raw = str(device.user_name or "").strip()
        try:
            return (int(raw), raw)
        except ValueError:
            return (9999, raw)

    devices = [
        d
        for d in device_manager.devices.values()
        if str(d.user_name or "").strip()
    ]
    return sorted(devices, key=_slot_key)
