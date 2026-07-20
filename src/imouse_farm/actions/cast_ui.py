"""Cast by opening iMouse Control Bar UI and tapping Screen Mirroring (no airplay/connect API)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from imouse_farm.config.models import CastUiConfig
from imouse_farm.controller.device_controller import DeviceController
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

RefreshFn = Callable[[], Awaitable[None]]
OnlineFn = Callable[[str], bool]


async def run_control_bar_cast(
    controller: DeviceController,
    device_id: str,
    cfg: CastUiConfig,
) -> bool:
    """Wake → ControlBar → Screen Mirroring tap → wait → target tap.

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

    fn_key = (cfg.control_bar_fn_key or "ControlBar").strip() or "ControlBar"
    logger.info("cast_ui_control_bar", device_id=device_id, fn_key=fn_key)
    bar_ok = await controller.send_fn_key(device_id, fn_key)
    if not bar_ok:
        logger.warning("cast_ui_control_bar_failed", device_id=device_id, fn_key=fn_key)
    if cfg.after_control_bar_seconds > 0:
        await asyncio.sleep(cfg.after_control_bar_seconds)

    logger.info(
        "cast_ui_screen_mirroring_tap",
        device_id=device_id,
        x=cfg.screen_mirroring_x,
        y=cfg.screen_mirroring_y,
    )
    mirror_ok = await controller.tap(
        device_id, cfg.screen_mirroring_x, cfg.screen_mirroring_y
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

    logger.info(
        "cast_ui_target_tap",
        device_id=device_id,
        x=cfg.target_x,
        y=cfg.target_y,
    )
    target_ok = await controller.tap(device_id, cfg.target_x, cfg.target_y)
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
    """Full UI cast: sequence + confirm iMouse online (state==1) + return home."""
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
