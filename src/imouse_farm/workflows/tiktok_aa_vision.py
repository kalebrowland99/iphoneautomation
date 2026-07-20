"""Locate TikTok editor Aa (+ editor icon) via OpenAI vision; tap Aa now, save editor for later."""

from __future__ import annotations

import base64
import io
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

from imouse_farm.config.models import AppConfig
from imouse_farm.utils.logging import get_logger
from imouse_farm.workflows.account_switch import (
    _account_switcher_image_detail,
    _openai_account_switcher_coords,
)
from imouse_farm.workflows.vision_recovery import _to_jpeg

logger = get_logger(__name__)

LogFn = Callable[..., Awaitable[None]]

AA_VISION_MODEL_DEFAULT = "gpt-5.5"
EDITOR_FALLBACK_XY = (566, 247)
EDITOR_TEMPLATE_NAME = "editor.jpg"

# Per-device editor toolbar coords from the last successful Aa+editor vision locate.
_saved_editor_coords: dict[str, tuple[int, int]] = {}

_AA_VISION_SYSTEM = """\
Device: iPhone 7 or iPhone 8 (compact home-button phone, TikTok’s smaller older UI).
Screenshot is {width}×{height} pixels — these are iMouse cast / tap coordinates.
Return tap coordinates in THIS pixel space only (not iOS points, not a newer iPhone \
layout). Origin is top-left; X rightward, Y downward; X∈[0,{width}], Y∈[0,{height}].

Locate TWO controls on the RIGHT-SIDE vertical toolbar of the TikTok video editor:

1) Aa — the text tool labeled "Aa" / "AA" used to add on-screen text.
   Landmark: Aa is ALWAYS the next icon ABOVE the sticker icon (rounded square /
   sticky-note face / sticker pack glyph) on that same right-side column.
2) Editor — the clip/timeline editor icon ABOVE Aa on the same toolbar. A reference \
crop of this icon is attached (first image). Match that shape: rounded rectangular \
frame with a filled center and small left/right chevrons (‹ ›).
   Landmark: Editor is ALWAYS the next icon DIRECTLY UNDER the Settings gear (top-right \
toolbar / gear icon) on that same right-side column.
Do NOT confuse either with stickers, smileys, music, Settings gear itself, Share, Done, or Next.

Editor appearance:
- The EDITOR ICON ITSELF IS WHITE (light glyph).
- The BACKGROUND BEHIND it can change (moving video / bright or dark frames). Ignore \
background colors; match the white icon silhouette from the reference crop.
- Use the soft drop-shadow / dark halo around the white icon when contrast is low.

Visibility (important):
- The preview behind the toolbar is a moving video. "Aa" and editor are often white \
(or light) and can sit on bright/white video frames — glyphs may look missing, faded, \
or incomplete.
- Do not conclude a control is absent just because it blends into the background.
- Tap the CENTER of each control, not a neighboring toolbar icon.

Rules:
- Editor is the next icon under the Settings gear; Aa is the next icon above the sticker.
- Editor is typically ABOVE Aa on the same right-edge column (similar X, smaller Y).
- Reply with exactly four lines and nothing else:
AA_X: <integer>
AA_Y: <integer>
EDITOR_X: <integer>
EDITOR_Y: <integer>
"""


def editor_template_path(app_config: AppConfig) -> Path:
    templates_dir = Path(
        getattr(app_config.analysis, "templates_directory", "") or "config/templates"
    )
    return templates_dir / EDITOR_TEMPLATE_NAME


def load_editor_template_b64(app_config: AppConfig) -> str | None:
    """Load ``editor.jpg`` template as JPEG base64 for the vision reference image."""
    path = editor_template_path(app_config)
    if not path.is_file():
        logger.warning("editor_template_missing", path=str(path))
        return None
    try:
        raw = path.read_bytes()
        jpeg = _to_jpeg(raw) or raw
        return base64.b64encode(jpeg).decode("ascii")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "editor_template_load_failed",
            path=str(path),
            error=str(exc),
        )
        return None


@dataclass(frozen=True)
class AaEditorLocateResult:
    aa_x: int
    aa_y: int
    editor_x: int
    editor_y: int
    reason: str
    model: str
    screen_width: int
    screen_height: int
    raw: str


def aa_vision_model(app_config: AppConfig) -> str:
    configured = str(
        getattr(app_config.openai, "aa_vision_model", "") or ""
    ).strip()
    return configured or AA_VISION_MODEL_DEFAULT


def save_editor_coords(device_id: str, x: int, y: int) -> None:
    key = str(device_id or "").strip()
    if not key:
        return
    _saved_editor_coords[key] = (int(x), int(y))
    logger.info("editor_coords_saved", device_id=key, x=int(x), y=int(y))


def get_saved_editor_coords(device_id: str) -> tuple[int, int] | None:
    key = str(device_id or "").strip()
    if not key:
        return None
    return _saved_editor_coords.get(key)


def clear_saved_editor_coords(device_id: str | None = None) -> None:
    if device_id is None:
        _saved_editor_coords.clear()
        return
    key = str(device_id or "").strip()
    if key:
        _saved_editor_coords.pop(key, None)


def editor_tap_coords(device_id: str) -> tuple[int, int, str]:
    """Return (x, y, source) for the editor icon; saved vision coords or hardcoded fallback."""
    saved = get_saved_editor_coords(device_id)
    if saved is not None:
        return saved[0], saved[1], "vision_saved"
    return EDITOR_FALLBACK_XY[0], EDITOR_FALLBACK_XY[1], "fallback"


def _validate_aa_coords(x: int, y: int, width: int, height: int) -> None:
    """Reject taps that are clearly not on the right-side editor toolbar."""
    if width <= 0 or height <= 0:
        return
    if x < int(width * 0.62):
        raise RuntimeError(
            f"Aa vision tap ({x}, {y}) too far left for right-side toolbar "
            f"(screen {width}x{height})"
        )
    if y < int(height * 0.12) or y > int(height * 0.72):
        raise RuntimeError(
            f"Aa vision tap ({x}, {y}) outside typical Aa toolbar band "
            f"(screen {width}x{height})"
        )


def _validate_editor_coords(
    x: int,
    y: int,
    *,
    aa_x: int,
    aa_y: int,
    width: int,
    height: int,
) -> None:
    """Reject editor taps that are clearly not the right-side icon above Aa."""
    if width <= 0 or height <= 0:
        return
    if x < int(width * 0.62):
        raise RuntimeError(
            f"Editor vision tap ({x}, {y}) too far left for right-side toolbar "
            f"(screen {width}x{height})"
        )
    if y < int(height * 0.11) or y > int(height * 0.55):
        raise RuntimeError(
            f"Editor vision tap ({x}, {y}) outside typical editor toolbar band "
            f"(screen {width}x{height}; rejects Settings-gear top corner)"
        )
    if y >= aa_y - 8:
        raise RuntimeError(
            f"Editor vision tap ({x}, {y}) is not clearly above Aa ({aa_x}, {aa_y})"
        )
    if abs(x - aa_x) > int(width * 0.12):
        raise RuntimeError(
            f"Editor vision tap ({x}, {y}) too far from Aa column X={aa_x} "
            f"(screen {width}x{height})"
        )


def _line_int(text: str, label: str) -> int | None:
    match = re.search(
        rf"(?im)^\s*{re.escape(label)}\s*:\s*(-?\d+)\s*$",
        text,
    )
    if match:
        return int(match.group(1))
    inline = re.search(rf"(?i)\b{re.escape(label)}\s*:\s*(-?\d+)\b", text)
    if inline:
        return int(inline.group(1))
    return None


def parse_aa_editor_coords(raw: str) -> tuple[int, int, int, int]:
    """Extract AA_X/AA_Y/EDITOR_X/EDITOR_Y from a vision reply."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = "\n".join(text.splitlines()[1:])
        if text.endswith("```"):
            text = text[: text.rfind("```")]
        text = text.strip()

    aa_x = _line_int(text, "AA_X")
    aa_y = _line_int(text, "AA_Y")
    editor_x = _line_int(text, "EDITOR_X")
    editor_y = _line_int(text, "EDITOR_Y")

    # Backward-compatible: plain X:/Y: only → treat as Aa; no editor.
    if aa_x is None and aa_y is None:
        plain_x = _line_int(text, "X")
        plain_y = _line_int(text, "Y")
        if plain_x is not None and plain_y is not None:
            raise RuntimeError(
                "Vision reply only had X/Y (Aa) — need AA_X/AA_Y and EDITOR_X/EDITOR_Y"
            )

    missing = [
        name
        for name, val in (
            ("AA_X", aa_x),
            ("AA_Y", aa_y),
            ("EDITOR_X", editor_x),
            ("EDITOR_Y", editor_y),
        )
        if val is None
    ]
    if missing:
        raise RuntimeError(
            "Vision reply must include AA_X, AA_Y, EDITOR_X, EDITOR_Y; "
            f"missing {', '.join(missing)}; got {text[:240]!r}"
        )
    return int(aa_x), int(aa_y), int(editor_x), int(editor_y)


async def vision_locate_aa_button(
    controller: Any,
    device_id: str,
    *,
    app_config: AppConfig,
    log_activity: LogFn | None = None,
) -> tuple[int, int, str]:
    """Locate Aa (+ editor); save editor coords; return Aa tap (x, y, reason)."""
    result = await vision_locate_aa_and_editor(
        controller,
        device_id,
        app_config=app_config,
        log_activity=log_activity,
    )
    save_editor_coords(device_id, result.editor_x, result.editor_y)
    return result.aa_x, result.aa_y, result.reason


async def vision_locate_aa_and_editor(
    controller: Any,
    device_id: str,
    *,
    app_config: AppConfig,
    log_activity: LogFn | None = None,
) -> AaEditorLocateResult:
    """Screenshot the editor and ask vision for Aa + editor toolbar coords."""
    from PIL import Image

    openai_cfg = app_config.openai
    api_key = (os.environ.get("OPENAI_API_KEY") or openai_cfg.api_key or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")
    if not getattr(openai_cfg, "enabled", True):
        raise RuntimeError("OpenAI is disabled — cannot locate Aa via vision")

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
        / "aa_vision"
        / now.strftime("%Y-%m-%d")
    )
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_path = debug_dir / f"vision_{now.strftime('%H%M%S')}_{safe_id}.jpg"
    try:
        debug_path.write_bytes(jpeg_bytes)
        logger.info(
            "aa_vision_screenshot_saved",
            device_id=device_id,
            path=str(debug_path),
        )
        if log_activity:
            await log_activity(
                "info",
                "workflow",
                f"Aa vision screenshot saved — {debug_path}",
                device_id,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "aa_vision_screenshot_save_failed",
            device_id=device_id,
            error=str(exc),
        )

    from openai import AsyncOpenAI

    model = aa_vision_model(app_config)
    client = AsyncOpenAI(api_key=api_key)
    system = _AA_VISION_SYSTEM.format(width=width, height=height)
    editor_ref_b64 = load_editor_template_b64(app_config)
    reference_images: list[tuple[str, str]] = []
    if editor_ref_b64:
        reference_images.append(
            (
                "Reference crop of the EDITOR icon (white glyph; match this shape on "
                "the live screenshot — background behind it may differ):",
                editor_ref_b64,
            )
        )
        if log_activity:
            await log_activity(
                "info",
                "workflow",
                f"Aa+editor vision: attached editor template {editor_template_path(app_config)}",
                device_id,
            )
    else:
        if log_activity:
            await log_activity(
                "warn",
                "workflow",
                "Aa+editor vision: editor.jpg template missing — text description only",
                device_id,
            )
    user_text = (
        "Locate Aa and the editor icon on the right-side toolbar. "
        "Use the attached editor reference crop for EDITOR_X/EDITOR_Y "
        "(white icon; background can change). Reply with exactly:\n"
        "AA_X: <integer>\nAA_Y: <integer>\nEDITOR_X: <integer>\nEDITOR_Y: <integer>"
    )

    models_to_try = [model]
    if model != "gpt-4o":
        models_to_try.append("gpt-4o")

    last_raw = ""
    last_model = model
    parse_error: Exception | None = None
    for attempt_model in models_to_try:
        detail = _account_switcher_image_detail(attempt_model)
        if log_activity:
            await log_activity(
                "info",
                "workflow",
                (
                    f"Aa+editor vision: model={attempt_model} detail={detail} "
                    f"screen={width}x{height} "
                    f"editor_ref={'yes' if reference_images else 'no'}"
                ),
                device_id,
            )
        try:
            raw = await _openai_account_switcher_coords(
                client,
                model=attempt_model,
                system=system,
                user_text=user_text,
                b64_jpeg=b64,
                image_detail=detail,
                reference_images=reference_images or None,
                max_output_tokens=120 if not attempt_model.startswith(("gpt-5", "o")) else None,
            )
        except Exception as api_exc:
            logger.warning(
                "aa_vision_api_failed",
                device_id=device_id,
                model=attempt_model,
                error=str(api_exc),
            )
            if log_activity:
                await log_activity(
                    "warn",
                    "workflow",
                    f"Aa+editor vision API error ({attempt_model}): {api_exc}",
                    device_id,
                )
            last_raw = ""
            last_model = attempt_model
            parse_error = api_exc
            continue

        last_raw = raw
        last_model = attempt_model
        logger.info(
            "aa_vision_raw_reply",
            device_id=device_id,
            model=attempt_model,
            raw=raw[:500],
            screenshot=str(debug_path),
        )
        reply_msg = f"Aa+editor vision raw reply ({attempt_model}): {raw[:300]!r}"
        if log_activity:
            await log_activity("info", "workflow", reply_msg, device_id)
        try:
            reply_path = debug_path.with_suffix(".reply.txt")
            reply_path.write_text(
                f"model={attempt_model}\ndetail={detail}\nscreen={width}x{height}\n\n{raw}\n",
                encoding="utf-8",
            )
        except Exception as save_exc:  # noqa: BLE001
            logger.warning(
                "aa_vision_reply_save_failed",
                device_id=device_id,
                error=str(save_exc),
            )
        if not raw:
            if log_activity and attempt_model != models_to_try[-1]:
                await log_activity(
                    "warn",
                    "workflow",
                    f"Empty reply from {attempt_model} — retrying with fallback model",
                    device_id,
                )
            continue
        try:
            aa_x, aa_y, editor_x, editor_y = parse_aa_editor_coords(raw)
            reason = "Aa text toolbar button"
            _validate_aa_coords(aa_x, aa_y, width, height)
            _validate_editor_coords(
                editor_x,
                editor_y,
                aa_x=aa_x,
                aa_y=aa_y,
                width=width,
                height=height,
            )
        except Exception as exc:
            parse_error = exc
            logger.warning(
                "aa_vision_parse_failed",
                device_id=device_id,
                model=attempt_model,
                raw=raw[:300],
                error=str(exc),
            )
            continue

        logger.info(
            "aa_vision_locate",
            device_id=device_id,
            aa_x=aa_x,
            aa_y=aa_y,
            editor_x=editor_x,
            editor_y=editor_y,
            reason=reason,
            screen=(width, height),
            model=attempt_model,
            detail=detail,
            screenshot=str(debug_path),
            raw=raw[:200],
        )
        tap_msg = (
            f"Aa+editor vision: Aa=({aa_x}, {aa_y}) editor=({editor_x}, {editor_y}) "
            f"[{attempt_model}]"
        )
        if log_activity:
            await log_activity("info", "workflow", tap_msg, device_id)
        try:
            meta_path = debug_path.with_suffix(".tap.txt")
            meta_path.write_text(
                f"model={attempt_model}\ndetail={detail}\nscreen={width}x{height}\n"
                f"aa_x={aa_x}\naa_y={aa_y}\n"
                f"editor_x={editor_x}\neditor_y={editor_y}\n"
                f"reason={reason}\n\n{raw}\n",
                encoding="utf-8",
            )
        except Exception as save_exc:  # noqa: BLE001
            logger.warning(
                "aa_vision_tap_meta_save_failed",
                device_id=device_id,
                error=str(save_exc),
            )
        return AaEditorLocateResult(
            aa_x=aa_x,
            aa_y=aa_y,
            editor_x=editor_x,
            editor_y=editor_y,
            reason=reason,
            model=attempt_model,
            screen_width=width,
            screen_height=height,
            raw=raw,
        )

    detail = str(parse_error) if parse_error else "empty or unparseable reply"
    raise RuntimeError(
        f"Could not parse Aa/editor coords from {last_model}: "
        f"{last_raw[:180]!r} ({detail})"
    )


async def tap_aa_via_vision(
    controller: Any,
    device_id: str,
    *,
    app_config: AppConfig,
    log_activity: LogFn | None = None,
) -> bool:
    """Locate Aa + editor with vision, save editor coords, tap Aa once."""
    result = await vision_locate_aa_and_editor(
        controller,
        device_id,
        app_config=app_config,
        log_activity=log_activity,
    )
    save_editor_coords(device_id, result.editor_x, result.editor_y)
    if log_activity:
        await log_activity(
            "info",
            "workflow",
            (
                f"Saved editor coords ({result.editor_x}, {result.editor_y}) "
                f"for later tap [{result.model}]"
            ),
            device_id,
        )
    logger.info(
        "aa_vision_tap",
        device_id=device_id,
        x=result.aa_x,
        y=result.aa_y,
        editor_x=result.editor_x,
        editor_y=result.editor_y,
        reason=result.reason,
    )
    return bool(await controller.tap(device_id, int(result.aa_x), int(result.aa_y)))


async def tap_saved_editor(
    controller: Any,
    device_id: str,
    *,
    log_activity: LogFn | None = None,
) -> bool:
    """Tap the editor icon using coords saved during the Aa vision step."""
    x, y, source = editor_tap_coords(device_id)
    msg = f"Tap editor ({x}, {y}) source={source}"
    logger.info("editor_saved_tap", device_id=device_id, x=x, y=y, source=source)
    if log_activity:
        level = "info" if source == "vision_saved" else "warn"
        await log_activity(level, "workflow", msg, device_id)
    return bool(await controller.tap(device_id, int(x), int(y)))
