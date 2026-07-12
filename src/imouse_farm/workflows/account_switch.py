"""Ensure TikTok is on the configured @ account before posting."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Awaitable

from imouse_farm.config.models import AppConfig, TikTokNavigationConfig
from imouse_farm.post.account_profile_store import (
    get_profile_for_device,
    handle_match_queries,
    normalize_handle,
    opposite_brand,
)
from imouse_farm.utils.logging import get_logger
from imouse_farm.workflows.tiktok_plus_ready import (
    _plus_template_path,
    _plus_threshold,
    wait_for_tiktok_plus_visible,
)
from imouse_farm.workflows.vision_step_context import (
    MAX_VISION_DISMISS_INLINE,
    vision_inline_context_goal,
)

logger = get_logger(__name__)

LogFn = Callable[..., Awaitable[None]]
ClearPopupsFn = Callable[[str], Awaitable[bool]]

PROFILE_TAB_TAP_ATTEMPTS = 3
POPUP_SCAN_LOG_SLOW_SECONDS = 2.0
POPUP_CLEAR_TIMEOUT_SECONDS = 8.0
HOME_FEED_SETTLE_SECONDS = 4.0
PLUS_LOW_CONFIDENCE_THRESHOLD = 0.65
PLUS_LOW_CONFIDENCE_SETTLE_SECONDS = 6.0
PROFILE_FIRST_TAP_SETTLE_SECONDS = 2.5
PROFILE_RETRY_TAP_SETTLE_SECONDS = 2.0


async def _clear_popups_if_needed(
    clear_popups: ClearPopupsFn | None,
    context: str,
    *,
    log_activity: LogFn | None = None,
    device_id: str = "",
) -> bool:
    if clear_popups is None:
        return False
    started = time.monotonic()
    try:
        cleared = bool(
            await asyncio.wait_for(
                clear_popups(context),
                timeout=POPUP_CLEAR_TIMEOUT_SECONDS,
            )
        )
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - started
        if log_activity:
            await log_activity(
                "warn",
                "workflow",
                (
                    f"Popup scan ({context}) timed out after {elapsed:.1f}s "
                    f"(limit {POPUP_CLEAR_TIMEOUT_SECONDS:.0f}s) — continuing"
                ),
                device_id,
            )
        return False
    elapsed = time.monotonic() - started
    if log_activity and elapsed >= POPUP_SCAN_LOG_SLOW_SECONDS:
        suffix = " — dismissed popup" if cleared else ""
        await log_activity(
            "info",
            "workflow",
            f"Popup scan ({context}) took {elapsed:.1f}s{suffix}",
            device_id,
        )
    return cleared


async def _vision_dismiss_profile_error(
    controller: Any,
    device_id: str,
    app_config: AppConfig | None,
    *,
    context: str,
    log_activity: LogFn | None = None,
    recent_errors: list[str] | None = None,
    extra_context: str = "",
    _attempts: dict[str, int] | None = None,
) -> bool:
    """Use OpenAI Vision to dismiss a blocking overlay during account switch."""
    if not app_config or not app_config.openai.enabled:
        return False
    key = context
    attempts = _attempts if _attempts is not None else {}
    if attempts.get(key, 0) >= MAX_VISION_DISMISS_INLINE:
        return False
    attempts[key] = attempts.get(key, 0) + 1

    from imouse_farm.workflows.vision_recovery import try_dismiss_blocking_popup

    inline_goal = vision_inline_context_goal(context)
    prompt_context = inline_goal or extra_context
    if inline_goal and extra_context:
        prompt_context = f"{inline_goal}\n{extra_context}"

    dismissed = await try_dismiss_blocking_popup(
        controller,
        device_id,
        app_config=app_config,
        step_name="ensure_tiktok_account",
        workflow_name="tiktok_account_switch",
        error_msg=context,
        recent_errors=recent_errors,
        extra_context=prompt_context,
        log_activity=log_activity,
    )
    if dismissed and log_activity:
        await log_activity(
            "info",
            "workflow",
            f"Vision dismissed overlay ({context})",
            device_id,
        )
    return dismissed


async def ensure_tiktok_account(
    *,
    controller: Any,
    device_id: str,
    tiktok_handle: str,
    navigation: TikTokNavigationConfig,
    log_activity: LogFn | None = None,
    device_manager: Any | None = None,
    templates_dir: str = "config/templates",
    vision: Any | None = None,
    app_config: AppConfig | None = None,
    brand: str = "labely",
    device_user_name: str = "",
    toggle_to_opposite: bool = False,
    tiktok_ready_timeout_seconds: float = 90.0,
    clear_popups: ClearPopupsFn | None = None,
    recent_errors: list[str] | None = None,
) -> bool:
    """Tap profile, switch account if needed, then tap home. Returns True if ready."""
    target_handle = normalize_handle(tiktok_handle)
    if not target_handle:
        if log_activity:
            await log_activity(
                "info",
                "workflow",
                "Account switch skipped — no @ handle configured for this slot",
            )
        return True

    user_name = str(device_user_name or "").strip()
    if not user_name and device_manager:
        device = device_manager.get_device(device_id)
        if device:
            user_name = str(device.user_name or "").strip()

    other_profile = get_profile_for_device(device_id, user_name, brand=opposite_brand(brand))
    other_handle = normalize_handle(str(other_profile.get("tiktok_handle") or ""))

    dest_handle = other_handle if toggle_to_opposite else target_handle
    if not dest_handle:
        which = opposite_brand(brand) if toggle_to_opposite else brand
        raise RuntimeError(
            f"No {which} @ handle saved for this slot — set it on the dashboard first"
        )

    dest_queries = handle_match_queries(dest_handle)
    vision_attempts: dict[str, int] = {}
    if log_activity:
        mode = "toggle to other brand" if toggle_to_opposite else "ensure for post"
        await log_activity(
            "info",
            "workflow",
            f"Checking TikTok account ({dest_handle}, {mode})",
            device_id,
        )

    plus_confidence = await wait_for_tiktok_plus_visible(
        controller,
        device_id,
        device_manager=device_manager,
        vision=vision,
        app_config=app_config,
        templates_directory=templates_dir,
        log_activity=log_activity,
        timeout_seconds=tiktok_ready_timeout_seconds,
        recent_errors=recent_errors,
    )

    settle_seconds = (
        PLUS_LOW_CONFIDENCE_SETTLE_SECONDS
        if plus_confidence < PLUS_LOW_CONFIDENCE_THRESHOLD
        else HOME_FEED_SETTLE_SECONDS
    )
    if log_activity:
        await log_activity(
            "info",
            "workflow",
            (
                f"Settling {settle_seconds:g}s — home feed loading after + detected "
                f"(confidence {plus_confidence:.2f})"
            ),
            device_id,
        )
    await _sleep(settle_seconds)
    profile_x = navigation.profile_tab_x
    profile_y = navigation.profile_tab_y
    rect = _search_rect(device_manager, device_id, navigation.account_name_search_rect_pct)
    await _open_profile_tab_for_check(
        controller,
        device_id,
        profile_x,
        profile_y,
        scan_handle=dest_handle,
        clear_popups=clear_popups,
        app_config=app_config,
        log_activity=log_activity,
        recent_errors=recent_errors,
        vision_attempts=vision_attempts,
        vision=vision,
        templates_dir=templates_dir,
    )
    if log_activity:
        await log_activity(
            "info",
            "workflow",
            f"Scanning profile for {dest_handle}",
            device_id,
        )
    on_profile = await _screen_shows_handle(controller, device_id, dest_queries, rect)
    if on_profile:
        if log_activity:
            await log_activity("info", "workflow", f"Already on {dest_handle}")
        await controller.tap(device_id, navigation.home_tab_x, navigation.home_tab_y)
        await _sleep(1.0)
        return True

    await _switch_to_dest_account(
        controller,
        device_id,
        navigation,
        dest_handle=dest_handle,
        dest_queries=dest_queries,
        clear_popups=clear_popups,
        app_config=app_config,
        log_activity=log_activity,
        recent_errors=recent_errors,
        vision_attempts=vision_attempts,
        device_user_name=user_name,
    )
    return True


async def _switch_to_dest_account(
    controller: Any,
    device_id: str,
    navigation: TikTokNavigationConfig,
    *,
    dest_handle: str,
    dest_queries: list[str],
    clear_popups: ClearPopupsFn | None,
    app_config: AppConfig | None,
    log_activity: LogFn | None,
    recent_errors: list[str] | None,
    vision_attempts: dict[str, int],
    device_user_name: str = "",
) -> None:
    """Open switcher, pick @ handle, return to home — full account switch."""
    if log_activity:
        await log_activity(
            "info",
            "workflow",
            f"Not on {dest_handle} — running full account switch",
            device_id,
        )

    await _clear_popups_if_needed(
        clear_popups,
        "account_switcher",
        log_activity=log_activity,
        device_id=device_id,
    )
    switcher_open = await _open_account_switcher(
        controller,
        device_id,
        navigation,
        dest_queries,
        app_config=app_config,
        device_user_name=device_user_name,
        log_activity=log_activity,
    )
    if not switcher_open:
        if await _vision_dismiss_profile_error(
            controller,
            device_id,
            app_config,
            context="account switcher did not open",
            log_activity=log_activity,
            recent_errors=recent_errors,
            _attempts=vision_attempts,
        ):
            switcher_open = await _open_account_switcher(
                controller,
                device_id,
                navigation,
                dest_queries,
                app_config=app_config,
                device_user_name=device_user_name,
                log_activity=log_activity,
            )
    if not switcher_open:
        raise RuntimeError(
            "Could not open TikTok account switcher — GPT-4o vision could not locate the display name"
        )

    await _sleep(1.0)

    handle_tapped = await _tap_handle_in_list(controller, device_id, dest_queries)
    if not handle_tapped:
        if await _vision_dismiss_profile_error(
            controller,
            device_id,
            app_config,
            context="account dropdown handle not found",
            extra_context=f"Target account: {dest_handle}",
            log_activity=log_activity,
            recent_errors=recent_errors,
            _attempts=vision_attempts,
        ):
            handle_tapped = await _tap_handle_in_list(controller, device_id, dest_queries)
    if not handle_tapped:
        raise RuntimeError(
            f"Could not find {dest_handle} in account dropdown via OCR"
        )

    await _sleep(2.0)
    await controller.tap(device_id, navigation.home_tab_x, navigation.home_tab_y)
    await _sleep(1.0)

    if log_activity:
        await log_activity("info", "workflow", f"Switched to {dest_handle} — on home tab")


async def _find_text_match(
    controller: Any,
    device_id: str,
    queries: list[str],
    rect: list[int] | None,
) -> dict[str, Any] | None:
    for query in queries:
        if not str(query or "").strip():
            continue
        matches = await controller.find_text_on_device(
            device_id,
            [query],
            threshold=0.5,
            contain=True,
            rect=rect,
            is_ex=True,
        )
        if matches:
            return max(matches, key=lambda m: float(m.get("confidence", 0)))
    return None


async def _screen_shows_handle(
    controller: Any,
    device_id: str,
    queries: list[str],
    rect: list[int] | None,
) -> bool:
    if await _find_text_match(controller, device_id, queries, rect):
        return True
    at_queries = [q for q in queries if str(q).strip().startswith("@")]
    if not at_queries:
        return False
    screen = await controller.ocr_on_device(device_id)
    if not screen:
        return False
    lower = screen.lower()
    return any(q.lower() in lower for q in at_queries)


def _screen_size(
    device_manager: Any | None,
    device_id: str,
) -> tuple[int, int]:
    sw, sh = 406, 720
    if device_manager:
        device = device_manager.get_device(device_id)
        if device and device.screen_width and device.screen_height:
            sw = int(device.screen_width)
            sh = int(device.screen_height)
    return sw, sh


def _search_rect(
    device_manager: Any | None,
    device_id: str,
    pct: list[float],
) -> list[int] | None:
    if not pct or len(pct) != 4:
        return None
    sw, sh = _screen_size(device_manager, device_id)
    return [
        int(sw * float(pct[0])),
        int(sh * float(pct[1])),
        int(sw * float(pct[2])),
        int(sh * float(pct[3])),
    ]


async def _open_account_switcher(
    controller: Any,
    device_id: str,
    navigation: TikTokNavigationConfig,
    switch_queries: list[str],
    *,
    app_config: AppConfig | None = None,
    device_user_name: str = "",
    log_activity: LogFn | None = None,
) -> bool:
    """Open the account switcher by tapping the profile display name via GPT-4o vision."""
    del navigation, device_user_name  # opener no longer uses fixed coords / per-slot UI
    if app_config is None or not app_config.openai.enabled:
        logger.warning("account_switcher_vision_unavailable", reason="openai disabled")
        return False

    try:
        x, y, reason = await _vision_locate_account_switcher_opener(
            controller,
            device_id,
            app_config=app_config,
        )
    except Exception as exc:
        logger.warning(
            "account_switcher_vision_failed",
            device_id=device_id,
            error=str(exc),
        )
        if log_activity:
            await log_activity(
                "warn",
                "workflow",
                f"Account switcher vision failed: {exc}",
                device_id,
            )
        return False

    if log_activity:
        await log_activity(
            "info",
            "workflow",
            f"Vision: tapping account switcher name at ({x}, {y}) — {reason}",
            device_id,
        )
    ok = await controller.tap(device_id, x, y)
    logger.info(
        "account_switcher_opener_tap",
        x=x,
        y=y,
        ok=ok,
        mode="vision",
        reason=reason,
    )
    if not ok:
        return False

    await _sleep(1.0)
    if switch_queries and not await _switcher_shows_account(
        controller, device_id, switch_queries
    ):
        logger.warning(
            "account_switcher_open_unverified",
            switch_queries=switch_queries,
            mode="vision",
        )
        # Still treat as opened — OCR of the other @ can lag; caller retries handle pick.
    else:
        logger.info("account_switcher_open", mode="vision")
    return True


_ACCOUNT_SWITCHER_OPENER_MODEL = "gpt-4o"

_ACCOUNT_SWITCHER_OPENER_SYSTEM = """You are looking at a TikTok profile screen on an iPhone.
The account-switcher popup is NOT open yet — you should NOT see a list of other @ accounts.

On the profile header there is a display NAME above the @handle.
Tap that display name (the text above the @handle, or the small chevron next to it) to open the account switcher and reveal the accounts.

Reply with EXACTLY two lines and nothing else:
X: <integer>
Y: <integer>

Example:
X: 312
Y: 238

Rules:
- Use that exact label format: "X: " then the number, newline, "Y: " then the number.
- No JSON, no markdown, no reason text, no extra lines.
- Coordinates are integer pixels on this screenshot for the display name ABOVE the @handle.
- Screen dimensions are {width}×{height} pixels.
- Do not tap the @handle, profile picture, or bottom tabs."""


def _parse_account_switcher_opener_coords(raw: str) -> tuple[int, int, str]:
    """Extract (x, y, reason) from a vision reply in `X: / Y:` format (JSON fallback)."""
    import json
    import re

    text = (raw or "").strip()
    if text.startswith("```"):
        text = "\n".join(text.splitlines()[1:])
        if text.endswith("```"):
            text = text[: text.rfind("```")]
        text = text.strip()

    x_match = re.search(r"(?im)^\s*X\s*:\s*(-?\d+)\s*$", text)
    y_match = re.search(r"(?im)^\s*Y\s*:\s*(-?\d+)\s*$", text)
    if x_match and y_match:
        return int(x_match.group(1)), int(y_match.group(1)), "display name above @handle"

    # Same labels inline on one line: "X: 312 Y: 238"
    inline = re.search(
        r"(?i)\bX\s*:\s*(-?\d+)\s*[,;\s]+Y\s*:\s*(-?\d+)",
        text,
    )
    if inline:
        return int(inline.group(1)), int(inline.group(2)), "display name above @handle"

    parsed: dict[str, Any] | None = None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            parsed = obj
    except json.JSONDecodeError:
        match = re.search(r"\{[^{}]*\}", text, flags=re.DOTALL)
        if match:
            try:
                obj = json.loads(match.group(0))
                if isinstance(obj, dict):
                    parsed = obj
            except json.JSONDecodeError:
                parsed = None

    if parsed is not None:
        lower = {str(k).strip().lower(): v for k, v in parsed.items()}
        x_val = lower.get("x", lower.get("cx"))
        y_val = lower.get("y", lower.get("cy"))
        if x_val is not None and y_val is not None:
            return int(float(x_val)), int(float(y_val)), "display name above @handle"

    raise RuntimeError(
        "Vision reply must be exactly 'X: <int>' and 'Y: <int>' lines; "
        f"got {text[:240]!r}"
    )


async def _vision_locate_account_switcher_opener(
    controller: Any,
    device_id: str,
    *,
    app_config: AppConfig,
) -> tuple[int, int, str]:
    """Screenshot profile and ask GPT-4o for the display-name tap to open the switcher."""
    import base64
    import io
    import os

    from PIL import Image

    from imouse_farm.workflows.vision_recovery import _to_jpeg

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

    img = Image.open(io.BytesIO(jpeg_bytes))
    width, height = img.size
    b64 = base64.b64encode(jpeg_bytes).decode("ascii")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    system = _ACCOUNT_SWITCHER_OPENER_SYSTEM.format(width=width, height=height)
    response = await client.chat.completions.create(
        model=_ACCOUNT_SWITCHER_OPENER_MODEL,
        max_tokens=40,
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Find the display name ABOVE the @handle. "
                            "Reply with exactly two lines:\nX: <integer>\nY: <integer>"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    try:
        x, y, reason = _parse_account_switcher_opener_coords(raw)
    except Exception as exc:
        logger.warning(
            "account_switcher_vision_parse_failed",
            device_id=device_id,
            raw=raw[:300],
            error=str(exc),
        )
        raise RuntimeError(f"Could not parse opener coords from: {raw[:180]!r}") from exc
    logger.info(
        "account_switcher_vision_locate",
        device_id=device_id,
        x=x,
        y=y,
        reason=reason,
        screen=(width, height),
        model=_ACCOUNT_SWITCHER_OPENER_MODEL,
        raw=raw[:120],
    )
    return x, y, reason


async def _switcher_shows_account(
    controller: Any,
    device_id: str,
    queries: list[str],
) -> bool:
    if not queries:
        return True
    return await _screen_shows_handle(controller, device_id, queries, rect=None)


async def _tap_account_switcher_opener(
    controller: Any,
    device_id: str,
    navigation: TikTokNavigationConfig,
    switch_queries: list[str] | None = None,
    *,
    app_config: AppConfig | None = None,
    device_user_name: str = "",
    log_activity: LogFn | None = None,
) -> bool:
    """Open the account switcher via GPT-4o vision (debug/production shared path)."""
    return await _open_account_switcher(
        controller,
        device_id,
        navigation,
        switch_queries or [],
        app_config=app_config,
        device_user_name=device_user_name,
        log_activity=log_activity,
    )


async def _tap_handle_in_list(
    controller: Any,
    device_id: str,
    queries: list[str],
) -> bool:
    for query in queries:
        matches = await controller.find_text_on_device(
            device_id,
            [query],
            threshold=0.55,
            contain=True,
            is_ex=True,
        )
        if not matches:
            continue
        best = max(matches, key=lambda m: float(m.get("confidence", 0)))
        return await controller.tap(device_id, int(best["x"]), int(best["y"]))
    return False


async def _still_on_home_feed(
    controller: Any,
    device_id: str,
    *,
    vision: Any | None,
    templates_dir: str,
) -> bool:
    """True when the home + button is still visible (profile tab likely did not open)."""
    template_path = _plus_template_path(vision, templates_dir)
    if not template_path:
        return True
    threshold = _plus_threshold(vision)
    hit = await controller.find_template_on_device(
        device_id,
        template_path,
        threshold,
    )
    return bool(hit)


async def _profile_tab_opened(
    controller: Any,
    device_id: str,
    queries: list[str],
    rect: list[int] | None,
    *,
    vision: Any | None,
    templates_dir: str,
) -> bool:
    if await _screen_shows_handle(controller, device_id, queries, rect):
        return True
    return not await _still_on_home_feed(
        controller,
        device_id,
        vision=vision,
        templates_dir=templates_dir,
    )


async def _profile_screen_is_open(
    controller: Any,
    device_id: str,
    *,
    vision: Any | None,
    templates_dir: str,
) -> bool:
    """True when the home + button is gone — profile tab likely opened."""
    return not await _still_on_home_feed(
        controller,
        device_id,
        vision=vision,
        templates_dir=templates_dir,
    )


async def _open_profile_tab_for_check(
    controller: Any,
    device_id: str,
    x: int,
    y: int,
    *,
    scan_handle: str,
    clear_popups: ClearPopupsFn | None,
    app_config: AppConfig | None = None,
    log_activity: LogFn | None = None,
    recent_errors: list[str] | None = None,
    vision_attempts: dict[str, int] | None = None,
    vision: Any | None = None,
    templates_dir: str = "config/templates",
) -> None:
    """Tap profile to open it for @ scan only — does not open the account switcher."""
    handle_label = str(scan_handle or "").lstrip("@")
    for attempt in range(1, PROFILE_TAB_TAP_ATTEMPTS + 1):
        if log_activity:
            if attempt == 1:
                await log_activity(
                    "info",
                    "workflow",
                    f"Tapping profile tab ({x}, {y}) to scan for @{handle_label}",
                    device_id,
                )
            else:
                await log_activity(
                    "info",
                    "workflow",
                    f"Profile tab still on home feed — retry {attempt}/{PROFILE_TAB_TAP_ATTEMPTS}",
                    device_id,
                )

        if not await _tap_profile_tab(controller, device_id, x, y):
            if await _vision_dismiss_profile_error(
                controller,
                device_id,
                app_config,
                context="profile tab tap failed",
                log_activity=log_activity,
                recent_errors=recent_errors,
                _attempts=vision_attempts,
            ):
                if not await _tap_profile_tab(controller, device_id, x, y):
                    raise RuntimeError(
                        f"Failed to tap profile tab at ({x}, {y}) after vision recovery"
                    )
            else:
                raise RuntimeError(f"Failed to tap profile tab at ({x}, {y})")

        settle = (
            PROFILE_FIRST_TAP_SETTLE_SECONDS
            if attempt == 1
            else PROFILE_RETRY_TAP_SETTLE_SECONDS
        )
        await _sleep(settle)
        if await _profile_screen_is_open(
            controller,
            device_id,
            vision=vision,
            templates_dir=templates_dir,
        ):
            await _sleep(0.5)
            return

        if await _still_on_home_feed(
            controller,
            device_id,
            vision=vision,
            templates_dir=templates_dir,
        ):
            if log_activity:
                await log_activity(
                    "info",
                    "workflow",
                    "Still on home feed — second profile tab tap after transition delay",
                    device_id,
                )
            if await _tap_profile_tab(controller, device_id, x, y):
                await _sleep(PROFILE_RETRY_TAP_SETTLE_SECONDS)
                if await _profile_screen_is_open(
                    controller,
                    device_id,
                    vision=vision,
                    templates_dir=templates_dir,
                ):
                    await _sleep(0.5)
                    return

        if await _clear_popups_if_needed(
            clear_popups,
            "account_profile_tab_after_tap",
            log_activity=log_activity,
            device_id=device_id,
        ):
            if log_activity:
                await log_activity(
                    "info",
                    "workflow",
                    "Popup dismissed after profile tap — tapping profile tab again",
                    device_id,
                )
            continue

    if await _still_on_home_feed(
        controller,
        device_id,
        vision=vision,
        templates_dir=templates_dir,
    ):
        if await _vision_dismiss_profile_error(
            controller,
            device_id,
            app_config,
            context="profile tab did not open",
            log_activity=log_activity,
            recent_errors=recent_errors,
            _attempts=vision_attempts,
        ):
            if await _tap_profile_tab(controller, device_id, x, y):
                await _sleep(PROFILE_RETRY_TAP_SETTLE_SECONDS)
                if await _profile_screen_is_open(
                    controller,
                    device_id,
                    vision=vision,
                    templates_dir=templates_dir,
                ):
                    await _sleep(0.5)
                    return

    raise RuntimeError(
        f"Profile tab did not open after {PROFILE_TAB_TAP_ATTEMPTS} attempts at ({x}, {y})"
    )


async def _double_tap_profile_with_popup_safeguard(
    controller: Any,
    device_id: str,
    x: int,
    y: int,
    *,
    dest_handle: str,
    dest_queries: list[str],
    search_rect: list[int] | None,
    clear_popups: ClearPopupsFn | None,
    app_config: AppConfig | None = None,
    log_activity: LogFn | None = None,
    recent_errors: list[str] | None = None,
    vision_attempts: dict[str, int] | None = None,
    vision: Any | None = None,
    templates_dir: str = "config/templates",
) -> None:
    """Tap profile until the profile screen opens or attempts are exhausted."""
    for attempt in range(1, PROFILE_TAB_TAP_ATTEMPTS + 1):
        if log_activity:
            if attempt == 1:
                await log_activity(
                    "info",
                    "workflow",
                    f"Tapping profile tab ({x}, {y}) to check @{dest_handle.lstrip('@')}",
                    device_id,
                )
            else:
                await log_activity(
                    "info",
                    "workflow",
                    f"Profile tab still on home feed — retry {attempt}/{PROFILE_TAB_TAP_ATTEMPTS}",
                    device_id,
                )

        if not await _tap_profile_tab(controller, device_id, x, y):
            if await _vision_dismiss_profile_error(
                controller,
                device_id,
                app_config,
                context="profile tab tap failed",
                log_activity=log_activity,
                recent_errors=recent_errors,
                _attempts=vision_attempts,
            ):
                if not await _tap_profile_tab(controller, device_id, x, y):
                    raise RuntimeError(
                        f"Failed to tap profile tab at ({x}, {y}) after vision recovery"
                    )
            else:
                raise RuntimeError(f"Failed to tap profile tab at ({x}, {y})")

        settle = (
            PROFILE_FIRST_TAP_SETTLE_SECONDS
            if attempt == 1
            else PROFILE_RETRY_TAP_SETTLE_SECONDS
        )
        await _sleep(settle)
        if await _profile_tab_opened(
            controller,
            device_id,
            dest_queries,
            search_rect,
            vision=vision,
            templates_dir=templates_dir,
        ):
            await _sleep(0.5)
            return

        if await _still_on_home_feed(
            controller,
            device_id,
            vision=vision,
            templates_dir=templates_dir,
        ):
            if log_activity:
                await log_activity(
                    "info",
                    "workflow",
                    "Still on home feed — second profile tab tap after transition delay",
                    device_id,
                )
            if await _tap_profile_tab(controller, device_id, x, y):
                await _sleep(PROFILE_RETRY_TAP_SETTLE_SECONDS)
                if await _profile_tab_opened(
                    controller,
                    device_id,
                    dest_queries,
                    search_rect,
                    vision=vision,
                    templates_dir=templates_dir,
                ):
                    await _sleep(0.5)
                    return

        if await _clear_popups_if_needed(
            clear_popups,
            "account_profile_tab_after_tap",
            log_activity=log_activity,
            device_id=device_id,
        ):
            if log_activity:
                await log_activity(
                    "info",
                    "workflow",
                    "Popup dismissed after profile tap — tapping profile tab again",
                    device_id,
                )
            continue

    if await _still_on_home_feed(
        controller,
        device_id,
        vision=vision,
        templates_dir=templates_dir,
    ):
        if await _vision_dismiss_profile_error(
            controller,
            device_id,
            app_config,
            context="profile tab did not open",
            log_activity=log_activity,
            recent_errors=recent_errors,
            _attempts=vision_attempts,
        ):
            if await _tap_profile_tab(controller, device_id, x, y):
                await _sleep(PROFILE_RETRY_TAP_SETTLE_SECONDS)
                if await _profile_tab_opened(
                    controller,
                    device_id,
                    dest_queries,
                    search_rect,
                    vision=vision,
                    templates_dir=templates_dir,
                ):
                    await _sleep(0.5)
                    return

    raise RuntimeError(
        f"Profile tab did not open after {PROFILE_TAB_TAP_ATTEMPTS} attempts at ({x}, {y})"
    )


async def _tap_profile_tab(
    controller: Any,
    device_id: str,
    x: int,
    y: int,
) -> bool:
    return await controller.tap(device_id, x, y)


async def _double_tap(
    controller: Any,
    device_id: str,
    x: int,
    y: int,
    *,
    interval_seconds: float = 0.5,
) -> bool:
    ok = await controller.tap(device_id, x, y)
    if not ok:
        return False
    await _sleep(interval_seconds)
    return await controller.tap(device_id, x, y)


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
