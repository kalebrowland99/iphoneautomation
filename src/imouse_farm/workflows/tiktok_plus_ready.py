"""Wait until TikTok's home feed + button is visible (app finished loading)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Callable, Awaitable

from imouse_farm.config.models import AppConfig
from imouse_farm.utils.logging import get_logger
from imouse_farm.workflows.vision_step_context import MAX_VISION_DISMISS_PER_WAIT

logger = get_logger(__name__)

PLUS_TEMPLATE_NAME = "plus"
PLUS_DEVICE_THRESHOLD = 0.50
DEFAULT_TIMEOUT_SECONDS = 90.0
DEFAULT_POLL_SECONDS = 0.5
VISION_DISMISS_AFTER_ATTEMPTS = 2

LogFn = Callable[..., Awaitable[None]]


def _plus_template_path(vision: Any | None, templates_directory: str) -> Path | None:
    if vision and hasattr(vision, "template_path_for"):
        path = vision.template_path_for(PLUS_TEMPLATE_NAME)
        if path and path.is_file():
            return path
    candidate = Path(templates_directory) / "plus.jpg"
    return candidate if candidate.is_file() else None


def _plus_threshold(vision: Any | None) -> float:
    if vision and hasattr(vision, "device_threshold_for"):
        return float(vision.device_threshold_for(PLUS_TEMPLATE_NAME))
    if vision and hasattr(vision, "threshold_for"):
        return float(vision.threshold_for(PLUS_TEMPLATE_NAME))
    return PLUS_DEVICE_THRESHOLD


async def wait_for_tiktok_plus_visible(
    controller: Any,
    device_id: str,
    *,
    device_manager: Any | None = None,
    vision: Any | None = None,
    app_config: AppConfig | None = None,
    templates_directory: str = "config/templates",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    log_activity: LogFn | None = None,
    recent_errors: list[str] | None = None,
) -> float:
    """Poll until the + create button is visible. Returns match confidence."""
    template_path = _plus_template_path(vision, templates_directory)
    if not template_path:
        raise RuntimeError("plus.jpg template not found — cannot verify TikTok is ready")

    # NOTE: search the whole device screenshot. The iMouse on-device match runs against
    # the raw screen-pixel image, but device.screen_width/height report iOS points
    # (375x667), so a points-derived rect lands in the wrong region and the + is missed.
    threshold = _plus_threshold(vision)
    poll = max(0.25, float(poll_seconds))
    deadline = time.monotonic() + max(1.0, float(timeout_seconds))
    started = time.monotonic()

    if log_activity:
        await log_activity(
            "info",
            "workflow",
            (
                f"Waiting for TikTok + button (continues as soon as visible, "
                f"max {int(timeout_seconds)}s)"
            ),
        )

    attempt = 0
    vision_dismiss_count = 0
    while time.monotonic() < deadline:
        attempt += 1
        hit = await controller.find_template_on_device(
            device_id,
            template_path,
            threshold,
        )
        if hit:
            elapsed = time.monotonic() - started
            logger.info(
                "tiktok_plus_visible",
                device_id=device_id,
                attempts=attempt,
                elapsed_seconds=round(elapsed, 2),
                confidence=hit.get("confidence"),
                x=hit.get("x"),
                y=hit.get("y"),
            )
            if log_activity:
                await log_activity(
                    "info",
                    "workflow",
                    f"TikTok ready — + visible after {elapsed:.1f}s (attempt {attempt}, confidence {hit.get('confidence', 0):.2f})",
                    device_id,
                )
            return float(hit.get("confidence", 0) or 0)

        if (
            app_config
            and app_config.openai.enabled
            and attempt >= VISION_DISMISS_AFTER_ATTEMPTS
            and attempt % VISION_DISMISS_AFTER_ATTEMPTS == 0
            and vision_dismiss_count < MAX_VISION_DISMISS_PER_WAIT
        ):
            from imouse_farm.workflows.vision_recovery import try_dismiss_blocking_popup

            vision_dismiss_count += 1
            dismissed = await try_dismiss_blocking_popup(
                controller,
                device_id,
                app_config=app_config,
                step_name="wait_for_plus",
                workflow_name="tiktok",
                error_msg="+ button template not found while waiting",
                recent_errors=recent_errors,
                log_activity=log_activity,
            )
            if dismissed:
                logger.info(
                    "tiktok_plus_vision_dismissed",
                    device_id=device_id,
                    attempt=attempt,
                )
                if log_activity:
                    await log_activity(
                        "info",
                        "workflow",
                        f"Vision dismissed overlay while waiting for + (attempt {attempt})",
                        device_id,
                    )
                await asyncio.sleep(1.0)
                continue

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(poll, remaining))

    raise RuntimeError(
        f"TikTok + button not visible after {int(timeout_seconds)}s — app may still be loading"
    )
