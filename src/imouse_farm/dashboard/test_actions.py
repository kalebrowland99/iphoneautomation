"""Dashboard debug tests — template taps, OCR taps, and isolated workflow actions.

Add a new debug test
--------------------
**Template tap** (JPG in ``config/templates/``):
    Add an entry under ``ui_elements`` in ``config/workflows/screen_states.yaml``.
    It appears in the Debug dropdown automatically as ``Tap <name>``.

**Text tap** (Allow, Delete, etc.):
    Add to ``MANUAL_DEBUG_TESTS`` below with ``kind: tap_ocr`` and a ``texts`` list.

**Custom action** (e.g. gallery upload):
    Add to ``MANUAL_DEBUG_TESTS`` with a new ``kind`` and handle it in ``run_debug_test``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Literal, TypedDict

import yaml
from fastapi import HTTPException

from imouse_farm.actions.permission_prompts import UPLOAD_PERMISSION_TEXTS
from imouse_farm.config.models import ActionType
from imouse_farm.utils.gallery import list_media_files, phone_gallery_folder

from imouse_farm.post.post_caption_store import get_post_caption

DebugKind = Literal[
    "tap",
    "upload_gallery",
    "album_clear",
    "album_list",
    "tap_ocr",
    "open_photos_spotlight",
    "tap_xy",
    "swipe",
    "drag",
    "type_caption",
]

_POST_TEMPLATE_NAMES = frozenset({"plus", "gallery", "aa", "border", "border2", "editor"})

_POST_TEMPLATE_LABELS: dict[str, str] = {
    "plus": "Post: Tap plus (+ button)",
    "gallery": "Post: Tap gallery — after tapping plus",
    "aa": "Post: Tap aa (add text) — after dismissing music",
    "border": "Post: Tap border — after typing caption",
    "border2": "Post: Tap border2 — after typing caption",
    "editor": "Post: Tap editor — after Done",
}

_POST_DEBUG_LIST_PRIORITY = (
    "tap-plus",
    "tap-gallery",
    "post-tap-gallery-item",
    "post-tap-music",
    "post-tap-favorites",
    "post-tap-hvitserk",
    "post-dismiss-music",
    "tap-aa",
    "post-type-caption",
    "tap-border",
    "tap-border2",
    "post-tap-done",
    "tap-editor",
    "post-swipe-left",
    "post-tap-text-scrub",
    "post-drag-trim",
)

OFFLINE_HINT = "Device offline — click Connect AirPlay first"

# Mirror resolution ~406x720 — swipe down from center to open Spotlight (not top edge).
SPOTLIGHT_SWIPE: dict[str, int | str] = {
    "direction": "down",
    "sx": 203,
    "sy": 360,
    "ex": 203,
    "ey": 580,
}


class DebugTest(TypedDict, total=False):
    label: str
    kind: DebugKind
    group: str  # prep | post
    detection: str
    texts: list[str]
    x: int
    y: int
    x1: int
    y1: int
    x2: int
    y2: int
    direction: str
    distance: int
    direction: str
    sx: int
    sy: int
    ex: int
    ey: int
    duration_ms: int
    move_ms: int
    hold_ms: int
    wait_timeout_seconds: float
    threshold: float
    prefer_top: bool
    hint: str
    offline_hint: str


# Manual tests override auto-generated template entries with the same id.
MANUAL_DEBUG_TESTS: dict[str, DebugTest] = {
    "upload-gallery": {
        "label": "Upload gallery files",
        "kind": "upload_gallery",
        "group": "prep",
        "offline_hint": OFFLINE_HINT,
    },
    "clear-album": {
        "label": "Clear photo library",
        "kind": "album_clear",
        "group": "prep",
        "offline_hint": OFFLINE_HINT,
    },
    "list-album": {
        "label": "List album contents (Recents)",
        "kind": "album_list",
        "group": "prep",
        "offline_hint": OFFLINE_HINT,
    },
    "tap-ocr-allow": {
        "label": "Tap Allow / Always Allow",
        "kind": "tap_ocr",
        "group": "prep",
        "texts": list(UPLOAD_PERMISSION_TEXTS),
        "hint": "Show the photos permission dialog on screen first.",
        "offline_hint": OFFLINE_HINT,
    },
    "tap-ocr-delete": {
        "label": "Tap Delete",
        "kind": "tap_ocr",
        "group": "prep",
        "texts": ["Delete"],
        "hint": "Show the delete confirmation dialog on screen first.",
        "offline_hint": OFFLINE_HINT,
    },
    "open-photos-spotlight": {
        "label": "Open Photos (Spotlight)",
        "kind": "open_photos_spotlight",
        "group": "prep",
        "offline_hint": OFFLINE_HINT,
    },
}

TIKTOK_POST_DEBUG_TESTS: dict[str, DebugTest] = {
    "post-tap-gallery-item": {
        "label": "Post: Tap gallery item (82, 201) — after tapping gallery",
        "kind": "tap_xy",
        "group": "post",
        "x": 82,
        "y": 201,
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-music": {
        "label": "Post: Tap music gallery (194, 39) — after tapping gallery item",
        "kind": "tap_xy",
        "group": "post",
        "x": 194,
        "y": 39,
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-favorites": {
        "label": "Post: Wait + tap Favorites — after tapping music",
        "kind": "tap_ocr",
        "group": "post",
        "texts": ["Favorites", "FAVORITES"],
        "wait_timeout_seconds": 60,
        "hint": "Open the music picker and wait for Favorites to appear.",
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-hvitserk": {
        "label": "Post: Wait + tap text \"Hvitserk's choice\" (OCR) — after Favorites",
        "kind": "tap_ocr",
        "group": "post",
        "texts": [
            "Hvitserk's choice",
            "Hvitserk's Choice",
            "Hvitserks choice",
            "Hvitserks Choice",
            "HVITSERK'S CHOICE",
        ],
        "wait_timeout_seconds": 60,
        "threshold": 0.65,
        "hint": "Wait for the track row, then tap the Hvitserk's choice text.",
        "offline_hint": OFFLINE_HINT,
    },
    "post-dismiss-music": {
        "label": "Post: Dismiss music (187, 334) — after Hvitserk's choice",
        "kind": "tap_xy",
        "group": "post",
        "x": 187,
        "y": 334,
        "offline_hint": OFFLINE_HINT,
    },
    "post-type-caption": {
        "label": "Post: Type dashboard caption — after tapping aa",
        "kind": "type_caption",
        "group": "post",
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-done": {
        "label": "Post: Tap Done — after tapping border",
        "kind": "tap_ocr",
        "group": "post",
        "texts": ["Done", "DONE"],
        "prefer_top": True,
        "hint": "Show the text editor with Done in the top-right.",
        "offline_hint": OFFLINE_HINT,
    },
    "post-swipe-left": {
        "label": "Post: Swipe left (341,533)→(40,533) — after tapping editor",
        "kind": "swipe",
        "group": "post",
        "direction": "left",
        "sx": 341,
        "sy": 533,
        "ex": 40,
        "ey": 533,
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-text-scrub": {
        "label": "Post: Tap text scrub (161, 561) — after swiping left",
        "kind": "tap_xy",
        "group": "post",
        "x": 161,
        "y": 561,
        "offline_hint": OFFLINE_HINT,
    },
    "post-drag-trim": {
        "label": "Post: Drag trim (214,508) left fast, release after 1s — after text scrub",
        "kind": "drag",
        "group": "post",
        "x1": 214,
        "y1": 508,
        "direction": "left",
        "distance": 172,
        "duration_ms": 1000,
        "move_ms": 10,
        "hold_ms": 0,
        "offline_hint": OFFLINE_HINT,
    },
}


def _iter_ui_elements(data: dict[str, Any]) -> list[dict[str, Any]]:
    ui = data.get("ui_elements", {})
    if isinstance(ui, list):
        return ui
    if isinstance(ui, dict):
        items: list[dict[str, Any]] = []
        for value in ui.values():
            if isinstance(value, list):
                items.extend(value)
            elif isinstance(value, dict):
                items.append(value)
        return items
    return []


def _template_debug_tests(workflows_dir: str = "config/workflows") -> dict[str, DebugTest]:
    path = Path(workflows_dir) / "screen_states.yaml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    tests: dict[str, DebugTest] = {}
    for element in _iter_ui_elements(data):
        name = str(element.get("name", "")).strip()
        if not name:
            continue
        template = str(element.get("template", f"{name}.jpg"))
        is_post = name in _POST_TEMPLATE_NAMES
        label = _POST_TEMPLATE_LABELS.get(name, f"Tap {name.replace('_', ' ')}")
        tests[f"tap-{name}"] = {
            "label": label,
            "detection": name,
            "group": "post" if is_post else "prep",
            "hint": f"Show the target on screen. Template: config/templates/{template}",
            "offline_hint": OFFLINE_HINT,
        }
    return tests


def get_debug_registry(workflows_dir: str = "config/workflows") -> dict[str, DebugTest]:
    registry = _template_debug_tests(workflows_dir)
    registry.update(MANUAL_DEBUG_TESTS)
    registry.update(TIKTOK_POST_DEBUG_TESTS)
    return registry


# Backward-compatible alias used by tests.
DEBUG_TESTS = get_debug_registry()

_DEBUG_LIST_PRIORITY = (
    "upload-gallery",
    "clear-album",
    "list-album",
    "open-photos-spotlight",
    "tap-ocr-allow",
    "tap-ocr-delete",
)


def list_debug_tests(group: str | None = None) -> list[dict[str, str]]:
    registry = get_debug_registry()
    if group == "post":
        priority = _POST_DEBUG_LIST_PRIORITY
        ordered = [i for i in priority if i in registry]
        ordered.extend(
            i for i in registry if registry[i].get("group") == "post" and i not in ordered
        )
    else:
        priority = _DEBUG_LIST_PRIORITY
        ordered = [i for i in priority if i in registry]
        ordered.extend(i for i in registry if i not in ordered)
    items = [
        {
            "id": test_id,
            "label": registry[test_id]["label"],
            "group": registry[test_id].get("group", "prep"),
        }
        for test_id in ordered
    ]
    if group == "prep":
        items = [item for item in items if item["group"] == "prep"]
    elif group == "post":
        items = [item for item in items if item["group"] == "post"]
    return items


async def run_debug_test(app: Any, device_id: str, test_id: str) -> dict[str, Any]:
    spec = get_debug_registry().get(test_id)
    if not spec:
        raise HTTPException(404, f"Unknown debug test: {test_id}")
    kind = spec.get("kind", "tap")
    if kind == "upload_gallery":
        return await upload_gallery_debug(app, device_id, test_id, spec)
    if kind == "album_clear":
        return await clear_album_debug(app, device_id, test_id, spec)
    if kind == "album_list":
        return await list_album_debug(app, device_id, test_id, spec)
    if kind == "tap_ocr":
        return await tap_ocr_debug(app, device_id, test_id, spec)
    if kind == "open_photos_spotlight":
        return await open_photos_spotlight_debug(app, device_id, test_id, spec)
    if kind == "tap_xy":
        return await tap_xy_debug(app, device_id, test_id, spec)
    if kind == "swipe":
        return await swipe_debug(app, device_id, test_id, spec)
    if kind == "drag":
        return await drag_debug(app, device_id, test_id, spec)
    if kind == "type_caption":
        return await type_caption_debug(app, device_id, test_id, spec)
    return await tap_detection(
        app,
        device_id,
        spec["detection"],
        hint=spec.get("hint", ""),
        offline_hint=spec.get("offline_hint", OFFLINE_HINT),
        test_id=test_id,
    )


async def open_photos_spotlight_debug(
    app: Any,
    device_id: str,
    test_id: str,
    spec: DebugTest,
) -> dict[str, Any]:
    """Home → swipe down → clear search → type photos → tap result."""
    dm = app.device_manager
    device = dm.get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not device.is_online:
        raise HTTPException(503, spec.get("offline_hint", OFFLINE_HINT))

    engine = app.action_engine
    await engine.execute_direct(device_id, ActionType.HOME, {}, step_name=f"debug_{test_id}_home")
    await asyncio.sleep(2)
    sequence: list[tuple[ActionType, dict[str, Any]]] = [
        (ActionType.SWIPE, dict(SPOTLIGHT_SWIPE)),
        (ActionType.CLEAR_TEXT, {}),
        (ActionType.TEXT_INPUT, {"text": "photos"}),
        (ActionType.TAP_OCR, {"texts": ["Photos", "photos"], "prefer_top": True, "optional": False}),
    ]
    for action_type, params in sequence:
        ok = await engine.execute_direct(
            device_id, action_type, params, step_name=f"debug_{test_id}_{action_type.value}"
        )
        if not ok:
            return {"success": False, "message": f"Failed at {action_type.value}"}
        await asyncio.sleep(2 if action_type == ActionType.SWIPE else 1)
    await app.screenshot_service.capture(device_id)
    await app.db.log_activity(
        "info", "test", "Debug open Photos via Spotlight OK", device_id, {"test_id": test_id}
    )
    return {"success": True, "message": "Opened Photos via Spotlight search"}


async def tap_ocr_debug(
    app: Any,
    device_id: str,
    test_id: str,
    spec: DebugTest,
) -> dict[str, Any]:
    dm = app.device_manager
    device = dm.get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not device.is_online:
        raise HTTPException(503, spec.get("offline_hint", OFFLINE_HINT))

    texts = list(spec.get("texts") or [])
    if not texts:
        raise HTTPException(500, f"Debug test {test_id} has no texts configured")

    wait_timeout = spec.get("wait_timeout_seconds")
    if wait_timeout:
        params: dict[str, Any] = {
            "texts": texts,
            "optional": False,
            "wait_timeout_seconds": float(wait_timeout),
            "poll_interval_seconds": 2,
            "prefer_top": bool(spec.get("prefer_top", False)),
        }
        if "threshold" in spec:
            params["threshold"] = float(spec["threshold"])
        ok = await app.action_engine.execute_direct(
            device_id,
            ActionType.TAP_OCR,
            params,
            step_name=f"debug_{test_id}",
        )
        await app.screenshot_service.capture(device_id)
        message = f"Tapped {texts[0]}" if ok else f"Text not found — {spec.get('hint', '')}"
        await app.db.log_activity(
            "info" if ok else "warn",
            "test",
            f"Debug OCR tap: {message}",
            device_id,
            {"test_id": test_id, "texts": texts},
        )
        return {"success": ok, "message": message, "texts": texts}

    tapped = await tap_permission_prompts(app, device_id, texts, test_id=test_id, rounds=1)
    await app.screenshot_service.capture(device_id)

    if not tapped:
        await app.db.log_activity(
            "warn",
            "test",
            f"Debug OCR tap: none of {texts!r} found on screen",
            device_id,
            {"test_id": test_id, "texts": texts},
        )
        return {
            "success": False,
            "message": f"Text not found — {spec.get('hint', '')}",
            "texts": texts,
        }

    return {
        "success": True,
        "message": f"Tapped {tapped[0]}",
        "text": tapped[0],
        "texts": texts,
    }


async def tap_permission_prompts(
    app: Any,
    device_id: str,
    texts: list[str],
    *,
    test_id: str,
    rounds: int = 2,
    wait_seconds: float = 3,
) -> list[str]:
    """Find and tap permission buttons via iMouse on-device OCR."""
    tapped: list[str] = []
    ctrl = app.device_manager.controller
    for attempt in range(rounds):
        if attempt:
            await asyncio.sleep(wait_seconds)
        for text in texts:
            matches = await ctrl.find_text_on_device(device_id, [text])
            if not matches:
                continue
            best = max(matches, key=lambda m: m.get("confidence", 0))
            await ctrl.tap(device_id, int(best["x"]), int(best["y"]))
            tapped.append(text)
            await app.db.log_activity(
                "info",
                "test",
                f"Debug tap text: {text}",
                device_id,
                {"test_id": test_id, "text": text, "x": best["x"], "y": best["y"]},
            )
            await asyncio.sleep(1)
            break
    return tapped


async def list_album_debug(
    app: Any,
    device_id: str,
    test_id: str,
    spec: DebugTest,
) -> dict[str, Any]:
    """Scan all common iOS album names and report which ones have items."""
    dm = app.device_manager
    device = dm.get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not device.is_online:
        raise HTTPException(503, spec.get("offline_hint", OFFLINE_HINT))

    ctrl = dm.controller
    # "" = Recents (iMouse default); also probe common iOS album names
    candidates = ["", "All Photos", "Camera Roll", "Recents", "Videos", "Favorites", "Selfies"]
    results: dict[str, int] = {}
    for name in candidates:
        items = await ctrl.album_list(device_id, album_name=name or None)
        label = name if name else "Recents (default)"
        results[label] = len(items)

    summary = {k: v for k, v in results.items() if v > 0}
    message = (
        "Non-empty albums: " + ", ".join(f"{k}={v}" for k, v in summary.items())
        if summary
        else "All checked albums are empty"
    )

    await app.db.log_activity(
        "info", "test", f"Album scan: {message}", device_id,
        {"test_id": test_id, "album_counts": results},
    )

    return {
        "success": True,
        "message": message,
        "album_counts": results,
        "non_empty": summary,
    }


async def clear_album_debug(
    app: Any,
    device_id: str,
    test_id: str,
    spec: DebugTest,
) -> dict[str, Any]:
    """Clear photo library via shortcut_album_clear + tapping the iOS Delete popup."""
    dm = app.device_manager
    device = dm.get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not device.is_online:
        raise HTTPException(503, spec.get("offline_hint", OFFLINE_HINT))

    success = await app.action_engine.execute_direct(
        device_id,
        ActionType.ALBUM_CLEAR,
        {"timeout_ms": 120000},
        step_name=f"debug_{test_id}",
    )

    if success:
        await app.screenshot_service.capture(device_id)

    await app.db.log_activity(
        "info" if success else "warn",
        "test",
        f"Debug clear album {'OK' if success else 'failed'}",
        device_id,
        {"test_id": test_id},
    )

    return {
        "success": success,
        "message": "Cleared photo library" if success else "Album clear failed",
    }


async def upload_gallery_debug(
    app: Any,
    device_id: str,
    test_id: str,
    spec: DebugTest,
) -> dict[str, Any]:
    """Upload all media from gallery/<slot>/ to the device — no other steps."""
    dm = app.device_manager
    device = dm.get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not device.is_online:
        raise HTTPException(503, spec.get("offline_hint", "Device offline — click Connect AirPlay first"))

    gallery = app.config.gallery
    folder = phone_gallery_folder(
        gallery.base_directory,
        device.user_name,
        device.phone_name,
    )
    files = list_media_files(folder, gallery.media_extensions)
    if not files:
        message = f"No media files in {folder} — add videos/images for slot {device.user_name}"
        await app.db.log_activity(
            "warn",
            "test",
            f"Debug upload: {message}",
            device_id,
            {"test_id": test_id, "folder": str(folder)},
        )
        return {
            "success": False,
            "message": message,
            "folder": str(folder),
            "file_count": 0,
        }

    success = await app.action_engine.execute_direct(
        device_id,
        ActionType.ALBUM_UPLOAD,
        {
            "folder": str(folder),
            "extensions": gallery.media_extensions,
            "timeout_ms": gallery.upload_timeout_ms,
        },
        step_name=f"debug_{test_id}",
    )

    await app.db.log_activity(
        "info" if success else "warn",
        "test",
        f"Debug upload gallery {'OK' if success else 'failed'} — {len(files)} file(s) from {folder}",
        device_id,
        {"test_id": test_id, "folder": str(folder), "file_count": len(files)},
    )

    tapped_permissions: list[str] = []
    if success:
        await asyncio.sleep(10)
        tapped_permissions = await tap_permission_prompts(
            app, device_id, UPLOAD_PERMISSION_TEXTS, test_id=test_id
        )
        await app.screenshot_service.capture(device_id)

    message = f"Uploaded {len(files)} file(s) from {folder}" if success else "Gallery upload failed"
    if tapped_permissions:
        message += f" — tapped {', '.join(tapped_permissions)}"

    return {
        "success": success,
        "message": message,
        "folder": str(folder),
        "file_count": len(files),
        "files": [Path(f).name for f in files],
        "tapped_permissions": tapped_permissions,
    }


async def _require_online_device(app: Any, device_id: str, spec: DebugTest) -> Any:
    device = app.device_manager.get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not device.is_online:
        raise HTTPException(503, spec.get("offline_hint", OFFLINE_HINT))
    return device


async def tap_xy_debug(app: Any, device_id: str, test_id: str, spec: DebugTest) -> dict[str, Any]:
    await _require_online_device(app, device_id, spec)
    x, y = int(spec["x"]), int(spec["y"])
    ok = await app.action_engine.execute_direct(
        device_id, ActionType.TAP, {"x": x, "y": y}, step_name=f"debug_{test_id}"
    )
    await app.screenshot_service.capture(device_id)
    return {"success": ok, "message": f"Tapped ({x}, {y})", "x": x, "y": y}


async def swipe_debug(app: Any, device_id: str, test_id: str, spec: DebugTest) -> dict[str, Any]:
    await _require_online_device(app, device_id, spec)
    params = {
        "direction": spec.get("direction", "left"),
        "sx": spec.get("sx"),
        "sy": spec.get("sy"),
        "ex": spec.get("ex"),
        "ey": spec.get("ey"),
    }
    ok = await app.action_engine.execute_direct(
        device_id, ActionType.SWIPE, params, step_name=f"debug_{test_id}"
    )
    await app.screenshot_service.capture(device_id)
    return {"success": ok, "message": f"Swipe {params['direction']}"}


async def drag_debug(app: Any, device_id: str, test_id: str, spec: DebugTest) -> dict[str, Any]:
    await _require_online_device(app, device_id, spec)
    params: dict[str, Any] = {
        "x1": int(spec["x1"]),
        "y1": int(spec["y1"]),
        "duration_ms": int(spec.get("duration_ms", 1000)),
        "move_ms": int(spec.get("move_ms", 10)),
        "hold_ms": int(spec.get("hold_ms", 0)),
    }
    if "x2" in spec and "y2" in spec:
        params["x2"] = int(spec["x2"])
        params["y2"] = int(spec["y2"])
    if spec.get("direction"):
        params["direction"] = str(spec["direction"])
    if "distance" in spec:
        params["distance"] = int(spec["distance"])
    ok = await app.action_engine.execute_direct(
        device_id, ActionType.DRAG, params, step_name=f"debug_{test_id}"
    )
    await app.screenshot_service.capture(device_id)
    return {"success": ok, "message": "Drag complete", **params}


async def type_caption_debug(app: Any, device_id: str, test_id: str, spec: DebugTest) -> dict[str, Any]:
    await _require_online_device(app, device_id, spec)
    text = get_post_caption()
    ok = await app.action_engine.execute_direct(
        device_id, ActionType.TEXT_INPUT, {"text": text}, step_name=f"debug_{test_id}"
    )
    await app.screenshot_service.capture(device_id)
    return {"success": ok, "message": f"Typed caption ({len(text)} chars)", "text": text}


async def tap_detection(
    app: Any,
    device_id: str,
    detection: str,
    *,
    hint: str,
    offline_hint: str = OFFLINE_HINT,
    test_id: str | None = None,
) -> dict[str, Any]:
    """Screenshot → find template → tap. Used by debug tests and workflows."""
    dm = app.device_manager
    device = dm.get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not device.is_online:
        raise HTTPException(503, offline_hint)

    shot = await app.screenshot_service.capture(device_id)
    if not shot:
        raise HTTPException(500, "Screenshot failed")

    vision = app.vision
    analysis = vision.analyze(
        device_id,
        shot["file_path"],
        template_names=[detection],
    )
    detections: dict[str, dict[str, Any]] = {
        d.name: {"x": d.x, "y": d.y, "confidence": d.confidence}
        for d in analysis.detections
    }

    if hasattr(vision, "template_path_for"):
        path = vision.template_path_for(detection)
        if path:
            threshold = vision.threshold_for(detection)
            sw = int(device.screen_width) if device.screen_width else 406
            sh = int(device.screen_height) if device.screen_height else 720
            rect = (
                vision.search_rect_for(detection, width=sw, height=sh)
                if hasattr(vision, "search_rect_for")
                else None
            )
            hit = await dm.controller.find_template_on_device(
                device_id, path, threshold, rect=rect
            )
            if hit:
                existing = detections.get(detection)
                if not existing or hit["confidence"] >= existing.get("confidence", 0):
                    detections[detection] = hit

    if detection not in detections:
        await app.db.log_activity(
            "warn",
            "test",
            f"Debug tap: {detection} not found on screen",
            device_id,
            {"test_id": test_id, "template": detection, "screenshot": shot.get("file_path")},
        )
        return {
            "success": False,
            "message": f"{detection} not found — {hint}",
            "detection": detection,
            "detections": list(detections.keys()),
        }

    hit = detections[detection]
    app.action_engine.set_detections(device_id, detections)
    success = await app.action_engine.execute_direct(
        device_id,
        ActionType.TAP_DETECTION,
        {"detection": detection},
        step_name=f"debug_{test_id or detection}",
    )

    await app.screenshot_service.capture(device_id)

    await app.db.log_activity(
        "info" if success else "warn",
        "test",
        f"Debug tap {detection} {'OK' if success else 'failed'} at ({hit['x']}, {hit['y']})",
        device_id,
        {"test_id": test_id, "confidence": hit.get("confidence"), "x": hit["x"], "y": hit["y"]},
    )

    return {
        "success": success,
        "message": f"Tapped {detection}" if success else "Tap failed",
        "detection": detection,
        "x": int(hit["x"]),
        "y": int(hit["y"]),
        "confidence": float(hit.get("confidence", 0)),
    }


async def tap_vpntoggle(app: Any, device_id: str) -> dict[str, Any]:
    """Backward-compatible alias for the VPN toggle debug test."""
    return await run_debug_test(app, device_id, "tap-vpntoggle")
