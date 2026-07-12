"""OpenAI Vision-based error recovery for workflow steps.

When a step fails, capture a screenshot and ask GPT-4o what to tap/press
to navigate out of the unexpected screen state so the flow can continue.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
from typing import Any

from imouse_farm.config.models import AppConfig
from imouse_farm.utils.logging import get_logger
from imouse_farm.workflows.vision_step_context import build_vision_error_msg

logger = get_logger(__name__)

# System prompt for error recovery — simple popup check.
_RECOVERY_SYSTEM = """You are an iOS automation assistant.
Look at this iPhone screenshot and answer ONE question:

Is there a popup, alert, dialog, permission prompt, or overlay on screen that would
block taps on the app behind it?

If YES — respond with the coordinate to tap to dismiss it:
{"popup": true, "x": <integer>, "y": <integer>, "reason": "<button or element you are tapping>"}

If NO — respond:
{"popup": false}

Respond with valid JSON only — no markdown, no extra text.
Screen dimensions are 1170×2532 pixels (iPhone)."""

# System prompt for the goal-driven tap loop.
_TAP_SYSTEM = """You are an iOS automation assistant controlling a real iPhone.
You will be given a screenshot and a goal. Each turn, decide the SINGLE next tap needed.

If the goal is already achieved on this screen, respond:
{"done": true, "reason": "<why goal is complete>"}

Otherwise respond with the coordinate to tap next:
{"x": <integer>, "y": <integer>, "reason": "<element you are tapping and why>"}

Rules:
- Respond with valid JSON only — no markdown, no extra text.
- Screen dimensions are 1170×2532 pixels (iPhone).
- Always pick the most obvious tap target. Never return null x/y unless done.
- After each tap you will receive a new screenshot. Keep tapping until the goal is reached."""


def _to_jpeg(data: bytes) -> bytes | None:
    """Convert raw screenshot bytes (BMP/PNG/JPEG/etc.) to JPEG for OpenAI."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception as exc:
        logger.warning("vision_recovery_jpeg_convert_failed", error=str(exc))
        return None


async def _screenshot_to_b64(controller: Any, device_id: str) -> str:
    """Capture screenshot, convert to JPEG, return base64 string. Raises on failure."""
    screenshot_bytes = await controller.capture_screenshot(device_id)
    if not screenshot_bytes:
        raise RuntimeError("Screenshot returned no data")
    jpeg_bytes = _to_jpeg(screenshot_bytes)
    if not jpeg_bytes:
        raise RuntimeError("Could not convert screenshot to JPEG")
    return base64.b64encode(jpeg_bytes).decode("ascii")


def _make_openai_client(app_config: AppConfig) -> Any:
    from openai import AsyncOpenAI

    openai_cfg = app_config.openai
    api_key = (os.environ.get("OPENAI_API_KEY") or openai_cfg.api_key or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")
    return AsyncOpenAI(api_key=api_key)


def _model(app_config: AppConfig) -> str:
    return getattr(app_config.openai, "model", "gpt-4o-mini") or "gpt-4o-mini"


def _strip_fences(raw: str) -> str:
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:])
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]
    return raw.strip()


async def ask_vision_for_recovery(
    controller: Any,
    device_id: str,
    *,
    step_name: str,
    workflow_name: str,
    error_msg: str,
    app_config: AppConfig,
    recent_errors: list[str] | None = None,
    extra_context: str = "",
) -> dict[str, Any]:
    """
    Screenshot the device and ask: is there a blocking popup?

    Returns one of:
      {"popup": True,  "x": int, "y": int, "reason": str}  → tap to dismiss
      {"popup": False}                                       → no popup, kill+reopen TikTok
    Raises on any failure.
    """
    b64 = await _screenshot_to_b64(controller, device_id)
    client = _make_openai_client(app_config)
    model = _model(app_config)

    user_text = build_vision_error_msg(
        workflow_name=workflow_name,
        step_name=step_name,
        error_msg=error_msg,
        recent_errors=recent_errors,
        extra_context=extra_context,
    )
    response = await client.chat.completions.create(
        model=model,
        max_tokens=80,
        messages=[
            {"role": "system", "content": _RECOVERY_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}},
                ],
            },
        ],
    )
    raw = _strip_fences((response.choices[0].message.content or "").strip())
    result = json.loads(raw)
    logger.info("vision_recovery_response", device_id=device_id, step=step_name, result=result)
    return result


async def kill_and_reopen_tiktok(
    controller: Any,
    device_id: str,
    app_config: AppConfig,
    *,
    log_activity: Any | None = None,
) -> None:
    """Kill TikTok via app switcher, go home, then use vision to reopen it."""
    if log_activity:
        await log_activity("info", "workflow", "Vision recovery: no popup — killing and reopening TikTok", device_id)

    # Kill TikTok via app switcher.
    await controller.kill_app(device_id)
    await asyncio.sleep(1.0)

    # Go to home screen.
    await controller.press_home(device_id)
    await asyncio.sleep(1.5)

    # Tap the TikTok icon at the configured home-screen coordinate.
    nav = app_config.tiktok_navigation
    x = nav.tiktok_home_icon_x
    y = nav.tiktok_home_icon_y
    if log_activity:
        await log_activity(
            "info",
            "workflow",
            f"Vision recovery: tapping TikTok icon at ({x}, {y})",
            device_id,
        )
    ok = await controller.tap(device_id, x, y)
    if not ok:
        logger.warning("vision_recovery_reopen_tap_failed", device_id=device_id, x=x, y=y)
        if log_activity:
            await log_activity(
                "warn",
                "workflow",
                f"Vision recovery: TikTok icon tap failed at ({x}, {y})",
                device_id,
            )
        return
    await asyncio.sleep(3.0)


async def ask_vision_for_tap(
    controller: Any,
    device_id: str,
    *,
    goal: str,
    app_config: AppConfig,
    client: Any | None = None,
) -> tuple[int, int, str] | tuple[None, None, str]:
    """
    Screenshot the device and ask GPT what coordinate to tap next toward `goal`.

    Returns:
      (x, y, reason)       — tap this coordinate
      (None, None, reason) — goal is already achieved ("done")

    Raises on any failure (screenshot, API, parse).
    Pass an existing `client` to reuse the same OpenAI connection across loop iterations.
    """
    openai_cfg = app_config.openai
    api_key = (os.environ.get("OPENAI_API_KEY") or openai_cfg.api_key or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    screenshot_bytes = await controller.capture_screenshot(device_id)
    if not screenshot_bytes:
        raise RuntimeError("Screenshot returned no data")

    jpeg_bytes = _to_jpeg(screenshot_bytes)
    if not jpeg_bytes:
        raise RuntimeError("Could not convert screenshot to JPEG")

    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    model = getattr(openai_cfg, "model", "gpt-4o-mini") or "gpt-4o-mini"

    if client is None:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)

    response = await client.chat.completions.create(
        model=model,
        max_tokens=120,
        messages=[
            {"role": "system", "content": _TAP_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Goal: {goal}"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"},
                    },
                ],
            },
        ],
    )
    raw = (response.choices[0].message.content or "").strip()

    # Strip markdown fences if present.
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:])
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]

    parsed = json.loads(raw)

    if parsed.get("done"):
        reason = str(parsed.get("reason", "goal achieved"))
        logger.info("vision_tap_done", device_id=device_id, reason=reason)
        return None, None, reason

    x = int(parsed["x"])
    y = int(parsed["y"])
    reason = str(parsed.get("reason", ""))
    logger.info("vision_tap_response", device_id=device_id, x=x, y=y, reason=reason)
    return x, y, reason


async def try_dismiss_blocking_popup(
    controller: Any,
    device_id: str,
    *,
    app_config: AppConfig,
    step_name: str = "wait_for_plus",
    workflow_name: str = "tiktok",
    error_msg: str = "+ button not found — checking for blocking overlay",
    recent_errors: list[str] | None = None,
    extra_context: str = "",
    log_activity: Any | None = None,
) -> bool:
    """Use OpenAI Vision to find and tap a blocking popup/overlay. Returns True if dismissed."""
    if not app_config.openai.enabled:
        return False
    try:
        result = await ask_vision_for_recovery(
            controller,
            device_id,
            step_name=step_name,
            workflow_name=workflow_name,
            error_msg=error_msg,
            app_config=app_config,
            recent_errors=recent_errors,
            extra_context=extra_context,
        )
        if result.get("popup"):
            return await execute_recovery_action(
                controller,
                device_id,
                result,
                log_activity=log_activity,
            )
    except Exception as exc:
        logger.warning(
            "vision_dismiss_popup_failed",
            device_id=device_id,
            step=step_name,
            error=str(exc),
        )
    return False


async def execute_recovery_action(
    controller: Any,
    device_id: str,
    result: dict[str, Any],
    *,
    log_activity: Any | None = None,
) -> bool:
    """
    Tap the popup dismiss coordinate returned by ask_vision_for_recovery.
    Returns True if a tap was executed, False if popup=False (caller handles kill/reopen).
    """
    if not result.get("popup"):
        return False

    x = result.get("x")
    y = result.get("y")
    reason = result.get("reason", "popup")

    if x is None or y is None:
        return False

    if log_activity:
        await log_activity("info", "workflow", f"Vision recovery: dismissing popup — tapping ({x}, {y}) {reason}", device_id)

    try:
        await controller.tap(device_id, int(x), int(y))
        await asyncio.sleep(1.5)
        return True
    except Exception as exc:
        logger.warning("vision_recovery_tap_failed", device_id=device_id, error=str(exc))
        return False
