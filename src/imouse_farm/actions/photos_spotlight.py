"""Open Photos via iOS Spotlight search, with verify-and-retry."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from imouse_farm.config.models import ActionType, AppConfig
from imouse_farm.controller.device_controller import DeviceController
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

ExecuteFn = Callable[[ActionType, dict[str, Any], str], Awaitable[bool]]

# Mirror resolution ~406x720 — swipe down from center (not top edge).
SPOTLIGHT_SWIPE: dict[str, int | str] = {
    "direction": "down",
    "sx": 203,
    "sy": 360,
    "ex": 203,
    "ey": 580,
}

PHOTOS_SEARCH_TEXTS = ["Photos", "photos"]
PHOTOS_TEMPLATE_NAME = "photos.jpg"
PHOTOS_TEMPLATE_THRESHOLD = 0.42
DEFAULT_MAX_ATTEMPTS = 2


def photos_template_path(config: AppConfig) -> Path:
    return Path(config.analysis.templates_directory) / PHOTOS_TEMPLATE_NAME


async def photos_is_open(
    controller: DeviceController,
    config: AppConfig,
    device_id: str,
) -> bool:
    hit = await controller.find_template_on_device(
        device_id,
        photos_template_path(config),
        threshold=PHOTOS_TEMPLATE_THRESHOLD,
    )
    return hit is not None


async def close_photos_app(
    controller: DeviceController,
    config: AppConfig,
    device_id: str,
) -> None:
    """Return to home screen and leave Photos / Spotlight so a retry starts clean."""
    await controller.press_home(device_id)
    await asyncio.sleep(1)
    if await photos_is_open(controller, config, device_id):
        await controller.press_home(device_id)
        await asyncio.sleep(1)
    logger.info("photos_app_closed", device_id=device_id)


async def run_spotlight_open_sequence(
    execute: ExecuteFn,
    *,
    step_prefix: str,
) -> bool:
    sequence: list[tuple[ActionType, dict[str, Any]]] = [
        (ActionType.SWIPE, dict(SPOTLIGHT_SWIPE)),
        (ActionType.CLEAR_TEXT, {}),
        (ActionType.TEXT_INPUT, {"text": "photos"}),
        (
            ActionType.TAP_OCR,
            {
                "texts": list(PHOTOS_SEARCH_TEXTS),
                "prefer_top": True,
                "optional": False,
            },
        ),
    ]
    for action_type, params in sequence:
        ok = await execute(action_type, params, f"{step_prefix}_{action_type.value}")
        if not ok:
            logger.warning(
                "spotlight_sequence_failed",
                step=action_type.value,
                step_prefix=step_prefix,
            )
            return False
        await asyncio.sleep(2 if action_type == ActionType.SWIPE else 1)
    return True


async def open_photos_via_spotlight(
    execute: ExecuteFn,
    controller: DeviceController,
    config: AppConfig,
    device_id: str,
    *,
    step_prefix: str = "open_photos",
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    load_wait_seconds: float = 4.0,
) -> bool:
    """Home → Spotlight search → tap Photos. Retries after closing Photos on failure."""
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            await close_photos_app(controller, config, device_id)
            await asyncio.sleep(2)
            logger.info("open_photos_retry", device_id=device_id, attempt=attempt)

        ok = await execute(ActionType.HOME, {}, f"{step_prefix}_home")
        if not ok:
            continue
        await asyncio.sleep(2)

        if not await run_spotlight_open_sequence(execute, step_prefix=step_prefix):
            continue

        await asyncio.sleep(load_wait_seconds)
        if await photos_is_open(controller, config, device_id):
            logger.info("open_photos_success", device_id=device_id, attempt=attempt)
            return True

        logger.warning(
            "open_photos_verify_failed",
            device_id=device_id,
            attempt=attempt,
            message="Photos template not detected after Spotlight flow",
        )

    return False
