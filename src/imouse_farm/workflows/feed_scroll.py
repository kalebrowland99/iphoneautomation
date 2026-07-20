"""Random TikTok feed swipe / double-tap helpers and timed home-feed scroll."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

from imouse_farm.actions.cancel import is_cancelled
from imouse_farm.actions.permission_prompts import is_tiktok_live_feed_dialog
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_SCREEN_WIDTH = 406
DEFAULT_SCREEN_HEIGHT = 720

StopCheck = Callable[[], bool]
ActivityFn = Callable[[], Awaitable[None]]
LogFn = Callable[..., Awaitable[None]]


def screen_dimensions(device: Any | None) -> tuple[int, int]:
    sw = DEFAULT_SCREEN_WIDTH
    sh = DEFAULT_SCREEN_HEIGHT
    if device is not None:
        dw = int(getattr(device, "screen_width", 0) or 0)
        dh = int(getattr(device, "screen_height", 0) or 0)
        if dw > 0 and dh > 0:
            sw, sh = dw, dh
    return sw, sh


def random_feed_swipe_coords(sw: int, sh: int) -> tuple[int, int, int, int]:
    """Return (sx, sy, ex, ey) for a random upward swipe on the feed."""
    sx = random.randint(max(5, int(sw * 0.25)), max(6, int(sw * 0.75)))
    sy = random.randint(max(5, int(sh * 0.55)), max(6, int(sh * 0.85)))
    swipe_len = random.randint(max(80, int(sh * 0.25)), max(120, int(sh * 0.45)))
    ey = max(5, sy - swipe_len)
    ex = max(5, min(sw - 5, sx + random.randint(-15, 15)))
    return sx, sy, ex, ey


def random_center_double_tap_coords(sw: int, sh: int) -> tuple[int, int]:
    """Random point in the center band of the screen (for like double-tap)."""
    x = random.randint(max(5, int(sw * 0.30)), max(6, int(sw * 0.70)))
    y = random.randint(max(5, int(sh * 0.30)), max(6, int(sh * 0.70)))
    return x, y


async def swipe_feed_up(
    controller: Any,
    device_id: str,
    sw: int,
    sh: int,
) -> dict[str, Any] | None:
    sx, sy, ex, ey = random_feed_swipe_coords(sw, sh)
    ok = await controller.swipe(
        device_id,
        direction="up",
        sx=sx,
        sy=sy,
        ex=ex,
        ey=ey,
    )
    if not ok:
        return None
    return {"sx": sx, "sy": sy, "ex": ex, "ey": ey}


async def _wait_with_live_watch(
    controller: Any,
    device_id: str,
    sw: int,
    sh: int,
    duration: float,
    deadline: float,
    *,
    stop_check: StopCheck,
    on_activity: ActivityFn | None = None,
) -> bool:
    """Sleep up to *duration* seconds, polling for LIVE feed overlays."""
    end = min(time.monotonic() + duration, deadline)
    while time.monotonic() < end:
        if stop_check():
            return False
        if on_activity:
            await on_activity()

        screen = await controller.ocr_on_device(device_id)
        if screen and is_tiktok_live_feed_dialog(screen):
            swiped = await swipe_feed_up(controller, device_id, sw, sh)
            if swiped:
                logger.info("feed_scroll_live_dismiss", device_id=device_id, **swiped)
                if on_activity:
                    await on_activity()

        remaining = end - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(0.5, remaining))
    return True


async def scroll_tiktok_feed(
    controller: Any,
    device: Any,
    *,
    duration_seconds: float,
    home_tab_x: int,
    home_tab_y: int,
    swipe_delay_min_seconds: float = 0.0,
    swipe_delay_max_seconds: float = 53.0,
    swipe_delay_mean_seconds: float = 4.0,
    swipe_delay_long_watch_probability: float = 0.20,
    double_tap_interval_seconds: float = 0.35,
    tap_home_first: bool = True,
    enable_double_tap: bool = True,
    log_activity: LogFn | None = None,
    log_label: str = "Feed scroll",
    stop_check: StopCheck | None = None,
    on_activity: ActivityFn | None = None,
) -> None:
    """Scroll TikTok home feed for *duration_seconds* (watch + swipe loop)."""
    device_id = str(getattr(device, "device_id", "") or "")
    sw, sh = screen_dimensions(device)
    duration = max(1.0, float(duration_seconds))
    delay_min = float(swipe_delay_min_seconds)
    delay_max = float(swipe_delay_max_seconds)
    delay_mean = max(0.1, float(swipe_delay_mean_seconds))
    long_watch_prob = float(swipe_delay_long_watch_probability)
    tap_interval = float(double_tap_interval_seconds)
    home_x = int(home_tab_x)
    home_y = int(home_tab_y)

    def _stopped() -> bool:
        if is_cancelled(device_id):
            return True
        if stop_check and stop_check():
            return True
        return False

    if tap_home_first:
        ok = await controller.tap(device_id, home_x, home_y)
        logger.info(
            "feed_scroll_home_tab",
            device_id=device_id,
            x=home_x,
            y=home_y,
            ok=ok,
            at="start",
        )
        if log_activity:
            await log_activity(
                "info",
                "workflow",
                f"{log_label}: tapped home tab ({home_x}, {home_y})",
                device_id,
            )
        if on_activity:
            await on_activity()
        await asyncio.sleep(2.0)

    if log_activity:
        await log_activity(
            "info",
            "workflow",
            f"{log_label}: starting ({int(duration)}s scroll)",
            device_id,
        )

    started = time.monotonic()
    deadline = started + duration
    double_tap_at = started + random.uniform(0.0, duration) if enable_double_tap else None
    double_tap_done = False
    swipes_since_home = 0
    home_every_swipes = random.randint(3, 4)

    logger.info(
        "feed_scroll_started",
        device_id=device_id,
        duration_seconds=duration,
        log_label=log_label,
        enable_double_tap=enable_double_tap,
    )

    while time.monotonic() < deadline:
        if _stopped():
            logger.info("feed_scroll_stopped", device_id=device_id, reason="cancelled")
            return

        elapsed = time.monotonic() - started
        remaining = deadline - time.monotonic()

        if (
            enable_double_tap
            and not double_tap_done
            and double_tap_at is not None
            and time.monotonic() >= double_tap_at
        ):
            x, y = random_center_double_tap_coords(sw, sh)
            await controller.tap(device_id, x, y)
            await asyncio.sleep(tap_interval)
            await controller.tap(device_id, x, y)
            double_tap_done = True
            if on_activity:
                await on_activity()
            logger.info("feed_scroll_double_tap", device_id=device_id, x=x, y=y)
            if log_activity:
                await log_activity(
                    "info",
                    "workflow",
                    f"{log_label}: liked video (double-tap) at ({x}, {y}) — {elapsed:.0f}s elapsed",
                    device_id,
                )

        if random.random() < long_watch_prob:
            delay = delay_max
        else:
            delay = min(delay_max, max(delay_min, random.expovariate(1.0 / delay_mean)))
        if log_activity:
            await log_activity(
                "info",
                "workflow",
                f"{log_label}: watching {delay:.0f}s — {elapsed:.0f}s elapsed, {remaining:.0f}s left",
                device_id,
            )
        if not await _wait_with_live_watch(
            controller,
            device_id,
            sw,
            sh,
            delay,
            deadline,
            stop_check=_stopped,
            on_activity=on_activity,
        ):
            return

        if _stopped():
            return

        swiped = await swipe_feed_up(controller, device_id, sw, sh)
        if swiped:
            swipes_since_home += 1
            if on_activity:
                await on_activity()
            logger.info("feed_scroll_swipe", device_id=device_id, **swiped)
            if log_activity:
                elapsed_after = time.monotonic() - started
                remaining_after = deadline - time.monotonic()
                await log_activity(
                    "info",
                    "workflow",
                    (
                        f"{log_label}: swiped to next video — "
                        f"{elapsed_after:.0f}s elapsed, {remaining_after:.0f}s left"
                    ),
                    device_id,
                )

            if swipes_since_home >= home_every_swipes:
                ok = await controller.tap(device_id, home_x, home_y)
                logger.info(
                    "feed_scroll_home_tab",
                    device_id=device_id,
                    x=home_x,
                    y=home_y,
                    ok=ok,
                    after_swipes=swipes_since_home,
                )
                if on_activity:
                    await on_activity()
                if log_activity:
                    await log_activity(
                        "info",
                        "workflow",
                        f"{log_label}: tapped home tab ({home_x}, {home_y}) after {swipes_since_home} swipes",
                        device_id,
                    )
                swipes_since_home = 0
                home_every_swipes = random.randint(3, 4)
                await asyncio.sleep(1.0)

    logger.info(
        "feed_scroll_completed",
        device_id=device_id,
        duration_seconds=round(time.monotonic() - started, 1),
        log_label=log_label,
    )
    if log_activity:
        await log_activity(
            "info",
            "workflow",
            f"{log_label}: complete ({int(duration)}s)",
            device_id,
        )
