"""Cast by opening iMouse Control Bar UI and tapping Screen Mirroring (no airplay/connect API)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from imouse_farm.actions.pre_touch_reset import pre_touch_mouse_reset
from imouse_farm.config.models import CastUiConfig
from imouse_farm.controller.device_controller import DeviceController
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

RefreshFn = Callable[[], Awaitable[None]]
OnlineFn = Callable[[str], bool]


async def _tap_n_times(
    controller: DeviceController,
    device_id: str,
    x: int,
    y: int,
    *,
    count: int,
    interval_seconds: float,
    label: str,
) -> bool:
    taps = max(1, int(count))
    interval = max(0.0, float(interval_seconds))
    logger.info(
        "cast_ui_tap",
        device_id=device_id,
        label=label,
        x=x,
        y=y,
        tap_count=taps,
        interval_seconds=interval,
    )
    for i in range(taps):
        # Same double mouse_reset as TikTok taps — clears cursor drift before each coord.
        await pre_touch_mouse_reset(
            controller, device_id, step_name=f"cast_ui:{label}"
        )
        ok = await controller.tap(device_id, x, y)
        if not ok:
            logger.warning(
                "cast_ui_tap_failed",
                device_id=device_id,
                label=label,
                x=x,
                y=y,
                tap_index=i + 1,
                tap_count=taps,
            )
            return False
        if i + 1 < taps and interval > 0:
            await asyncio.sleep(interval)
    return True


async def run_control_bar_cast(
    controller: DeviceController,
    device_id: str,
    cfg: CastUiConfig,
) -> bool:
    """Wake → dismiss Cancel → ControlBar → Screen Mirroring → target.

    Does not call device_airplay_connect. Returns True if the UI sequence ran.
    """
    if not cfg.enabled:
        return False

    if cfg.wake_screen:
        logger.info("cast_ui_wake_screen", device_id=device_id)
        unlocked = await controller.press_unlock(device_id)
        if not unlocked:
            logger.warning("cast_ui_unlock_failed", device_id=device_id)
        if cfg.wake_settle_seconds > 0:
            await asyncio.sleep(cfg.wake_settle_seconds)
        home_ok = await controller.press_home(device_id)
        if not home_ok:
            logger.warning("cast_ui_home_failed", device_id=device_id)
        if cfg.post_home_settle_seconds > 0:
            await asyncio.sleep(cfg.post_home_settle_seconds)

        # Just-in-case Cancel tap for any leftover popup after wake.
        await _tap_n_times(
            controller,
            device_id,
            cfg.dismiss_cancel_x,
            cfg.dismiss_cancel_y,
            count=1,
            interval_seconds=0,
            label="dismiss_cancel",
        )
        if cfg.after_dismiss_cancel_seconds > 0:
            await asyncio.sleep(cfg.after_dismiss_cancel_seconds)

    fn_key = (cfg.control_bar_fn_key or "ControlBar").strip() or "ControlBar"
    logger.info("cast_ui_control_bar", device_id=device_id, fn_key=fn_key)
    bar_ok = await controller.send_fn_key(device_id, fn_key)
    if not bar_ok:
        logger.warning("cast_ui_control_bar_failed", device_id=device_id, fn_key=fn_key)
    if cfg.after_control_bar_seconds > 0:
        await asyncio.sleep(cfg.after_control_bar_seconds)

    mirror_ok = await _tap_n_times(
        controller,
        device_id,
        cfg.screen_mirroring_x,
        cfg.screen_mirroring_y,
        count=cfg.ui_tap_count,
        interval_seconds=cfg.ui_tap_interval_seconds,
        label="screen_mirroring",
    )
    if not mirror_ok:
        logger.warning(
            "cast_ui_screen_mirroring_tap_failed",
            device_id=device_id,
            x=cfg.screen_mirroring_x,
            y=cfg.screen_mirroring_y,
        )
    if cfg.after_mirroring_seconds > 0:
        await asyncio.sleep(cfg.after_mirroring_seconds)

    target_ok = await _tap_n_times(
        controller,
        device_id,
        cfg.target_x,
        cfg.target_y,
        count=cfg.ui_tap_count,
        interval_seconds=cfg.ui_tap_interval_seconds,
        label="airplay_target",
    )
    if not target_ok:
        logger.warning(
            "cast_ui_target_tap_failed",
            device_id=device_id,
            x=cfg.target_x,
            y=cfg.target_y,
        )
    if cfg.after_target_seconds > 0:
        await asyncio.sleep(cfg.after_target_seconds)

    return True


async def wait_until_online(
    device_id: str,
    *,
    refresh_devices: RefreshFn,
    is_online: OnlineFn,
    timeout_seconds: float,
    poll_seconds: float = 1.0,
) -> bool:
    """Poll iMouse device list until state/online or timeout."""
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    poll = max(0.2, float(poll_seconds))
    while True:
        await refresh_devices()
        if is_online(device_id):
            logger.info("cast_ui_online", device_id=device_id)
            return True
        if time.monotonic() >= deadline:
            logger.warning("cast_ui_not_online", device_id=device_id)
            return False
        await asyncio.sleep(poll)


async def return_home_after_cast(
    controller: DeviceController,
    device_id: str,
    cfg: CastUiConfig,
) -> None:
    """Press Home N times after a successful cast to leave Screen Mirroring UI."""
    count = max(0, int(cfg.home_after_connect_count))
    if count <= 0:
        return
    interval = max(0.0, float(cfg.home_after_connect_interval_seconds))
    logger.info(
        "cast_ui_return_home",
        device_id=device_id,
        count=count,
        interval_seconds=interval,
    )
    for i in range(count):
        ok = await controller.press_home(device_id)
        if not ok:
            logger.warning(
                "cast_ui_return_home_failed",
                device_id=device_id,
                index=i + 1,
                count=count,
            )
        if i + 1 < count and interval > 0:
            await asyncio.sleep(interval)


async def ensure_cast_via_control_bar(
    controller: DeviceController,
    device_id: str,
    cfg: CastUiConfig,
    *,
    refresh_devices: RefreshFn,
    is_online: OnlineFn,
) -> bool:
    """Full UI cast: sequence + confirm iMouse online (state==1) + return home.

    This is the single cast implementation used by the dashboard Cast toggle,
    farm batch connect, device-manager reconnect, and workflow re-cast.
    Does not call device_airplay_connect.
    """
    await refresh_devices()
    if is_online(device_id):
        return True
    if not cfg.enabled:
        logger.warning("cast_ui_disabled", device_id=device_id)
        return False
    await run_control_bar_cast(controller, device_id, cfg)
    online = await wait_until_online(
        device_id,
        refresh_devices=refresh_devices,
        is_online=is_online,
        timeout_seconds=cfg.confirm_timeout_seconds,
        poll_seconds=cfg.confirm_poll_seconds,
    )
    if online:
        await return_home_after_cast(controller, device_id, cfg)
    return online


async def ensure_cast_via_control_bar_retries(
    controller: DeviceController,
    device_id: str,
    cfg: CastUiConfig,
    *,
    refresh_devices: RefreshFn,
    is_online: OnlineFn,
    max_attempts: int = 1,
    retry_seconds: float = 15.0,
) -> bool:
    """Same Control Bar cast as the UI toggle, with optional retries."""
    attempts = max(1, int(max_attempts))
    interval = max(0.0, float(retry_seconds))
    for attempt in range(1, attempts + 1):
        logger.info(
            "cast_ui_attempt",
            device_id=device_id,
            attempt=attempt,
            max_attempts=attempts,
            mode="control_bar_ui",
        )
        ok = await ensure_cast_via_control_bar(
            controller,
            device_id,
            cfg,
            refresh_devices=refresh_devices,
            is_online=is_online,
        )
        if ok:
            return True
        if attempt < attempts and interval > 0:
            await asyncio.sleep(interval)
    return False
