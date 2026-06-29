"""Generate and apply captions for one or all farm devices."""

from __future__ import annotations

from typing import Any

from imouse_farm.captions.ai_generator import generate_post_captions, stem_to_food_name
from imouse_farm.captions.onscreen_templates import apply_onscreen_for_stems
from imouse_farm.captions.prompt_store import get_ai_settings
from imouse_farm.config.models import AppConfig, OpenAICaptionConfig
from imouse_farm.post.post_caption_store import (
    POST_COUNT,
    device_storage_key,
    get_final_caption,
    get_onscreen_text,
    list_post_texts,
    media_index_for_post,
    post_media_stem,
    set_final_caption,
    set_onscreen_text,
)
from imouse_farm.utils.gallery import list_media_stems_for_posts, phone_gallery_folder
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


def _gallery_stems(config: AppConfig, device: Any) -> list[str]:
    gallery = config.gallery
    folder = phone_gallery_folder(
        gallery.base_directory,
        device.user_name,
        device.phone_name,
    )
    return list_media_stems_for_posts(folder, gallery.media_extensions, POST_COUNT)


async def generate_captions_for_device(
    config: AppConfig,
    device: Any,
    *,
    prompt: str | None = None,
    hashtags: str | None = None,
    onscreen_template: str | None = None,
) -> dict[str, Any]:
    """Generate unique final captions per post; optional onscreen template per device."""
    openai_cfg = config.openai
    if not openai_cfg.enabled:
        raise ValueError("OpenAI caption generation is disabled in config")

    settings = get_ai_settings()
    prompt_text = (prompt if prompt is not None else settings["prompt"]).strip()
    hashtags_text = (hashtags if hashtags is not None else settings["hashtags"]).strip()

    media_stems = _gallery_stems(config, device)
    if not any(media_stems):
        raise ValueError(
            f"No media files in gallery for Phone {device.user_name or device.device_id}"
        )

    text_key = device_storage_key(device.device_id, device.user_name)
    generated = await generate_post_captions(
        media_stems,
        user_prompt=prompt_text,
        hashtags=hashtags_text,
        config=openai_cfg,
    )

    template_key = (onscreen_template or "").strip()
    if template_key:
        apply_onscreen_for_stems(
            template_key,
            media_stems,
            text_key,
            set_onscreen_text=set_onscreen_text,
            food_names=[cap.get("food", "") for cap in generated],
        )

    posts: list[dict[str, Any]] = []
    for i, cap in enumerate(generated, start=1):
        post_num = POST_COUNT + 1 - i
        set_final_caption(text_key, post_num, cap["final"])
        stem = post_media_stem(media_stems, post_num)
        posts.append({
            "post": post_num,
            "onscreen": get_onscreen_text(text_key, post_num),
            "final": cap["final"],
            "media_file": stem,
            "food_name": cap.get("food") or stem_to_food_name(stem),
        })

    return {
        "device_id": device.device_id,
        "slot": device.user_name,
        "label": device.display_label,
        "text_key": text_key,
        "posts": posts,
        "media_files": media_stems,
    }


def default_onscreen_template_for_brand(brand: str, template: str | None = None) -> str | None:
    explicit = str(template or "").strip()
    if explicit:
        return explicit
    if str(brand or "").strip().lower() == "labely":
        return "america_sick"
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
