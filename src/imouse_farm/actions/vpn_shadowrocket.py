"""Turn VPN on/off via Shadowrocket URL shortcuts (iMouse shortcut_exec_url)."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from imouse_farm.config.models import AppConfig, DeviceState
from imouse_farm.controller.device_controller import DeviceController
from imouse_farm.devices.manager import DeviceManager
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

SHADOWROCKET_ICON_X = 376
SHADOWROCKET_ICON_Y = 1013
TIKTOK_HOME_ICON_X = 507
TIKTOK_HOME_ICON_Y = 1011

VpnShortcutMode = Literal["on", "off", "toggle", "open"]


def vpn_shortcut_url(config: AppConfig, mode: VpnShortcutMode) -> str:
    """Resolve the configured Shadowrocket / Shortcuts URL for on, off, toggle, or open."""
    vpn = config.vpn
    key = str(mode).strip().lower()
    if key == "on":
        return str(vpn.shortcut_url_on or "").strip()
    if key == "off":
        return str(vpn.shortcut_url_off or "").strip()
    if key == "toggle":
        return str(vpn.shortcut_url_toggle or "").strip()
    if key == "open":
        return str(vpn.shortcut_url_open or "").strip()
    raise ValueError(f"Unknown VPN shortcut mode: {mode}")


async def exec_vpn_shortcut_url(
    controller: DeviceController,
    device_id: str,
    url: str,
    *,
    settle_seconds: float = 4.0,
    press_home_after: bool = True,
    outtime_ms: int | None = None,
    log_activity: Any | None = None,
) -> None:
    """Open a VPN URL on the phone via iMouse shortcut_exec_url, then wait and home."""
    from imouse_farm.actions.permission_prompts import tap_open_external_app_allow_if_visible

    target = str(url or "").strip()
    if not target:
        raise ValueError("VPN shortcut URL is not configured")

    sdk_error = ""

    async def _launch(label: str) -> bool:
        nonlocal sdk_error
        ok, sdk_error = await controller.launch_app_with_error(
            device_id, target, outtime_ms=outtime_ms
        )
        if log_activity:
            detail = f" — {sdk_error}" if sdk_error else ""
            await log_activity(
                "info",
                "device",
                f"shortcut_exec_url({target!r}) {label}→ {'ok' if ok else 'failed'}{detail}",
                device_id,
            )
        return ok

    # iOS shows "Allow X to open Shadowrocket?" once per phone; after Allow, shortcuts open directly.
    launched = await _launch("")
    await asyncio.sleep(0.8)
    if await tap_open_external_app_allow_if_visible(
        controller, device_id, log_activity=log_activity
    ):
        if log_activity:
            await log_activity(
                "info",
                "device",
                "Tapped Allow on external-app prompt — retrying shortcut_exec_url",
                device_id,
            )
        await asyncio.sleep(1.0)
        launched = await _launch("retry ")
    elif not launched:
        # Dialog may appear slightly after the failed SDK response on slow devices.
        await asyncio.sleep(0.7)
        if await tap_open_external_app_allow_if_visible(
            controller, device_id, log_activity=log_activity
        ):
            if log_activity:
                await log_activity(
                    "info",
                    "device",
                    "Tapped Allow (delayed) — retrying shortcut_exec_url",
                    device_id,
                )
            await asyncio.sleep(1.0)
            launched = await _launch("retry ")

    if not launched:
        detail = sdk_error or "no iMouse error message"
        raise RuntimeError(f"shortcut_exec_url failed for {target!r} — {detail}")

    logger.info("vpn_shortcut_opened", device_id=device_id, url=target)
    if log_activity:
        await log_activity(
            "info",
            "device",
            f"Opened VPN shortcut URL ({target})",
            device_id,
        )
    settle = max(0.5, float(settle_seconds))
    if log_activity:
        await log_activity(
            "info",
            "device",
            f"Waiting {settle:g}s for VPN shortcut to settle",
            device_id,
        )
    await asyncio.sleep(settle)
    if press_home_after:
        if log_activity:
            await log_activity("info", "device", "Pressing home after VPN shortcut", device_id)
        await controller.press_home(device_id)
        await asyncio.sleep(0.5)


async def ensure_vpn_on_via_shortcut(
    controller: DeviceController,
    config: AppConfig,
    device_id: str,
    *,
    log_activity: Any | None = None,
) -> None:
    """Turn VPN on by opening the configured connect URL on the phone."""
    await exec_vpn_shortcut_url(
        controller,
        device_id,
        vpn_shortcut_url(config, "on"),
        settle_seconds=config.vpn.shortcut_settle_seconds,
        outtime_ms=config.vpn.shortcut_url_timeout_ms,
        log_activity=log_activity,
    )


async def ensure_vpn_off_via_shortcut(
    controller: DeviceController,
    config: AppConfig,
    device_id: str,
    *,
    log_activity: Any | None = None,
) -> None:
    """Turn VPN off by opening the configured disconnect URL on the phone."""
    await exec_vpn_shortcut_url(
        controller,
        device_id,
        vpn_shortcut_url(config, "off"),
        settle_seconds=config.vpn.shortcut_settle_seconds,
        outtime_ms=config.vpn.shortcut_url_timeout_ms,
        log_activity=log_activity,
    )


async def open_shadowrocket_via_shortcut(
    controller: DeviceController,
    config: AppConfig,
    device_id: str,
    *,
    settle_seconds: float | None = None,
    log_activity: Any | None = None,
) -> None:
    """Open Shadowrocket via configured URL shortcut (no home press)."""
    await exec_vpn_shortcut_url(
        controller,
        device_id,
        vpn_shortcut_url(config, "open"),
        settle_seconds=(
            float(settle_seconds)
            if settle_seconds is not None
            else config.vpn.shortcut_settle_seconds
        ),
        outtime_ms=config.vpn.shortcut_url_timeout_ms,
        press_home_after=False,
        log_activity=log_activity,
    )


async def ensure_vpn_on(
    controller: DeviceController,
    config: AppConfig,
    device_id: str,
    *,
    log_activity: Any | None = None,
) -> None:
    """Turn VPN on via configured URL shortcut."""
    await ensure_vpn_on_via_shortcut(
        controller, config, device_id, log_activity=log_activity
    )
    logger.info("vpn_shortcut_on", device_id=device_id)
    if log_activity:
        await log_activity("info", "device", "VPN on (shortcut)", device_id)


async def ensure_vpn_off(
    controller: DeviceController,
    config: AppConfig,
    device_id: str,
    *,
    log_activity: Any | None = None,
) -> None:
    """Turn VPN off via configured URL shortcut."""
    await ensure_vpn_off_via_shortcut(
        controller, config, device_id, log_activity=log_activity
    )
    logger.info("vpn_shortcut_off", device_id=device_id)
    if log_activity:
        await log_activity("info", "device", "VPN off (shortcut)", device_id)


async def ensure_vpn_off_before_album(
    controller: DeviceController,
    config: AppConfig,
    device_manager: DeviceManager,
    device_id: str,
    *,
    log_activity: Any | None = None,
) -> None:
    """Turn VPN off via shortcut before album clear/upload."""
    if log_activity:
        await log_activity(
            "info",
            "device",
            "ensure_vpn_off_before_album — same call as tiktok_prep clear_album step",
            device_id,
        )
    await ensure_vpn_off(controller, config, device_id, log_activity=log_activity)
    await device_manager.set_state(device_id, DeviceState.WAITING, "vpn_off_before_album")
    if log_activity:
        await log_activity(
            "info",
            "device",
            "Device state → WAITING (vpn_off_before_album)",
            device_id,
        )
