"""Turn VPN off via Shadowrocket before iMouse album clear/upload."""

from __future__ import annotations

import asyncio
from pathlib import Path

from imouse_farm.config.models import AppConfig, DeviceState
from imouse_farm.controller.device_controller import DeviceController
from imouse_farm.devices.manager import DeviceManager
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

SHADOWROCKET_ICON_X = 376
SHADOWROCKET_ICON_Y = 1013
VPN_TOGGLE_X = 511
VPN_TOGGLE_Y = 172
TEMPLATE_THRESHOLD = 0.42


def _template_path(config: AppConfig, filename: str) -> Path:
    return Path(config.analysis.templates_directory) / filename


async def open_shadowrocket(
    controller: DeviceController,
    device_id: str,
    *,
    settle_seconds: float = 2.0,
) -> None:
    """Press home, then tap the fixed Shadowrocket icon coordinate."""
    await controller.press_home(device_id)
    await asyncio.sleep(0.5)
    if not await controller.tap(device_id, SHADOWROCKET_ICON_X, SHADOWROCKET_ICON_Y):
        raise RuntimeError(
            f"Failed to tap Shadowrocket at ({SHADOWROCKET_ICON_X}, {SHADOWROCKET_ICON_Y})"
        )
    await asyncio.sleep(settle_seconds)


async def ensure_vpn_off_before_album(
    controller: DeviceController,
    config: AppConfig,
    device_manager: DeviceManager,
    device_id: str,
) -> None:
    """Home → Shadowrocket → tap VPN off if toggle shows connected, then home."""
    await open_shadowrocket(controller, device_id)

    blue_path = _template_path(config, "bluetoggle.jpg")
    vpn_on = await controller.find_template_on_device(
        device_id, blue_path, threshold=TEMPLATE_THRESHOLD
    )
    if vpn_on:
        if not await controller.tap(device_id, VPN_TOGGLE_X, VPN_TOGGLE_Y):
            raise RuntimeError("Failed to tap VPN toggle to turn VPN off")
        await asyncio.sleep(3)
        logger.info("vpn_turned_off_before_album", device_id=device_id)
    else:
        logger.info("vpn_already_off_before_album", device_id=device_id)

    await controller.press_home(device_id)
    await asyncio.sleep(1)
    await device_manager.set_state(device_id, DeviceState.WAITING, "vpn_off_before_album")
