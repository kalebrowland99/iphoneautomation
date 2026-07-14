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
    from imouse_farm.actions.permission_prompts import (
        tap_local_network_ok_if_visible,
        tap_open_external_app_allow_if_visible,
    )

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

    async def _dismiss_vpn_permission_sheets() -> bool:
        """Tap Allow (open Shadowrocket) and/or OK (local network) if either sheet is up."""
        did = False
        if await tap_open_external_app_allow_if_visible(
            controller, device_id, log_activity=log_activity
        ):
            did = True
        if await tap_local_network_ok_if_visible(
            controller, device_id, log_activity=log_activity
        ):
            did = True
        return did

    # iOS shows "Allow X to open Shadowrocket?" once per phone; after Allow, shortcuts open directly.
    # Local-network OK can also appear the first time Shadowrocket connects.
    launched = await _launch("")
    await asyncio.sleep(0.8)
    if await _dismiss_vpn_permission_sheets():
        if log_activity:
            await log_activity(
                "info",
                "device",
                "Dismissed VPN permission sheet(s) — retrying shortcut_exec_url",
                device_id,
            )
        await asyncio.sleep(1.0)
        launched = await _launch("retry ")
    elif not launched:
        # Dialog may appear slightly after the failed SDK response on slow devices.
        await asyncio.sleep(0.7)
        if await _dismiss_vpn_permission_sheets():
            if log_activity:
                await log_activity(
                    "info",
                    "device",
                    "Dismissed VPN permission sheet(s) (delayed) — retrying shortcut_exec_url",
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
    # Local-network sheet usually appears right after Shadowrocket opens; poll briefly,
    # then sleep the rest (permission watcher also taps OK if it shows later).
    early = min(settle, 12.0)
    early_deadline = asyncio.get_running_loop().time() + early
    while True:
        remaining = early_deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        await tap_local_network_ok_if_visible(
            controller, device_id, log_activity=log_activity
        )
        await asyncio.sleep(min(2.0, remaining))
    leftover = settle - early
    if leftover > 0:
        await asyncio.sleep(leftover)
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
    """Turn VPN on via shortcut; wait for shortcut_exec_url (no vision confirm)."""
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
    """Turn VPN off via shortcut; wait for shortcut_exec_url (no vision confirm)."""
    await ensure_vpn_off_via_shortcut(
        controller, config, device_id, log_activity=log_activity
    )
    logger.info("vpn_shortcut_off", device_id=device_id)
    if log_activity:
        await log_activity("info", "device", "VPN off (shortcut)", device_id)


VpnStatus = Literal["on", "off"]

_VPN_STATUS_MODEL = "gpt-4o"

_VPN_STATUS_SYSTEM = """You are looking at an iPhone screenshot.
Check ONLY the status bar in the TOP-LEFT corner of the screen.

When a VPN is connected, iOS shows a small "VPN" label in the top-left status bar
(near the time / signal area). When VPN is off, that "VPN" label is absent.

Reply with EXACTLY one line and nothing else:
STATUS: ON
or
STATUS: OFF

Rules:
- STATUS: ON  → the small "VPN" text is visible in the top-left status bar
- STATUS: OFF → no "VPN" text in the top-left status bar
- Ignore the rest of the screen (apps, Shadowrocket, home icons, etc.)
- No JSON, no markdown, no extra text."""


def _parse_vpn_status(raw: str) -> VpnStatus:
    """Parse a vision reply of the form `STATUS: ON` / `STATUS: OFF`."""
    import re

    text = (raw or "").strip()
    if text.startswith("```"):
        text = "\n".join(text.splitlines()[1:])
        if text.endswith("```"):
            text = text[: text.rfind("```")]
        text = text.strip()

    match = re.search(r"(?im)^\s*STATUS\s*:\s*(ON|OFF)\s*$", text)
    if match:
        return "on" if match.group(1).upper() == "ON" else "off"

    inline = re.search(r"(?i)\bSTATUS\s*:\s*(ON|OFF)\b", text)
    if inline:
        return "on" if inline.group(1).upper() == "ON" else "off"

    raise RuntimeError(
        "Vision reply must be exactly 'STATUS: ON' or 'STATUS: OFF'; "
        f"got {text[:240]!r}"
    )


async def _vision_read_vpn_status(
    controller: DeviceController,
    device_id: str,
    *,
    app_config: AppConfig,
) -> VpnStatus:
    """Screenshot and ask GPT-4o if the top-left status bar shows VPN (debug only)."""
    import base64
    import os

    from imouse_farm.workflows.vision_recovery import _to_jpeg

    openai_cfg = app_config.openai
    api_key = (os.environ.get("OPENAI_API_KEY") or openai_cfg.api_key or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")
    if not openai_cfg.enabled:
        raise RuntimeError("OpenAI vision is disabled")

    screenshot_bytes = await controller.capture_screenshot(device_id)
    if not screenshot_bytes:
        raise RuntimeError("Screenshot returned no data")
    jpeg_bytes = _to_jpeg(screenshot_bytes)
    if not jpeg_bytes:
        raise RuntimeError("Could not convert screenshot to JPEG")
    b64 = base64.b64encode(jpeg_bytes).decode("ascii")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model=_VPN_STATUS_MODEL,
        max_tokens=20,
        temperature=0,
        messages=[
            {"role": "system", "content": _VPN_STATUS_SYSTEM},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Look only at the top-left status bar. "
                            "Is the small 'VPN' label visible? "
                            "Reply with exactly one line: STATUS: ON or STATUS: OFF"
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
        status = _parse_vpn_status(raw)
    except Exception as exc:
        logger.warning(
            "vpn_status_vision_parse_failed",
            device_id=device_id,
            raw=raw[:200],
            error=str(exc),
        )
        raise RuntimeError(f"Could not parse VPN status from: {raw[:180]!r}") from exc
    logger.info(
        "vpn_status_vision",
        device_id=device_id,
        status=status,
        raw=raw[:80],
        model=_VPN_STATUS_MODEL,
    )
    return status


async def confirm_vpn_status_via_vision(
    controller: DeviceController,
    config: AppConfig,
    device_id: str,
    *,
    want: VpnStatus,
    log_activity: Any | None = None,
    settle_seconds: float | None = None,
) -> VpnStatus:
    """Go home, then confirm VPN via status-bar label (debug only; not used in production)."""
    settle = float(
        settle_seconds
        if settle_seconds is not None
        else config.vpn.confirm_settle_seconds
    )
    if log_activity:
        await log_activity(
            "info",
            "device",
            f"Waiting {settle:g}s then checking status-bar VPN label (top-left)",
            device_id,
        )
    await controller.press_home(device_id)
    await asyncio.sleep(max(0.5, settle))

    status = await _vision_read_vpn_status(
        controller, device_id, app_config=config
    )
    if log_activity:
        await log_activity(
            "info",
            "device",
            f"VPN vision status: {status.upper()} (want {want.upper()})",
            device_id,
        )
    if status != want:
        raise RuntimeError(
            f"VPN vision confirmed {status.upper()}, expected {want.upper()}"
        )
    return status


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
