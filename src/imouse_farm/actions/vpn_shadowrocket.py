"""Shadowrocket VPN: home → fixed icon tap → vision status → fixed toggle tap → confirm."""

from __future__ import annotations

import asyncio
import base64
import io
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from imouse_farm.config.models import AppConfig, DeviceState
from imouse_farm.controller.device_controller import DeviceController
from imouse_farm.devices.manager import DeviceManager
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

# Home-screen Shadowrocket icon (open app).
SHADOWROCKET_ICON_X = 373
SHADOWROCKET_ICON_Y = 1003
# In-app connect/disconnect control.
SHADOWROCKET_TOGGLE_X = 515
SHADOWROCKET_TOGGLE_Y = 171

TIKTOK_HOME_ICON_X = 507
TIKTOK_HOME_ICON_Y = 1011

VpnStatus = Literal["on", "off"]

_VPN_VISION_MODEL_DEFAULT = "gpt-4o"

_VPN_STATUS_SYSTEM = """Screenshot is of the Shadowrocket iPhone app.
Decide whether the VPN / proxy is currently ON (connected) or OFF (not connected).
Look for Connected / Not Connected / Connecting and the main circular button state.

Reply with EXACTLY one line and nothing else:
STATUS: ON
or
STATUS: OFF

Rules:
- STATUS: ON  → connected / proxy active
- STATUS: OFF → not connected / disconnected
- No markdown, no JSON, no extra text."""


def _vpn_vision_model(app_config: AppConfig) -> str:
    configured = str(getattr(app_config.vpn, "vision_model", "") or "").strip()
    return configured or _VPN_VISION_MODEL_DEFAULT


def _image_detail(model: str) -> str:
    if model.startswith(("gpt-5.4", "gpt-5.5", "gpt-5.6")):
        return "original"
    return "high"


def _is_reasoning_vision_model(model: str) -> bool:
    return model.startswith("gpt-5") or model.startswith("o")


def _parse_vpn_status(raw: str) -> VpnStatus:
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
        "Vision reply must be 'STATUS: ON' or 'STATUS: OFF'; "
        f"got {text[:240]!r}"
    )


def _icon_coords(config: AppConfig) -> tuple[int, int]:
    vpn = config.vpn
    return (
        int(getattr(vpn, "icon_x", None) or SHADOWROCKET_ICON_X),
        int(getattr(vpn, "icon_y", None) or SHADOWROCKET_ICON_Y),
    )


def _toggle_coords(config: AppConfig) -> tuple[int, int]:
    vpn = config.vpn
    return (
        int(getattr(vpn, "toggle_x", None) or SHADOWROCKET_TOGGLE_X),
        int(getattr(vpn, "toggle_y", None) or SHADOWROCKET_TOGGLE_Y),
    )


async def _openai_vpn_status(
    client: Any,
    *,
    model: str,
    b64_jpeg: str,
    image_detail: str,
) -> str:
    messages = [
        {"role": "system", "content": _VPN_STATUS_SYSTEM},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Is Shadowrocket VPN ON or OFF? Reply STATUS: ON or STATUS: OFF only.",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64_jpeg}",
                        "detail": image_detail,
                    },
                },
            ],
        },
    ]
    create_kwargs: dict[str, Any] = {"model": model, "messages": messages}
    if _is_reasoning_vision_model(model):
        create_kwargs["max_completion_tokens"] = 4096
        create_kwargs["reasoning_effort"] = "low"
    else:
        create_kwargs["max_tokens"] = 20
        create_kwargs["temperature"] = 0

    try:
        response = await client.chat.completions.create(**create_kwargs)
    except Exception as exc:
        msg = str(exc).lower()
        if "reasoning_effort" in msg or "unexpected" in msg or "unsupported" in msg:
            create_kwargs.pop("reasoning_effort", None)
            response = await client.chat.completions.create(**create_kwargs)
        else:
            raise
    return (response.choices[0].message.content or "").strip()


async def _screenshot_jpeg(
    controller: DeviceController,
    device_id: str,
    *,
    app_config: AppConfig,
    log_activity: Any | None = None,
) -> tuple[str, int, int]:
    from PIL import Image

    from imouse_farm.workflows.vision_recovery import _to_jpeg

    screenshot_bytes = await controller.capture_screenshot(device_id)
    if not screenshot_bytes:
        raise RuntimeError("Screenshot returned no data")
    jpeg_bytes = _to_jpeg(screenshot_bytes)
    if not jpeg_bytes:
        raise RuntimeError("Could not convert screenshot to JPEG")

    img = Image.open(io.BytesIO(jpeg_bytes))
    width, height = img.size
    b64 = base64.b64encode(jpeg_bytes).decode("ascii")

    now = datetime.now()
    safe_id = str(device_id).replace(":", "-").replace("/", "-")
    debug_dir = (
        Path(app_config.gallery.base_directory).resolve()
        / "_debug"
        / "vpn_shadowrocket_vision"
        / now.strftime("%Y-%m-%d")
    )
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_path = debug_dir / f"vision_{now.strftime('%H%M%S')}_{safe_id}.jpg"
    try:
        debug_path.write_bytes(jpeg_bytes)
        if log_activity:
            await log_activity(
                "info",
                "device",
                f"VPN vision screenshot saved — {debug_path}",
                device_id,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("vpn_vision_screenshot_save_failed", error=str(exc))

    return b64, width, height


async def vision_read_vpn_status(
    controller: DeviceController,
    device_id: str,
    *,
    app_config: AppConfig,
    log_activity: Any | None = None,
) -> VpnStatus:
    """Screenshot Shadowrocket UI and return STATUS: ON/OFF."""
    from openai import AsyncOpenAI

    openai_cfg = app_config.openai
    api_key = (os.environ.get("OPENAI_API_KEY") or openai_cfg.api_key or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")
    if not openai_cfg.enabled:
        raise RuntimeError("OpenAI vision is disabled")

    b64, width, height = await _screenshot_jpeg(
        controller, device_id, app_config=app_config, log_activity=log_activity
    )
    model = _vpn_vision_model(app_config)
    client = AsyncOpenAI(api_key=api_key)

    models_to_try = [model]
    if model != "gpt-4o":
        models_to_try.append("gpt-4o")

    last_raw = ""
    for attempt_model in models_to_try:
        if log_activity:
            await log_activity(
                "info",
                "device",
                f"VPN vision status: model={attempt_model} screen={width}x{height}",
                device_id,
            )
        try:
            raw = await _openai_vpn_status(
                client,
                model=attempt_model,
                b64_jpeg=b64,
                image_detail=_image_detail(attempt_model),
            )
        except Exception as api_exc:
            logger.warning(
                "vpn_vision_status_api_failed",
                model=attempt_model,
                error=str(api_exc),
            )
            continue
        last_raw = raw
        if log_activity:
            await log_activity(
                "info",
                "device",
                f"VPN vision raw ({attempt_model}): {raw[:120]!r}",
                device_id,
            )
        if not raw:
            continue
        try:
            status = _parse_vpn_status(raw)
        except Exception:
            continue
        logger.info("vpn_vision_status", device_id=device_id, status=status, model=attempt_model)
        return status

    raise RuntimeError(f"VPN vision status failed — raw={last_raw[:180]!r}")


async def open_shadowrocket(
    controller: DeviceController,
    config: AppConfig,
    device_id: str,
    *,
    settle_seconds: float | None = None,
    log_activity: Any | None = None,
) -> None:
    """Go home and tap the fixed Shadowrocket home-screen icon."""
    from imouse_farm.actions.permission_prompts import tap_local_network_ok_if_visible

    ix, iy = _icon_coords(config)
    settle = float(
        settle_seconds
        if settle_seconds is not None
        else config.vpn.app_settle_seconds
    )

    await controller.press_home(device_id)
    await asyncio.sleep(0.6)
    if log_activity:
        await log_activity(
            "info",
            "device",
            f"Tapping Shadowrocket icon at ({ix}, {iy})",
            device_id,
        )
    await controller.tap(device_id, ix, iy)
    await asyncio.sleep(max(0.5, settle))
    await tap_local_network_ok_if_visible(
        controller, device_id, log_activity=log_activity
    )


async def ensure_vpn(
    controller: DeviceController,
    config: AppConfig,
    device_id: str,
    *,
    want: VpnStatus,
    log_activity: Any | None = None,
    press_home_after: bool = True,
) -> None:
    """Home → open Shadowrocket → vision status → maybe tap fixed toggle → confirm."""
    tx, ty = _toggle_coords(config)
    after_toggle = float(config.vpn.after_toggle_settle_seconds)
    confirm_settle = float(config.vpn.confirm_settle_seconds)

    await open_shadowrocket(controller, config, device_id, log_activity=log_activity)

    status = await vision_read_vpn_status(
        controller, device_id, app_config=config, log_activity=log_activity
    )
    if status == want:
        if log_activity:
            await log_activity(
                "info",
                "device",
                f"Shadowrocket already {want.upper()} — skip toggle",
                device_id,
            )
    else:
        if log_activity:
            await log_activity(
                "info",
                "device",
                f"VPN is {status.upper()}; tapping toggle ({tx}, {ty}) → {want.upper()}",
                device_id,
            )
        await controller.tap(device_id, tx, ty)
        await asyncio.sleep(max(0.5, after_toggle))

    if confirm_settle > 0:
        await asyncio.sleep(confirm_settle)

    confirmed = await vision_read_vpn_status(
        controller, device_id, app_config=config, log_activity=log_activity
    )
    if confirmed != want:
        raise RuntimeError(
            f"VPN vision confirmed {confirmed.upper()}, expected {want.upper()}"
        )
    if log_activity:
        await log_activity(
            "info",
            "device",
            f"VPN vision confirmed {want.upper()}",
            device_id,
        )

    if press_home_after:
        await controller.press_home(device_id)
        await asyncio.sleep(0.5)


async def ensure_vpn_on(
    controller: DeviceController,
    config: AppConfig,
    device_id: str,
    *,
    log_activity: Any | None = None,
) -> None:
    await ensure_vpn(
        controller, config, device_id, want="on", log_activity=log_activity
    )
    logger.info("vpn_on", device_id=device_id)


async def ensure_vpn_off(
    controller: DeviceController,
    config: AppConfig,
    device_id: str,
    *,
    log_activity: Any | None = None,
) -> None:
    await ensure_vpn(
        controller, config, device_id, want="off", log_activity=log_activity
    )
    logger.info("vpn_off", device_id=device_id)


async def ensure_vpn_off_before_album(
    controller: DeviceController,
    config: AppConfig,
    device_manager: DeviceManager,
    device_id: str,
    *,
    log_activity: Any | None = None,
) -> None:
    if log_activity:
        await log_activity(
            "info",
            "device",
            "ensure_vpn_off_before_album — home icon + vision toggle",
            device_id,
        )
    await ensure_vpn_off(controller, config, device_id, log_activity=log_activity)
    await device_manager.set_state(device_id, DeviceState.WAITING, "vpn_off_before_album")
