"""Ensure TikTok is on the configured @ account before posting."""

from __future__ import annotations

from typing import Any, Callable, Awaitable

from imouse_farm.config.models import TikTokNavigationConfig
from imouse_farm.post.account_profile_store import (
    get_profile_for_device,
    handle_match_queries,
    normalize_handle,
    opposite_brand,
)
from imouse_farm.utils.logging import get_logger
from imouse_farm.workflows.tiktok_plus_ready import wait_for_tiktok_plus_visible

logger = get_logger(__name__)

LogFn = Callable[..., Awaitable[None]]


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
    brand: str = "labely",
    device_user_name: str = "",
    toggle_to_opposite: bool = False,
    tiktok_ready_timeout_seconds: float = 90.0,
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
    if log_activity:
        mode = "toggle to other brand" if toggle_to_opposite else "ensure for post"
        await log_activity(
            "info",
            "workflow",
            f"Checking TikTok account ({dest_handle}, {mode})",
            device_id,
        )

    await wait_for_tiktok_plus_visible(
        controller,
        device_id,
        device_manager=device_manager,
        vision=vision,
        templates_directory=templates_dir,
        log_activity=log_activity,
        timeout_seconds=tiktok_ready_timeout_seconds,
    )

    if log_activity:
        await log_activity("info", "workflow", "Settling 3s — home feed loading after + detected", device_id)
    await _sleep(3.0)
    await controller.tap(device_id, navigation.profile_tab_x, navigation.profile_tab_y)
    await _sleep(2.0)

    rect = _search_rect(device_manager, device_id, navigation.account_name_search_rect_pct)
    if await _screen_shows_handle(controller, device_id, dest_queries, rect):
        if log_activity:
            await log_activity("info", "workflow", f"Already on {dest_handle}")
        await controller.tap(device_id, navigation.home_tab_x, navigation.home_tab_y)
        await _sleep(1.0)
        return True

    if log_activity:
        await log_activity(
            "info",
            "workflow",
            f"Switching to {dest_handle}",
        )

    if not await _open_account_switcher(
        controller, device_id, navigation, dest_queries
    ):
        raise RuntimeError(
            "Could not open TikTok account switcher — tap failed at configured opener coordinates"
        )

    await _sleep(1.0)

    if not await _tap_handle_in_list(controller, device_id, dest_queries):
        raise RuntimeError(
            f"Could not find {dest_handle} in account dropdown via OCR"
        )

    await _sleep(2.0)
    await controller.tap(device_id, navigation.home_tab_x, navigation.home_tab_y)
    await _sleep(1.0)

    if log_activity:
        await log_activity("info", "workflow", f"Switched to {dest_handle} — on home tab")
    return True


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
) -> bool:
    """Open account switcher; recover from Total Likes modal on alternate TikTok UI."""
    x = navigation.account_switcher_opener_x
    y = navigation.account_switcher_opener_y
    ok = await controller.tap(device_id, x, y)
    logger.info("account_switcher_opener_tap", x=x, y=y, ok=ok)
    if not ok:
        return False

    await _sleep(1.0)
    if await _switcher_shows_account(controller, device_id, switch_queries):
        logger.info("account_switcher_open", mode="primary")
        return True

    dismiss = navigation.account_likes_dismiss_ok
    dx = int(dismiss.x)
    dy = int(dismiss.y)
    ok = await controller.tap(device_id, dx, dy)
    logger.info("account_likes_dismiss_ok", x=dx, y=dy, ok=ok)
    if not ok:
        return False

    await _sleep(0.8)

    fallback = navigation.account_switcher_opener_fallback
    fx = int(fallback.x)
    fy = int(fallback.y)
    ok = await controller.tap(device_id, fx, fy)
    logger.info("account_switcher_opener_fallback_tap", x=fx, y=fy, ok=ok)
    if not ok:
        return False

    await _sleep(1.0)
    if switch_queries and not await _switcher_shows_account(
        controller, device_id, switch_queries
    ):
        logger.warning(
            "account_switcher_open_unverified",
            switch_queries=switch_queries,
        )
    else:
        logger.info("account_switcher_open", mode="fallback")
    return True


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
) -> bool:
    """Backward-compatible wrapper for debug/tests."""
    return await _open_account_switcher(
        controller,
        device_id,
        navigation,
        switch_queries or [],
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


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
