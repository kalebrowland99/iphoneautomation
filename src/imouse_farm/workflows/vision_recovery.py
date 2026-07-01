"""OpenAI Vision-based error recovery for workflow steps.

When a step fails, capture a screenshot and ask GPT-4o what to tap/press
to navigate out of the unexpected screen state so the flow can continue.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from typing import Any

from imouse_farm.config.models import AppConfig
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

# System prompt sent alongside every error screenshot.
_RECOVERY_SYSTEM = """You are an iOS automation assistant for a TikTok/iPhone farm.
A workflow step failed and the screen shows an unexpected state.
Your job: look at the screenshot and tell us the ONE action needed to dismiss the error
or navigate back so the automation can continue.

Respond with valid JSON only — no markdown, no extra text:
{
  "description": "<what you see on screen in 1-2 sentences>",
  "action": "<one of: tap | home | swipe_up | swipe_down | back | wait | none>",
  "x": <integer x coordinate to tap, omit or null if action is not tap>,
  "y": <integer y coordinate to tap, omit or null if action is not tap>,
  "reasoning": "<why this action will help>"
}

Screen dimensions are 1170×2532 pixels (iPhone).
If the screen looks normal and no action is needed, use action "none".
If a dialog/popup/alert is visible, tap the dismiss/OK/Cancel/Allow/Not Now button.
If the app crashed or shows a black screen, use action "home".
Prioritize the least destructive action that lets automation resume."""


async def ask_vision_for_recovery(
    controller: Any,
    device_id: str,
    *,
    step_name: str,
    workflow_name: str,
    error_msg: str,
    app_config: AppConfig,
) -> dict[str, Any] | None:
    """
    Capture a screenshot and ask OpenAI Vision what action to take.

    Returns a dict with keys: description, action, x, y, reasoning
    Returns None if vision is unavailable or the call fails.
    """
    openai_cfg = app_config.openai
    api_key = (os.environ.get("OPENAI_API_KEY") or openai_cfg.api_key or "").strip()
    if not api_key:
        logger.warning("vision_recovery_no_api_key", device_id=device_id)
        return None

    try:
        screenshot_bytes = await controller.capture_screenshot(device_id)
    except Exception as exc:
        logger.warning("vision_recovery_screenshot_failed", device_id=device_id, error=str(exc))
        return None

    if not screenshot_bytes:
        logger.warning("vision_recovery_no_screenshot", device_id=device_id)
        return None

    b64 = base64.b64encode(screenshot_bytes).decode("ascii")

    user_text = (
        f'Workflow: "{workflow_name}" | Step: "{step_name}"\n'
        f'Error: {error_msg}\n\n'
        f"What ONE action should I take to navigate out of this screen and let the automation continue?"
    )

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model="gpt-4o",
            max_tokens=256,
            messages=[
                {"role": "system", "content": _RECOVERY_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}",
                                "detail": "low",
                            },
                        },
                    ],
                },
            ],
        )
        raw = response.choices[0].message.content or ""
        result = json.loads(raw)
        logger.info(
            "vision_recovery_response",
            device_id=device_id,
            step=step_name,
            action=result.get("action"),
            reasoning=result.get("reasoning", ""),
        )
        return result
    except Exception as exc:
        logger.warning("vision_recovery_api_failed", device_id=device_id, error=str(exc))
        return None


async def execute_recovery_action(
    controller: Any,
    device_id: str,
    action_dict: dict[str, Any],
    *,
    log_activity: Any | None = None,
) -> bool:
    """
    Execute the recovery action returned by OpenAI.

    Returns True if an action was executed, False if nothing was done.
    """
    action = str(action_dict.get("action", "none")).lower().strip()
    description = action_dict.get("description", "")
    reasoning = action_dict.get("reasoning", "")

    if log_activity:
        await log_activity(
            "info",
            "workflow",
            f"Vision recovery — {description} → {action} ({reasoning})",
            device_id,
        )

    if action == "none":
        return False

    try:
        if action == "tap":
            x = action_dict.get("x")
            y = action_dict.get("y")
            if x is not None and y is not None:
                await controller.tap(device_id, int(x), int(y))
                await asyncio.sleep(1.5)
                return True
        elif action == "home":
            await controller.press_home(device_id)
            await asyncio.sleep(1.5)
            return True
        elif action == "back":
            # Swipe from left edge to go back on iOS
            await controller.swipe(device_id, 30, 600, 300, 600, duration_ms=200)
            await asyncio.sleep(1.0)
            return True
        elif action == "swipe_up":
            await controller.swipe(device_id, 585, 1800, 585, 400, duration_ms=300)
            await asyncio.sleep(1.0)
            return True
        elif action == "swipe_down":
            await controller.swipe(device_id, 585, 400, 585, 1800, duration_ms=300)
            await asyncio.sleep(1.0)
            return True
        elif action == "wait":
            await asyncio.sleep(3.0)
            return True
    except Exception as exc:
        logger.warning(
            "vision_recovery_action_failed",
            device_id=device_id,
            action=action,
            error=str(exc),
        )

    return False
