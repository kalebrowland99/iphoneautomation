"""TikTok account warmup — scroll feed before posting."""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Callable

from imouse_farm.actions.cancel import is_cancelled
from imouse_farm.actions.permission_prompts import is_tiktok_live_feed_dialog
from imouse_farm.actions.vpn_shadowrocket import (
    SHADOWROCKET_ICON_X,
    SHADOWROCKET_ICON_Y,
    TEMPLATE_THRESHOLD,
    TIKTOK_HOME_ICON_X,
    TIKTOK_HOME_ICON_Y,
    VPN_TOGGLE_X,
    VPN_TOGGLE_Y,
)
from imouse_farm.config.models import AppConfig
from imouse_farm.post.account_profile_store import (
    get_profile_for_device,
    increment_warmup_days,
)
from imouse_farm.utils.logging import get_logger
from imouse_farm.workflows.account_switch import ClearPopupsFn, ensure_tiktok_account
from imouse_farm.workflows.feed_scroll import (
    random_center_double_tap_coords,
    screen_dimensions,
    swipe_feed_up,
)

logger = get_logger(__name__)

StopCheck = Callable[[], bool]


async def run_tiktok_warmup(
    controller: Any,
    device: Any,
    *,
    brand: str,
    app_config: AppConfig,
    device_manager: Any | None = None,
    stop_check: StopCheck | None = None,
    log_activity: Any | None = None,
    duration_override: float | None = None,
    skip_setup: bool = False,
    after_labely: bool = False,
    clear_popups: ClearPopupsFn | None = None,
    permission_watchers: Any | None = None,
) -> None:
    """Verify account, tap home, then scroll the feed for the configured duration.

    Set skip_setup=True when TikTok is already open and on the correct account
    (e.g. debug flow where the account switch was a separate preceding step).

    after_labely=True when Labely posts just finished: confirm the Labely @ first,
    then toggle to the ValCoin account for warmup scrolling.
    """
    device_id = str(device.device_id)
    profile = get_profile_for_device(device_id, device.user_name, brand=brand)
    handle = str(profile.get("tiktok_handle") or "")
    warmup_cfg = app_config.batch.warmup

    dismiss_popups = clear_popups
    if dismiss_popups is None and permission_watchers is not None:
        async def dismiss_popups(context: str) -> bool:
            cleared = 0
            for _ in range(5):
                if not await permission_watchers.try_dismiss(device_id):
                    break
                cleared += 1
            return cleared > 0

    if not skip_setup and not (after_labely and brand == "valcoin"):
        await _open_tiktok_for_warmup(
            controller,
            device_id,
            app_config=app_config,
            log_activity=log_activity,
        )

    if not skip_setup:
        if after_labely and brand == "valcoin":
            labely_profile = get_profile_for_device(
                device_id, device.user_name, brand="labely"
            )
            labely_handle = str(labely_profile.get("tiktok_handle") or "")
            if log_activity:
                await log_activity(
                    "info",
                    "batch",
                    f"Labely finished — switching to ValCoin @ for warmup",
                    device_id,
                )
            await ensure_tiktok_account(
                controller=controller,
                device_id=device_id,
                tiktok_handle=labely_handle,
                navigation=app_config.tiktok_navigation,
                log_activity=log_activity,
                device_manager=device_manager,
                templates_dir=app_config.analysis.templates_directory,
                brand="labely",
                device_user_name=device.user_name,
                toggle_to_opposite=True,
                tiktok_ready_timeout_seconds=180.0,
                clear_popups=dismiss_popups,
            )
        else:
            await ensure_tiktok_account(
                controller=controller,
                device_id=device_id,
                tiktok_handle=handle,
                navigation=app_config.tiktok_navigation,
                log_activity=log_activity,
                device_manager=device_manager,
                templates_dir=app_config.analysis.templates_directory,
                brand=brand,
                device_user_name=device.user_name,
                # After tiktok_end kills apps + VPN, TikTok cold-start can take longer
                # than the default 90s — give it 3 minutes before giving up.
                tiktok_ready_timeout_seconds=180.0,
                clear_popups=dismiss_popups,
            )

    sw, sh = screen_dimensions(device)
    duration = float(duration_override) if duration_override is not None else float(warmup_cfg.duration_seconds)
    delay_min = float(warmup_cfg.swipe_delay_min_seconds)
    delay_max = float(warmup_cfg.swipe_delay_max_seconds)
    delay_mean = float(warmup_cfg.swipe_delay_mean_seconds)
    long_watch_prob = float(warmup_cfg.swipe_delay_long_watch_probability)
    tap_interval = float(warmup_cfg.double_tap_interval_seconds)

    if log_activity:
        await log_activity(
            "info",
            "batch",
            f"Warmup starting ({int(duration)}s scroll)",
            device_id,
        )

    started = time.monotonic()
    deadline = started + duration
    double_tap_at = started + random.uniform(0.0, duration)
    double_tap_done = False

    def _stopped() -> bool:
        if is_cancelled(device_id):
            return True
        if stop_check and stop_check():
            return True
        return False

    logger.info(
        "warmup_started",
        device_id=device_id,
        slot=device.user_name,
        brand=brand,
        duration_seconds=duration,
        double_tap_at_seconds=round(double_tap_at - started, 1),
    )

    while time.monotonic() < deadline:
        if _stopped():
            logger.info("warmup_stopped", device_id=device_id, reason="cancelled")
            return

        elapsed = time.monotonic() - started
        remaining = deadline - time.monotonic()

        if not double_tap_done and time.monotonic() >= double_tap_at:
            x, y = random_center_double_tap_coords(sw, sh)
            await controller.tap(device_id, x, y)
            await asyncio.sleep(tap_interval)
            await controller.tap(device_id, x, y)
            double_tap_done = True
            logger.info("warmup_double_tap", device_id=device_id, x=x, y=y)
            if log_activity:
                await log_activity(
                    "info",
                    "batch",
                    f"Warmup liked video (double-tap) at ({x}, {y}) — {elapsed:.0f}s elapsed",
                    device_id,
                )

        # Bimodal: long_watch_prob chance of a full-length watch (delay_max),
        # otherwise exponential weighted towards short watches (mean ~delay_mean).
        if random.random() < long_watch_prob:
            delay = delay_max
        else:
            delay = min(delay_max, max(delay_min, random.expovariate(1.0 / delay_mean)))
        if log_activity:
            await log_activity(
                "info",
                "batch",
                f"Warmup watching {delay:.0f}s — {elapsed:.0f}s elapsed, {remaining:.0f}s left",
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
        ):
            return

        if _stopped():
            return

        swiped = await swipe_feed_up(controller, device_id, sw, sh)
        if swiped:
            logger.info("warmup_swipe", device_id=device_id, **swiped)
            if log_activity:
                elapsed_after = time.monotonic() - started
                remaining_after = deadline - time.monotonic()
                await log_activity(
                    "info",
                    "batch",
                    f"Warmup swiped to next video — {elapsed_after:.0f}s elapsed, {remaining_after:.0f}s left",
                    device_id,
                )

    day = increment_warmup_days(device_id, device.user_name, brand=brand)
    logger.info("warmup_completed", device_id=device_id, slot=device.user_name, warmup_day=day)
    if log_activity:
        await log_activity(
            "info",
            "batch",
            f"Warmup Day {day} complete ✓",
            device_id,
        )

    await _teardown_after_warmup(controller, device_id, app_config, log_activity)


async def _teardown_after_warmup(
    controller: Any,
    device_id: str,
    app_config: AppConfig,
    log_activity: Any | None = None,
) -> None:
    """Home → open Shadowrocket → turn VPN off → home. Mirrors debug _warmup_steps_post_labely."""
    from pathlib import Path

    templates_dir = app_config.analysis.templates_directory
    blue_path = Path(templates_dir) / "bluetoggle.jpg"

    await controller.press_home(device_id)
    await asyncio.sleep(1.5)

    # Open Shadowrocket.
    await controller.tap(device_id, SHADOWROCKET_ICON_X, SHADOWROCKET_ICON_Y)
    await asyncio.sleep(2.0)

    # Turn VPN off only if it's currently on (bluetoggle visible).
    if blue_path.is_file():
        vpn_on = await controller.find_template_on_device(
            device_id, blue_path, threshold=TEMPLATE_THRESHOLD
        )
        if vpn_on:
            await controller.tap(device_id, VPN_TOGGLE_X, VPN_TOGGLE_Y)
            await asyncio.sleep(3.0)
            if log_activity:
                await log_activity("info", "batch", "Warmup: VPN turned off", device_id)
        else:
            if log_activity:
                await log_activity("info", "batch", "Warmup: VPN already off", device_id)

    await controller.press_home(device_id)
    await asyncio.sleep(1.0)
    logger.info("warmup_teardown_done", device_id=device_id)


async def _open_tiktok_for_warmup(
    controller: Any,
    device_id: str,
    *,
    app_config: AppConfig,
    log_activity: Any | None = None,
) -> None:
    """Turn VPN on, go home, open TikTok — minimal prep for warmup."""
    from imouse_farm.workflows.tiktok_plus_ready import (
        _plus_template_path,
        _plus_threshold,
    )
    from pathlib import Path

    templates_dir = app_config.analysis.templates_directory
    plus_path = _plus_template_path(None, templates_dir)
    threshold = _plus_threshold(None)

    # If TikTok is already open on home feed, just ensure VPN is on and return.
    if plus_path:
        hit = await controller.find_template_on_device(device_id, plus_path, threshold)
        if hit:
            await _ensure_vpn_on(controller, device_id, app_config, log_activity)
            return

    # Turn VPN on via Shadowrocket before opening TikTok.
    await _ensure_vpn_on(controller, device_id, app_config, log_activity)

    # Go home then tap TikTok icon.
    await controller.home(device_id)
    await asyncio.sleep(1.5)

    ok = await controller.tap(device_id, TIKTOK_HOME_ICON_X, TIKTOK_HOME_ICON_Y)
    if ok:
        if log_activity:
            await log_activity(
                "info",
                "batch",
                f"Warmup: opened TikTok at ({TIKTOK_HOME_ICON_X}, {TIKTOK_HOME_ICON_Y})",
                device_id,
            )
        # Extra settle time — after tiktok_end kills the app and VPN, TikTok needs
        # several seconds to cold-start before the account-ready check begins.
        await asyncio.sleep(8.0)
    elif log_activity:
        await log_activity(
            "warn",
            "batch",
            f"Warmup: TikTok tap failed at ({TIKTOK_HOME_ICON_X}, {TIKTOK_HOME_ICON_Y})",
            device_id,
        )


async def _ensure_vpn_on(
    controller: Any,
    device_id: str,
    app_config: AppConfig,
    log_activity: Any | None = None,
) -> None:
    """Open Shadowrocket and turn VPN on if it's currently off."""
    from pathlib import Path

    templates_dir = app_config.analysis.templates_directory
    grey_path = Path(templates_dir) / "greytoggle.jpg"

    # Open Shadowrocket.
    await controller.press_home(device_id)
    await asyncio.sleep(0.5)
    await controller.tap(device_id, SHADOWROCKET_ICON_X, SHADOWROCKET_ICON_Y)
    await asyncio.sleep(2.0)

    if grey_path.is_file():
        vpn_off = await controller.find_template_on_device(
            device_id, grey_path, threshold=TEMPLATE_THRESHOLD
        )
        if vpn_off:
            await controller.tap(device_id, VPN_TOGGLE_X, VPN_TOGGLE_Y)
            await asyncio.sleep(3.0)
            if log_activity:
                await log_activity("info", "batch", "Warmup: VPN turned on", device_id)
        else:
            if log_activity:
                await log_activity("info", "batch", "Warmup: VPN already on", device_id)

    await controller.press_home(device_id)
    await asyncio.sleep(1.0)


async def _wait_with_live_watch(
    controller: Any,
    device_id: str,
    sw: int,
    sh: int,
    duration: float,
    deadline: float,
    *,
    stop_check: Callable[[], bool],
) -> bool:
    """Sleep up to *duration* seconds, polling for LIVE feed overlays."""
    end = min(time.monotonic() + duration, deadline)
    while time.monotonic() < end:
        if stop_check():
            return False

        screen = await controller.ocr_on_device(device_id)
        if screen and is_tiktok_live_feed_dialog(screen):
            swiped = await swipe_feed_up(controller, device_id, sw, sh)
            if swiped:
                logger.info("warmup_live_dismiss", device_id=device_id, **swiped)

        remaining = end - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(0.5, remaining))
    return True
