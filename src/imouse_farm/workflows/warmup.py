"""TikTok account warmup — scroll feed before posting."""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Callable

from imouse_farm.actions.cancel import is_cancelled
from imouse_farm.actions.permission_prompts import is_tiktok_live_feed_dialog
from imouse_farm.actions.vpn_shadowrocket import (
    TIKTOK_HOME_ICON_X,
    TIKTOK_HOME_ICON_Y,
    ensure_vpn_off,
    ensure_vpn_on,
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
from imouse_farm.workflows.tiktok_plus_ready import wait_for_tiktok_plus_visible

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

    ValCoin warmup retries on failure by killing and reopening TikTok on the home
    tab — never re-runs prep or gallery upload/clear.
    """
    device_id = str(device.device_id)
    brand_key = str(brand or "labely").strip().lower()
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

    def _stopped() -> bool:
        if is_cancelled(device_id):
            return True
        if stop_check and stop_check():
            return True
        return False

    max_attempts = (
        max(1, int(warmup_cfg.max_retry_attempts))
        if brand_key == "valcoin"
        else 1
    )
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        if _stopped():
            logger.info("warmup_stopped", device_id=device_id, reason="cancelled")
            return

        try:
            if attempt == 1:
                if not skip_setup and not (after_labely and brand_key == "valcoin"):
                    await _open_tiktok_for_warmup(
                        controller,
                        device_id,
                        app_config=app_config,
                        log_activity=log_activity,
                        device_manager=device_manager,
                    )
                if not skip_setup:
                    await _ensure_account_for_warmup(
                        controller,
                        device,
                        brand=brand_key,
                        app_config=app_config,
                        device_manager=device_manager,
                        log_activity=log_activity,
                        after_labely=after_labely,
                        clear_popups=dismiss_popups,
                        log_switch_message=True,
                    )
            else:
                if log_activity:
                    await log_activity(
                        "info",
                        "batch",
                        (
                            f"ValCoin warmup retry {attempt}/{max_attempts} "
                            f"— closing and reopening TikTok (no gallery changes)…"
                        ),
                        device_id,
                    )
                await _reopen_tiktok_for_warmup_retry(
                    controller,
                    device_id,
                    app_config=app_config,
                    device_manager=device_manager,
                    log_activity=log_activity,
                    after_labely=after_labely,
                )
                await _ensure_account_for_warmup(
                    controller,
                    device,
                    brand=brand_key,
                    app_config=app_config,
                    device_manager=device_manager,
                    log_activity=log_activity,
                    after_labely=after_labely,
                    clear_popups=dismiss_popups,
                    log_switch_message=False,
                )

            await _run_warmup_scroll(
                controller,
                device,
                brand=brand_key,
                app_config=app_config,
                log_activity=log_activity,
                duration_override=duration_override,
                stop_check=_stopped,
            )
            await _teardown_after_warmup(
                controller, device_id, app_config, log_activity
            )
            return
        except Exception as exc:
            last_error = exc
            logger.warning(
                "warmup_attempt_failed",
                device_id=device_id,
                slot=device.user_name,
                brand=brand_key,
                attempt=attempt,
                max_attempts=max_attempts,
                error=str(exc),
            )
            if log_activity:
                await log_activity(
                    "warn",
                    "batch",
                    f"Warmup attempt {attempt}/{max_attempts} failed: {exc}",
                    device_id,
                )
            if attempt >= max_attempts or _stopped():
                raise

    if last_error is not None:
        raise last_error


async def _ensure_account_for_warmup(
    controller: Any,
    device: Any,
    *,
    brand: str,
    app_config: AppConfig,
    device_manager: Any | None,
    log_activity: Any | None,
    after_labely: bool,
    clear_popups: ClearPopupsFn | None,
    log_switch_message: bool = True,
) -> None:
    device_id = str(device.device_id)
    profile = get_profile_for_device(device_id, device.user_name, brand=brand)
    handle = str(profile.get("tiktok_handle") or "")

    if after_labely and brand == "valcoin":
        labely_profile = get_profile_for_device(
            device_id, device.user_name, brand="labely"
        )
        labely_handle = str(labely_profile.get("tiktok_handle") or "")
        if log_switch_message and log_activity:
            await log_activity(
                "info",
                "batch",
                "Labely finished — switching to ValCoin @ for warmup",
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
            app_config=app_config,
            brand="labely",
            device_user_name=device.user_name,
            toggle_to_opposite=True,
            tiktok_ready_timeout_seconds=180.0,
            clear_popups=clear_popups,
        )
        return

    await ensure_tiktok_account(
        controller=controller,
        device_id=device_id,
        tiktok_handle=handle,
        navigation=app_config.tiktok_navigation,
        log_activity=log_activity,
        device_manager=device_manager,
        templates_dir=app_config.analysis.templates_directory,
        app_config=app_config,
        brand=brand,
        device_user_name=device.user_name,
        tiktok_ready_timeout_seconds=180.0,
        clear_popups=clear_popups,
    )


async def _reopen_tiktok_for_warmup_retry(
    controller: Any,
    device_id: str,
    *,
    app_config: AppConfig,
    device_manager: Any | None = None,
    log_activity: Any | None = None,
    after_labely: bool = False,
) -> None:
    """Kill TikTok and reopen from the home screen — lands on the home feed tab."""
    if log_activity:
        await log_activity(
            "info",
            "batch",
            "Warmup: closing TikTok…",
            device_id,
        )
    await controller.kill_app(device_id)
    await asyncio.sleep(1.0)
    await controller.press_home(device_id)
    await asyncio.sleep(1.5)

    # After Labely posts VPN is already on — do not cycle Shadowrocket or touch gallery.
    if not after_labely:
        await _ensure_vpn_on(
            controller,
            device_id,
            app_config,
            log_activity,
            device_manager=device_manager,
        )

    ok = await controller.tap(device_id, TIKTOK_HOME_ICON_X, TIKTOK_HOME_ICON_Y)
    if ok:
        if log_activity:
            await log_activity(
                "info",
                "batch",
                (
                    f"Warmup: reopened TikTok at ({TIKTOK_HOME_ICON_X}, {TIKTOK_HOME_ICON_Y}) "
                    f"— waiting for home feed"
                ),
                device_id,
            )
        await asyncio.sleep(8.0)
    elif log_activity:
        await log_activity(
            "warn",
            "batch",
            f"Warmup: TikTok reopen tap failed at ({TIKTOK_HOME_ICON_X}, {TIKTOK_HOME_ICON_Y})",
            device_id,
        )

    await wait_for_tiktok_plus_visible(
        controller,
        device_id,
        device_manager=device_manager,
        templates_directory=app_config.analysis.templates_directory,
        app_config=app_config,
        log_activity=log_activity,
        timeout_seconds=180.0,
    )
    if log_activity:
        await log_activity(
            "info",
            "batch",
            "Warmup: TikTok home feed ready after reopen",
            device_id,
        )


async def _run_warmup_scroll(
    controller: Any,
    device: Any,
    *,
    brand: str,
    app_config: AppConfig,
    log_activity: Any | None,
    duration_override: float | None,
    stop_check: Callable[[], bool],
) -> None:
    device_id = str(device.device_id)
    warmup_cfg = app_config.batch.warmup
    sw, sh = screen_dimensions(device)
    duration = (
        float(duration_override)
        if duration_override is not None
        else float(warmup_cfg.duration_seconds)
    )
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

    nav = app_config.tiktok_navigation
    home_x = int(nav.home_tab_x)
    home_y = int(nav.home_tab_y)

    started = time.monotonic()
    deadline = started + duration
    double_tap_at = started + random.uniform(0.0, duration)
    double_tap_done = False
    swipes_since_home = 0
    home_every_swipes = random.randint(3, 4)

    logger.info(
        "warmup_started",
        device_id=device_id,
        slot=device.user_name,
        brand=brand,
        duration_seconds=duration,
        double_tap_at_seconds=round(double_tap_at - started, 1),
        home_every_swipes=home_every_swipes,
    )

    while time.monotonic() < deadline:
        if stop_check():
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
            stop_check=stop_check,
        ):
            return

        if stop_check():
            return

        swiped = await swipe_feed_up(controller, device_id, sw, sh)
        if swiped:
            swipes_since_home += 1
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

            if swipes_since_home >= home_every_swipes:
                ok = await controller.tap(device_id, home_x, home_y)
                logger.info(
                    "warmup_home_tab",
                    device_id=device_id,
                    x=home_x,
                    y=home_y,
                    ok=ok,
                    after_swipes=swipes_since_home,
                )
                if log_activity:
                    await log_activity(
                        "info",
                        "batch",
                        f"Warmup tapped home tab ({home_x}, {home_y}) after {swipes_since_home} swipes",
                        device_id,
                    )
                swipes_since_home = 0
                home_every_swipes = random.randint(3, 4)
                await asyncio.sleep(1.0)

    day = increment_warmup_days(device_id, device.user_name, brand=brand)
    logger.info("warmup_completed", device_id=device_id, slot=device.user_name, warmup_day=day)
    if log_activity:
        await log_activity(
            "info",
            "batch",
            f"Warmup Day {day} complete ✓",
            device_id,
        )


async def _teardown_after_warmup(
    controller: Any,
    device_id: str,
    app_config: AppConfig,
    log_activity: Any | None = None,
) -> None:
    """Turn VPN off via URL shortcut after warmup scroll.

    VPN-off failures are logged but do not fail the warmup — scroll already completed.
    """
    try:
        await ensure_vpn_off(
            controller, app_config, device_id, log_activity=log_activity
        )
    except Exception as exc:
        logger.warning(
            "warmup_vpn_off_failed",
            device_id=device_id,
            error=str(exc),
        )
        if log_activity:
            await log_activity(
                "warn",
                "batch",
                f"Warmup: VPN off failed after scroll ({exc}) — continuing",
                device_id,
            )
        return
    if log_activity:
        await log_activity("info", "batch", "Warmup: VPN off (shortcut)", device_id)
    logger.info("warmup_teardown_done", device_id=device_id)


async def _open_tiktok_for_warmup(
    controller: Any,
    device_id: str,
    *,
    app_config: AppConfig,
    log_activity: Any | None = None,
    device_manager: Any | None = None,
) -> None:
    """Turn VPN on, open TikTok from the home screen, then wait for the + button.

    Always taps the TikTok icon after VPN — do not skip open based on a pre-VPN
    + match (phone reset during VPN recovery lands on Springboard).
    """
    await _ensure_vpn_on(
        controller,
        device_id,
        app_config,
        log_activity,
        device_manager=device_manager,
    )

    await controller.press_home(device_id)
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
        await asyncio.sleep(8.0)
    elif log_activity:
        await log_activity(
            "warn",
            "batch",
            f"Warmup: TikTok tap failed at ({TIKTOK_HOME_ICON_X}, {TIKTOK_HOME_ICON_Y})",
            device_id,
        )

    await wait_for_tiktok_plus_visible(
        controller,
        device_id,
        device_manager=device_manager,
        templates_directory=app_config.analysis.templates_directory,
        app_config=app_config,
        log_activity=log_activity,
        timeout_seconds=180.0,
    )
    if log_activity:
        await log_activity(
            "info",
            "batch",
            "Warmup: TikTok home feed ready (+ visible)",
            device_id,
        )


async def _ensure_vpn_on(
    controller: Any,
    device_id: str,
    app_config: AppConfig,
    log_activity: Any | None = None,
    *,
    device_manager: Any | None = None,
) -> None:
    """Turn VPN on; on shortcut failure, reboot phone + recast once, then retry."""
    try:
        await ensure_vpn_on(controller, app_config, device_id, log_activity=log_activity)
        return
    except Exception as exc:
        if device_manager is None:
            raise
        logger.warning(
            "warmup_vpn_on_failed_resetting_phone",
            device_id=device_id,
            error=str(exc),
        )
        if log_activity:
            await log_activity(
                "warn",
                "batch",
                f"VPN on failed ({exc}) — restarting phone and recasting, then retrying VPN",
                device_id,
            )
        await device_manager.reset_phone_and_recast(device_id)
        await ensure_vpn_on(controller, app_config, device_id, log_activity=log_activity)


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
