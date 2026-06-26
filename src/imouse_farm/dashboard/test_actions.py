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
import time
from pathlib import Path
from typing import Any, Literal, TypedDict

import yaml
from fastapi import HTTPException

from imouse_farm.actions.permission_prompts import UPLOAD_PERMISSION_TEXTS
from imouse_farm.config.models import ActionType
from imouse_farm.vision.fallbacks import (
    apply_detection_fallbacks,
    apply_exclusive_detections,
    apply_tap_offsets,
    expand_template_names,
)

from imouse_farm.post.post_caption_store import (
    device_storage_key,
    get_final_caption,
    get_onscreen_text,
)
from imouse_farm.utils.gallery import list_media_files, phone_gallery_folder
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

_VPN_DETECT_LABELS: dict[str, str] = {
    "detect-vpn-on": "VPN connected (no Not Connected in Shadowrocket)",
    "detect-vpn-off": "VPN not connected (Not Connected in Shadowrocket)",
}

DebugKind = Literal[
    "tap",
    "detect",
    "detect_ocr",
    "upload_gallery",
    "album_clear",
    "album_list",
    "tap_ocr",
    "open_photos_spotlight",
    "tap_xy",
    "swipe",
    "drag",
    "type_caption",
    "type_final_caption",
    "final_caption_production",
    "media_then_next",
    "gallery_then_recents",
    "hvitserk_after_favorites",
    "close_app",
    "kill_app",
]

_POST_TEMPLATE_NAMES = frozenset({"plus", "aa", "continuearrow"})

_POST_TEMPLATE_LABELS: dict[str, str] = {
    "plus": "Post: Tap plus (+ button)",
    "aa": "Post: Tap aa (add text) — after dismissing music",
    "continuearrow": "Post: Tap continue arrow — after drag trim",
}

_POST_DEBUG_LIST_PRIORITY = (
    "tap-plus",
    "post-tap-gallery-recents",
    "post-wait-recents",
    "post-tap-gallery-item",
    "post-tap-gallery-item-2",
    "post-tap-gallery-item-3",
    "post-tap-next-after-media",
    "post-tap-music",
    "post-tap-favorites",
    "post-tap-hvitserk",
    "post-dismiss-music",
    "tap-aa",
    "post-type-caption",
    "post-tap-border2-coord",
    "post-tap-done",
    "tap-editor",
    "post-swipe-left",
    "post-tap-text-scrub",
    "post-drag-trim",
    "tap-continuearrow",
    "post-tap-final-caption-field",
    "post-type-final-caption",
    "post-final-caption-prod-1",
    "post-final-caption-prod-2",
    "post-final-caption-prod-3",
    "tap-post",
)

_END_DEBUG_LIST_PRIORITY = (
    "end-kill-apps",
    "end-tap-shadowrocket",
    "end-tap-bluetoggle",
)

OFFLINE_HINT = "Device offline — click Connect AirPlay first"

HVITSERK_CHOICE_TEXTS = [
    "Hvitserk's choice",
    "Hvitserk's Choice",
    "Hvitserks choice",
    "Hvitserks Choice",
    "HVITSERK'S CHOICE",
]

UNSTABLE_NETWORK_TEXTS = [
    "Your network is unstable. Tap to retry.",
    "Your network is unstable",
    "network is unstable",
    "Tap to retry",
]

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
    initial_wait_seconds: float
    retry_wait_seconds: float
    poll_interval_seconds: float
    unstable_texts: list[str]
    threshold: float
    prefer_top: bool
    hint: str
    offline_hint: str
    open_shadowrocket: bool
    expect_missing: bool


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
    "detect-vpn-on": {
        "label": "Detect VPN connected (Shadowrocket — no Not Connected)",
        "kind": "detect_ocr",
        "group": "prep",
        "texts": ["Not Connected", "NOT CONNECTED"],
        "open_shadowrocket": True,
        "expect_missing": True,
        "hint": "Opens Shadowrocket; VPN is on when Not Connected is absent.",
        "offline_hint": OFFLINE_HINT,
    },
    "detect-vpn-off": {
        "label": "Detect VPN not connected (Shadowrocket — Not Connected)",
        "kind": "detect_ocr",
        "group": "prep",
        "texts": ["Not Connected", "NOT CONNECTED"],
        "open_shadowrocket": True,
        "hint": "Opens Shadowrocket; VPN is off when Not Connected is visible.",
        "offline_hint": OFFLINE_HINT,
    },
}

TIKTOK_POST_DEBUG_TESTS: dict[str, DebugTest] = {
    "post-tap-gallery-recents": {
        "label": "Post: Tap gallery (33,669)×2 + Recents (fallback 326,609)×2",
        "kind": "gallery_then_recents",
        "group": "post",
        "x": 33,
        "y": 669,
        "tap_count": 2,
        "tap_interval_seconds": 0.5,
        "texts": ["Recents", "RECENTS", "Recent", "RECENT"],
        "wait_timeout_seconds": 10,
        "poll_interval_seconds": 1.5,
        "verify_only": True,
        "prefer_top": True,
        "threshold": 0.55,
        "contain": True,
        "ocr_ex": True,
        "search_rect_pct": [0.0, 0.0, 1.0, 0.32],
        "fallback_tap": {"x": 326, "y": 609, "tap_count": 2, "tap_interval_seconds": 0.5},
        "fallback_tap_delay_seconds": 1,
        "fallback_after_tap_seconds": 1.5,
        "fallback_retry_seconds": 10,
        "hint": "Run after plus: gallery 2× then OCR Recents; fallback gallery 2× at (326,609) if picker did not open.",
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-gallery-item": {
        "label": "Post 1: Tap gallery item (321, 194) — rightmost / post 1 file",
        "kind": "tap_xy",
        "group": "post",
        "x": 321,
        "y": 194,
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-gallery-item-2": {
        "label": "Post 2: Tap gallery item (191, 190) — middle",
        "kind": "tap_xy",
        "group": "post",
        "x": 191,
        "y": 190,
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-gallery-item-3": {
        "label": "Post 3: Tap gallery item (82, 201) — leftmost / post 3 file",
        "kind": "tap_xy",
        "group": "post",
        "x": 82,
        "y": 201,
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-next-after-media": {
        "label": "Post: Tap gallery item (321, 194) then black Next (OCR, optional)",
        "kind": "media_then_next",
        "group": "post",
        "x": 321,
        "y": 194,
        "texts": ["Next", "NEXT"],
        "after_tap_seconds": 2,
        "require_dark_text": True,
        "max_text_luminance": 110,
        "wait_timeout_seconds": 30,
        "poll_interval_seconds": 1,
        "threshold": 0.65,
        "skip_if_texts_present": ["Your Story", "YOUR STORY", "Your story", "Story"],
        "skip_if_all_texts_present": ["Your", "Story"],
        "skip_if_story_button": True,
        "skip_if_threshold": 0.45,
        "skip_if_ocr_ex": True,
        "hint": "Open TikTok post editor with gallery visible; skips Next when Your Story is on screen.",
        "offline_hint": OFFLINE_HINT,
    },
    "post-wait-recents": {
        "label": "Post: Wait for Recents (OCR) — after gallery picker opens",
        "kind": "tap_ocr",
        "group": "post",
        "texts": ["Recents", "RECENTS", "Recent", "RECENT"],
        "wait_timeout_seconds": 10,
        "poll_interval_seconds": 1.5,
        "verify_only": True,
        "prefer_top": True,
        "threshold": 0.55,
        "contain": True,
        "ocr_ex": True,
        "search_rect_pct": [0.0, 0.0, 1.0, 0.32],
        "fallback_tap": {"x": 326, "y": 609, "tap_count": 2, "tap_interval_seconds": 0.5},
        "fallback_tap_delay_seconds": 1,
        "fallback_after_tap_seconds": 1.5,
        "fallback_retry_seconds": 10,
        "hint": "Gallery picker already open — waits for Recents; fallback gallery 2× at (326,609) if needed.",
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
        "label": "Post: Wait for Hvitserk — 30s, unstable retry, +20s (after Favorites)",
        "kind": "hvitserk_after_favorites",
        "group": "post",
        "texts": list(HVITSERK_CHOICE_TEXTS),
        "unstable_texts": list(UNSTABLE_NETWORK_TEXTS),
        "initial_wait_seconds": 30,
        "retry_wait_seconds": 20,
        "poll_interval_seconds": 1.5,
        "threshold": 0.65,
        "hint": "Run after Favorites: wait up to 30s for Hvitserk; tap unstable-network retry if needed; wait up to 20s more.",
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
        "label": "Post 1: Type onscreen text — after tapping aa",
        "kind": "type_caption",
        "group": "post",
        "post_num": 1,
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-border2-coord": {
        "label": "Post 1: Tap white background (201, 38) ×2 — after typing caption (post 1 only)",
        "kind": "tap_xy",
        "group": "post",
        "x": 201,
        "y": 38,
        "tap_count": 2,
        "tap_interval_seconds": 0.5,
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-done": {
        "label": "Post: Tap Done — after tapping white background",
        "kind": "tap_ocr",
        "group": "post",
        "texts": ["Done", "DONE"],
        "prefer_top": True,
        "hint": "Show the text editor with Done in the top-right.",
        "offline_hint": OFFLINE_HINT,
    },
    "tap-editor": {
        "label": "Post: Tap editor (374, 163) — after Done",
        "kind": "tap_xy",
        "group": "post",
        "x": 374,
        "y": 163,
        "hint": "Show the post editor screen after tapping Done.",
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
    "post-tap-final-caption-field": {
        "label": "Post: Tap caption field (107, 130) — after continue arrow",
        "kind": "tap_xy",
        "group": "post",
        "x": 107,
        "y": 130,
        "offline_hint": OFFLINE_HINT,
    },
    "post-type-final-caption": {
        "label": "Post 1: Type final caption + hashtags — after tapping caption field",
        "kind": "type_final_caption",
        "group": "post",
        "post_num": 1,
        "offline_hint": OFFLINE_HINT,
    },
    "post-final-caption-prod-1": {
        "label": "Post 1: Production final caption flow (field → type → wait)",
        "kind": "final_caption_production",
        "group": "post",
        "post_num": 1,
        "hint": "TikTok post screen with caption field visible (after continue arrow). Uses dashboard Post 1 final text + hashtags, single-line like Full start.",
        "offline_hint": OFFLINE_HINT,
    },
    "post-final-caption-prod-2": {
        "label": "Post 2: Production final caption flow (field → type → wait)",
        "kind": "final_caption_production",
        "group": "post",
        "post_num": 2,
        "hint": "Same as production tiktok_post step 17–18 for Post 2 final caption from dashboard.",
        "offline_hint": OFFLINE_HINT,
    },
    "post-final-caption-prod-3": {
        "label": "Post 3: Production final caption flow (field → type → wait)",
        "kind": "final_caption_production",
        "group": "post",
        "post_num": 3,
        "hint": "Same as production tiktok_post step 17–18 for Post 3 final caption from dashboard.",
        "offline_hint": OFFLINE_HINT,
    },
    "tap-post": {
        "label": "Post: Tap post (352, 45) — after typing final caption",
        "kind": "tap_xy",
        "group": "post",
        "x": 352,
        "y": 45,
        "hint": "Caption field filled; keyboard may still be visible.",
        "offline_hint": OFFLINE_HINT,
    },
}

TIKTOK_END_DEBUG_TESTS: dict[str, DebugTest] = {
    "end-kill-apps": {
        "label": "End: Force-quit apps (App btn, swipe up ×5)",
        "kind": "kill_app",
        "group": "end",
        "offline_hint": OFFLINE_HINT,
    },
    "end-tap-shadowrocket": {
        "label": "End: Tap Shadowrocket icon — on home screen",
        "kind": "tap",
        "group": "end",
        "detection": "shadowrocket",
        "offline_hint": OFFLINE_HINT,
    },
    "end-tap-bluetoggle": {
        "label": "End: Tap blue VPN toggle — inside Shadowrocket (VPN on)",
        "kind": "tap",
        "group": "end",
        "detection": "bluetoggle",
        "hint": "Open Shadowrocket first; blue toggle shows when VPN is connected.",
        "offline_hint": OFFLINE_HINT,
    },
}


def _detect_activity_label(test_id: str | None, detection: str) -> str:
    if test_id and test_id in _VPN_DETECT_LABELS:
        return _VPN_DETECT_LABELS[test_id]
    return f"Detect ({detection})"


async def _log_detect_result(
    app: Any,
    *,
    device_id: str,
    test_id: str | None,
    detection: str,
    found: bool,
    hit: dict[str, Any] | None = None,
    screenshot: str | None = None,
    other_detections: list[str] | None = None,
) -> None:
    """Write activity + server log for detect-only debug tests."""
    label = _detect_activity_label(test_id, detection)
    details: dict[str, Any] = {
        "test_id": test_id,
        "template": detection,
        "screenshot": screenshot,
        "found": found,
    }
    if other_detections is not None:
        details["other_detections"] = other_detections
    if hit:
        details.update(
            confidence=float(hit.get("confidence", 0)),
            x=int(hit["x"]),
            y=int(hit["y"]),
            matched_via=hit.get("matched_via"),
        )

    if found and hit:
        via = hit.get("matched_via")
        via_note = f" via {via}" if via else ""
        conf = float(hit.get("confidence", 0))
        message = (
            f"{label}: SUCCESS at ({hit['x']}, {hit['y']}) "
            f"confidence {conf:.2f}{via_note}"
        )
        await app.db.log_activity("info", "test", message, device_id, details)
        logger.info(
            "debug_detect_success",
            device_id=device_id,
            test_id=test_id,
            detection=detection,
            x=int(hit["x"]),
            y=int(hit["y"]),
            confidence=conf,
        )
    else:
        other = other_detections or []
        other_note = f" (saw: {', '.join(other)})" if other else ""
        message = f"{label}: NOT FOUND{other_note}"
        await app.db.log_activity("warn", "test", message, device_id, details)
        logger.warning(
            "debug_detect_not_found",
            device_id=device_id,
            test_id=test_id,
            detection=detection,
            other_detections=other,
        )


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
    registry.update(TIKTOK_END_DEBUG_TESTS)
    return registry


# Backward-compatible alias used by tests.
DEBUG_TESTS = get_debug_registry()

_DEBUG_LIST_PRIORITY = (
    "upload-gallery",
    "clear-album",
    "list-album",
    "detect-vpn-on",
    "detect-vpn-off",
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
    elif group == "end":
        priority = _END_DEBUG_LIST_PRIORITY
        ordered = [i for i in priority if i in registry]
        ordered.extend(
            i for i in registry if registry[i].get("group") == "end" and i not in ordered
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
    elif group == "end":
        items = [item for item in items if item["group"] == "end"]
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
    if kind == "type_final_caption":
        return await type_final_caption_debug(app, device_id, test_id, spec)
    if kind == "final_caption_production":
        return await final_caption_production_debug(app, device_id, test_id, spec)
    if kind == "media_then_next":
        return await media_then_next_debug(app, device_id, test_id, spec)
    if kind == "gallery_then_recents":
        return await gallery_then_recents_debug(app, device_id, test_id, spec)
    if kind == "hvitserk_after_favorites":
        return await hvitserk_after_favorites_debug(app, device_id, test_id, spec)
    if kind == "close_app":
        return await close_app_debug(app, device_id, test_id, spec)
    if kind == "kill_app":
        return await kill_app_debug(app, device_id, test_id, spec)
    if kind == "detect_ocr":
        return await detect_ocr_debug(app, device_id, test_id, spec)
    if kind == "detect":
        if spec.get("open_shadowrocket"):
            open_result = await tap_detection(
                app,
                device_id,
                "shadowrocket",
                hint="Shadowrocket icon must be visible on the home screen.",
                offline_hint=spec.get("offline_hint", OFFLINE_HINT),
                test_id=f"{test_id}_open_shadowrocket",
            )
            if not open_result.get("success"):
                return {
                    "success": False,
                    "message": f"Could not open Shadowrocket — {open_result.get('message', '')}",
                    "detection": spec["detection"],
                }
            await asyncio.sleep(2)
        return await tap_detection(
            app,
            device_id,
            spec["detection"],
            hint=spec.get("hint", ""),
            offline_hint=spec.get("offline_hint", OFFLINE_HINT),
            test_id=test_id,
            tap=False,
        )
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


async def detect_ocr_debug(
    app: Any,
    device_id: str,
    test_id: str,
    spec: DebugTest,
) -> dict[str, Any]:
    """Open Shadowrocket (optional) and verify on-device OCR text."""
    dm = app.device_manager
    device = dm.get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not device.is_online:
        raise HTTPException(503, spec.get("offline_hint", OFFLINE_HINT))

    texts = list(spec.get("texts") or [])
    if not texts:
        raise HTTPException(500, f"Debug test {test_id} has no texts configured")

    if spec.get("open_shadowrocket"):
        open_result = await tap_detection(
            app,
            device_id,
            "shadowrocket",
            hint="Shadowrocket icon must be visible on the home screen.",
            offline_hint=spec.get("offline_hint", OFFLINE_HINT),
            test_id=f"{test_id}_open_shadowrocket",
        )
        if not open_result.get("success"):
            return {
                "success": False,
                "message": f"Could not open Shadowrocket — {open_result.get('message', '')}",
            }
        await asyncio.sleep(2)

    expect_missing = bool(spec.get("expect_missing"))
    try:
        ok = await app.action_engine.execute_direct(
            device_id,
            ActionType.TAP_OCR,
            {
                "texts": texts,
                "verify_only": True,
                "optional": False,
                "expect_missing": expect_missing,
            },
            step_name=f"debug_{test_id}",
        )
    except Exception as exc:
        label = _VPN_DETECT_LABELS.get(test_id, "Detect OCR")
        message = f"{label}: FAILED — {exc}"
        await app.db.log_activity("warn", "test", message, device_id, {"test_id": test_id})
        return {"success": False, "message": message}

    label = _VPN_DETECT_LABELS.get(test_id, "Detect OCR")
    message = f"{label}: SUCCESS" if ok else f"{label}: FAILED"
    level = "info" if ok else "warn"
    await app.db.log_activity(level, "test", message, device_id, {"test_id": test_id, "texts": texts})
    return {"success": ok, "message": message}


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
    has_unstable_flow = bool(
        spec.get("unstable_retry_texts") or spec.get("initial_wait_seconds")
    )
    if wait_timeout or has_unstable_flow:
        params: dict[str, Any] = {
            "texts": texts,
            "optional": False,
            "poll_interval_seconds": float(spec.get("poll_interval_seconds", 2)),
            "prefer_top": bool(spec.get("prefer_top", False)),
        }
        if wait_timeout:
            params["wait_timeout_seconds"] = float(wait_timeout)
        for key in (
            "threshold",
            "contain",
            "verify_only",
            "ocr_ex",
            "search_rect_pct",
            "expect_missing",
            "fallback_tap",
            "fallback_tap_delay_seconds",
            "fallback_after_tap_seconds",
            "fallback_retry_seconds",
            "initial_wait_seconds",
            "after_retry_wait_seconds",
            "unstable_retry_texts",
            "unstable_texts",
        ):
            if key in spec:
                if key == "unstable_texts":
                    params["unstable_retry_texts"] = spec[key]
                else:
                    params[key] = spec[key]
        if spec.get("retry_wait_seconds") is not None and "after_retry_wait_seconds" not in params:
            params["after_retry_wait_seconds"] = spec["retry_wait_seconds"]
        if has_unstable_flow and "wait_timeout_seconds" not in spec:
            params.pop("wait_timeout_seconds", None)
        ok = await app.action_engine.execute_direct(
            device_id,
            ActionType.TAP_OCR,
            params,
            step_name=f"debug_{test_id}",
        )
        await app.screenshot_service.capture(device_id)
        if spec.get("verify_only"):
            message = (
                f"Found {texts[0]}"
                if ok
                else f"Text not found — {spec.get('hint', '')}"
            )
        else:
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


async def _best_ocr_match(
    ctrl: Any,
    device_id: str,
    texts: list[str],
    *,
    threshold: float,
    contain: bool = True,
) -> dict[str, Any] | None:
    """Return the best on-device OCR match for any of ``texts``, or None."""
    batch = await ctrl.find_text_on_device(
        device_id, texts, threshold=threshold, contain=contain
    )
    if batch:
        return max(batch, key=lambda m: float(m.get("confidence", 0)))
    for text in texts:
        matches = await ctrl.find_text_on_device(
            device_id, [text], threshold=threshold, contain=contain
        )
        if matches:
            return max(matches, key=lambda m: float(m.get("confidence", 0)))
    return None


async def _poll_for_text(
    ctrl: Any,
    device_id: str,
    texts: list[str],
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
    threshold: float,
    contain: bool = True,
) -> dict[str, Any] | None:
    """Poll until ``texts`` appear or ``timeout_seconds`` elapses."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        match = await _best_ocr_match(
            ctrl, device_id, texts, threshold=threshold, contain=contain
        )
        if match:
            return match
        if time.monotonic() >= deadline:
            return None
        await asyncio.sleep(poll_interval_seconds)


async def _tap_ocr_match(ctrl: Any, device_id: str, match: dict[str, Any]) -> bool:
    return await ctrl.tap(device_id, int(match["x"]), int(match["y"]))


async def hvitserk_after_favorites_debug(
    app: Any,
    device_id: str,
    test_id: str,
    spec: DebugTest,
) -> dict[str, Any]:
    """Wait for Hvitserk after Favorites; tap unstable-network retry if needed."""
    await _require_online_device(app, device_id, spec)
    ctrl = app.device_manager.controller

    hvitserk_texts = list(spec.get("texts") or HVITSERK_CHOICE_TEXTS)
    unstable_texts = list(spec.get("unstable_texts") or UNSTABLE_NETWORK_TEXTS)
    initial_wait = float(spec.get("initial_wait_seconds", 30))
    retry_wait = float(spec.get("retry_wait_seconds", 20))
    poll_interval = float(spec.get("poll_interval_seconds", 1.5))
    threshold = float(spec.get("threshold", 0.65))

    steps: list[str] = []

    hvitserk = await _poll_for_text(
        ctrl,
        device_id,
        hvitserk_texts,
        timeout_seconds=initial_wait,
        poll_interval_seconds=poll_interval,
        threshold=threshold,
    )
    if hvitserk:
        tapped = await _tap_ocr_match(ctrl, device_id, hvitserk)
        await app.screenshot_service.capture(device_id)
        message = (
            f"Found Hvitserk within {initial_wait:.0f}s and tapped"
            if tapped
            else f"Found Hvitserk within {initial_wait:.0f}s but tap failed"
        )
        await app.db.log_activity(
            "info" if tapped else "warn",
            "test",
            f"Debug Hvitserk after Favorites: {message}",
            device_id,
            {"test_id": test_id, "phase": "initial", "text": hvitserk.get("text")},
        )
        return {"success": tapped, "message": message, "phase": "initial"}

    steps.append(f"no Hvitserk after {initial_wait:.0f}s")

    unstable = await _best_ocr_match(
        ctrl, device_id, unstable_texts, threshold=threshold, contain=True
    )
    if unstable:
        tapped_unstable = await _tap_ocr_match(ctrl, device_id, unstable)
        steps.append(
            f"tapped unstable-network retry ({unstable.get('text', '')!r})"
            if tapped_unstable
            else "found unstable-network prompt but tap failed"
        )
        await asyncio.sleep(1.5)
    else:
        steps.append("unstable-network prompt not found")

    hvitserk = await _poll_for_text(
        ctrl,
        device_id,
        hvitserk_texts,
        timeout_seconds=retry_wait,
        poll_interval_seconds=poll_interval,
        threshold=threshold,
    )

    if hvitserk:
        tapped = await _tap_ocr_match(ctrl, device_id, hvitserk)
        await app.screenshot_service.capture(device_id)
        message = (
            f"{' → '.join(steps)}; found Hvitserk within +{retry_wait:.0f}s and tapped"
            if tapped
            else f"{' → '.join(steps)}; found Hvitserk but tap failed"
        )
        await app.db.log_activity(
            "info" if tapped else "warn",
            "test",
            f"Debug Hvitserk after Favorites: {message}",
            device_id,
            {"test_id": test_id, "phase": "retry", "text": hvitserk.get("text")},
        )
        return {"success": tapped, "message": message, "phase": "retry", "steps": steps}

    await app.screenshot_service.capture(device_id)
    message = f"{' → '.join(steps)}; Hvitserk not found after +{retry_wait:.0f}s"
    await app.db.log_activity(
        "warn",
        "test",
        f"Debug Hvitserk after Favorites: {message}",
        device_id,
        {"test_id": test_id, "phase": "failed", "steps": steps},
    )
    return {
        "success": False,
        "message": message,
        "phase": "failed",
        "steps": steps,
        "hint": spec.get("hint", ""),
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
    params: dict[str, Any] = {"x": x, "y": y}
    if "tap_count" in spec:
        params["tap_count"] = int(spec["tap_count"])
    if "tap_interval_seconds" in spec:
        params["tap_interval_seconds"] = float(spec["tap_interval_seconds"])
    ok = await app.action_engine.execute_direct(
        device_id, ActionType.TAP, params, step_name=f"debug_{test_id}"
    )
    await app.screenshot_service.capture(device_id)
    count = int(params.get("tap_count", 1))
    msg = f"Tapped ({x}, {y}) ×{count}" if count > 1 else f"Tapped ({x}, {y})"
    return {"success": ok, "message": msg, "x": x, "y": y}


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
    device = await _require_online_device(app, device_id, spec)
    post_num = int(spec.get("post_num", 1))
    text_key = device_storage_key(device.device_id, device.user_name)
    text = get_onscreen_text(text_key, post_num)
    ok = await app.action_engine.execute_direct(
        device_id, ActionType.TEXT_INPUT, {"text": text}, step_name=f"debug_{test_id}"
    )
    await app.screenshot_service.capture(device_id)
    return {"success": ok, "message": f"Typed onscreen text ({len(text)} chars)", "text": text}


async def type_final_caption_debug(app: Any, device_id: str, test_id: str, spec: DebugTest) -> dict[str, Any]:
    device = await _require_online_device(app, device_id, spec)
    post_num = int(spec.get("post_num", 1))
    text_key = device_storage_key(device.device_id, device.user_name)
    text = get_final_caption(text_key, post_num)
    ok = await app.action_engine.execute_direct(
        device_id,
        ActionType.TEXT_INPUT,
        {"text": text, "single_line": True},
        step_name=f"debug_{test_id}",
    )
    await app.screenshot_service.capture(device_id)
    return {"success": ok, "message": f"Typed final caption ({len(text)} chars)", "text": text}


# Mirrors tiktok_post: tap caption field → 2s → single-line type → 3s (no Post tap).
_CAPTION_FIELD_X = 107
_CAPTION_FIELD_Y = 130
_CAPTION_FIELD_SETTLE_SECONDS = 2.0
_AFTER_CAPTION_TYPE_SECONDS = 3.0


async def gallery_then_recents_debug(
    app: Any, device_id: str, test_id: str, spec: DebugTest
) -> dict[str, Any]:
    """Tap gallery 2× then wait for Recents OCR with fallback (matches tiktok_post steps 2–3)."""
    await _require_online_device(app, device_id, spec)
    x, y = int(spec["x"]), int(spec["y"])
    step = f"debug_{test_id}"
    engine = app.action_engine

    tap_params: dict[str, Any] = {"x": x, "y": y}
    if "tap_count" in spec:
        tap_params["tap_count"] = int(spec["tap_count"])
    if "tap_interval_seconds" in spec:
        tap_params["tap_interval_seconds"] = float(spec["tap_interval_seconds"])

    tapped = await engine.execute_direct(
        device_id,
        ActionType.TAP,
        tap_params,
        step_name=f"{step}_gallery",
    )
    if not tapped:
        return {"success": False, "message": f"Failed to tap gallery at ({x}, {y})"}

    texts = list(spec.get("texts") or ["Recents", "RECENTS", "Recent", "RECENT"])
    ocr_params: dict[str, Any] = {
        "texts": texts,
        "optional": False,
        "wait_timeout_seconds": float(spec.get("wait_timeout_seconds", 10)),
        "poll_interval_seconds": float(spec.get("poll_interval_seconds", 1.5)),
        "verify_only": bool(spec.get("verify_only", True)),
        "prefer_top": bool(spec.get("prefer_top", True)),
        "threshold": float(spec.get("threshold", 0.55)),
        "contain": bool(spec.get("contain", True)),
        "ocr_ex": bool(spec.get("ocr_ex", True)),
    }
    for key in (
        "search_rect_pct",
        "fallback_tap",
        "fallback_tap_delay_seconds",
        "fallback_after_tap_seconds",
        "fallback_retry_seconds",
    ):
        if key in spec:
            ocr_params[key] = spec[key]

    ok = await engine.execute_direct(
        device_id,
        ActionType.TAP_OCR,
        ocr_params,
        step_name=f"{step}_recents",
    )
    await app.screenshot_service.capture(device_id)

    count = int(tap_params.get("tap_count", 1))
    tap_msg = f"({x}, {y}) ×{count}" if count > 1 else f"({x}, {y})"
    fallback = spec.get("fallback_tap") or {}
    fb_x, fb_y = fallback.get("x"), fallback.get("y")
    fb_count = int(fallback.get("tap_count", 1))
    if ok:
        message = f"Tapped gallery {tap_msg}; Recents visible"
    elif fb_x is not None and fb_y is not None:
        fb_msg = f"({fb_x}, {fb_y}) ×{fb_count}" if fb_count > 1 else f"({fb_x}, {fb_y})"
        message = (
            f"Tapped gallery {tap_msg}; Recents not found — "
            f"fallback {fb_msg} did not open picker"
        )
    else:
        message = f"Tapped gallery {tap_msg}; Recents not found"

    await app.db.log_activity(
        "info" if ok else "warn",
        "test",
        message,
        device_id,
        {"test_id": test_id, "texts": texts},
    )
    return {"success": ok, "message": message, "x": x, "y": y, "texts": texts}


async def media_then_next_debug(
    app: Any, device_id: str, test_id: str, spec: DebugTest
) -> dict[str, Any]:
    """Tap gallery media coord, then optionally tap Next via OCR (matches tiktok_post step)."""
    await _require_online_device(app, device_id, spec)
    x, y = int(spec["x"]), int(spec["y"])
    step = f"debug_{test_id}"
    engine = app.action_engine
    ctrl = app.device_manager.controller

    tapped_media = await engine.execute_direct(
        device_id,
        ActionType.TAP,
        {"x": x, "y": y},
        step_name=f"{step}_media",
    )
    if not tapped_media:
        return {"success": False, "message": f"Failed to tap media at ({x}, {y})"}

    await asyncio.sleep(float(spec.get("after_tap_seconds", 2)))

    texts = list(spec.get("texts") or ["Next", "NEXT"])
    threshold = float(spec.get("threshold", 0.65))
    ocr_params: dict[str, Any] = {
        "texts": texts,
        "optional": True,
        "wait_timeout_seconds": float(spec.get("wait_timeout_seconds", 30)),
        "poll_interval_seconds": float(spec.get("poll_interval_seconds", 1)),
        "threshold": threshold,
        "contain": True,
    }
    if spec.get("require_dark_text"):
        ocr_params["require_dark_text"] = True
        ocr_params["max_text_luminance"] = float(spec.get("max_text_luminance", 110))
    for key in (
        "skip_if_texts_present",
        "skip_if_all_texts_present",
        "skip_if_story_button",
        "skip_if_threshold",
        "skip_if_ocr_ex",
    ):
        if key in spec:
            ocr_params[key] = spec[key]

    from imouse_farm.vision.ocr_skip import should_skip_tap_ocr

    device = app.device_manager.get_device(device_id)
    sw = int(device.screen_width) if device and device.screen_width else 406
    sh = int(device.screen_height) if device and device.screen_height else 720

    async def _story_on_screen() -> bool:
        return await should_skip_tap_ocr(
            ctrl,
            device_id,
            ocr_params,
            default_threshold=threshold,
            default_contain=True,
            skip_rect=None,
            screen_width=sw,
            screen_height=sh,
        )

    async def _find_next() -> list[dict[str, Any]]:
        return await ctrl.find_text_on_device(
            device_id, texts, threshold=threshold, contain=True
        )

    before = await _find_next()
    await engine.execute_direct(
        device_id,
        ActionType.TAP_OCR,
        ocr_params,
        step_name=f"{step}_next",
    )
    await app.screenshot_service.capture(device_id)
    after = await _find_next()

    if await _story_on_screen():
        message = (
            f"Tapped media ({x}, {y}); Your Story on screen — skipped Next (go to music)"
        )
    elif before and not after:
        message = f"Tapped media ({x}, {y}), then tapped Next"
    elif before and after:
        message = f"Tapped media ({x}, {y}); Next found but still on screen"
        await app.db.log_activity(
            "warn", "test", message, device_id, {"test_id": test_id, "texts": texts}
        )
        return {"success": False, "message": message, "x": x, "y": y, "texts": texts}
    else:
        message = f"Tapped media ({x}, {y}); Next not on screen — skipped"

    await app.db.log_activity("info", "test", message, device_id, {"test_id": test_id})
    return {"success": True, "message": message, "x": x, "y": y, "texts": texts}


async def final_caption_production_debug(
    app: Any, device_id: str, test_id: str, spec: DebugTest
) -> dict[str, Any]:
    """Simulate production final caption + hashtags typing (steps 17–18 in tiktok_post)."""
    from imouse_farm.utils.text_input import flatten_line_breaks

    device = await _require_online_device(app, device_id, spec)
    post_num = int(spec.get("post_num", 1))
    text_key = device_storage_key(device.device_id, device.user_name)
    text = get_final_caption(text_key, post_num)
    if not text.strip():
        raise HTTPException(
            400,
            f"Post {post_num} final caption is empty — fill it in the dashboard Post {post_num} box first.",
        )

    engine = app.action_engine
    step = f"debug_{test_id}"

    tapped = await engine.execute_direct(
        device_id,
        ActionType.TAP,
        {"x": _CAPTION_FIELD_X, "y": _CAPTION_FIELD_Y},
        step_name=f"{step}_tap_field",
    )
    if not tapped:
        return {
            "success": False,
            "message": f"Failed to tap caption field ({_CAPTION_FIELD_X}, {_CAPTION_FIELD_Y})",
        }

    await asyncio.sleep(_CAPTION_FIELD_SETTLE_SECONDS)

    typed = await engine.execute_direct(
        device_id,
        ActionType.TEXT_INPUT,
        {"text": text, "single_line": True},
        step_name=f"{step}_type",
    )
    if not typed:
        return {"success": False, "message": "Caption field tapped but text_input failed"}

    await asyncio.sleep(_AFTER_CAPTION_TYPE_SECONDS)
    await app.screenshot_service.capture(device_id)

    flat = flatten_line_breaks(text)
    await app.db.log_activity(
        "info",
        "test",
        f"Production caption flow post {post_num}: {len(flat)} chars typed",
        device_id,
        {"test_id": test_id, "post_num": post_num, "char_count": len(flat)},
    )
    return {
        "success": True,
        "message": (
            f"Post {post_num} production flow OK — tapped (107,130), typed {len(flat)} chars "
            f"(caption + hashtags, single line), waited {_AFTER_CAPTION_TYPE_SECONDS:.0f}s. "
            f"Use Tap post (352, 45) to finish."
        ),
        "post_num": post_num,
        "char_count": len(flat),
        "text_preview": flat[:120] + ("…" if len(flat) > 120 else ""),
    }


async def kill_app_debug(app: Any, device_id: str, test_id: str, spec: DebugTest) -> dict[str, Any]:
    await _require_online_device(app, device_id, spec)
    ok = await app.action_engine.execute_direct(
        device_id, ActionType.KILL_APP, {}, step_name=f"debug_{test_id}"
    )
    await app.screenshot_service.capture(device_id)
    return {"success": ok, "message": "Force-quit: App button + 5 swipe ups"}


async def close_app_debug(app: Any, device_id: str, test_id: str, spec: DebugTest) -> dict[str, Any]:
    await _require_online_device(app, device_id, spec)
    ok = await app.action_engine.execute_direct(
        device_id, ActionType.CLOSE_APP, {}, step_name=f"debug_{test_id}"
    )
    await app.screenshot_service.capture(device_id)
    return {"success": ok, "message": "Closed app (pressed home)"}


async def tap_detection(
    app: Any,
    device_id: str,
    detection: str,
    *,
    hint: str,
    offline_hint: str = OFFLINE_HINT,
    test_id: str | None = None,
    tap: bool = True,
) -> dict[str, Any]:
    """Screenshot → find template → tap (or detect-only when ``tap=False``)."""
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
    template_names = expand_template_names([detection])
    analysis = vision.analyze(
        device_id,
        shot["file_path"],
        template_names=template_names,
    )
    detections: dict[str, dict[str, Any]] = {
        d.name: {"x": d.x, "y": d.y, "confidence": d.confidence}
        for d in analysis.detections
    }

    if hasattr(vision, "template_path_for"):
        sw = int(device.screen_width) if device.screen_width else 406
        sh = int(device.screen_height) if device.screen_height else 720
        for tmpl_name in template_names:
            path = vision.template_path_for(tmpl_name)
            if not path:
                continue
            threshold = vision.threshold_for(tmpl_name)
            if hasattr(vision, "device_threshold_for"):
                threshold = vision.device_threshold_for(tmpl_name)
            rect = (
                vision.search_rect_for(tmpl_name, width=sw, height=sh)
                if hasattr(vision, "search_rect_for")
                else None
            )
            hit = await dm.controller.find_template_on_device(
                device_id, path, threshold, rect=rect
            )
            if not hit:
                continue
            existing = detections.get(tmpl_name)
            if not existing or hit["confidence"] >= existing.get("confidence", 0):
                detections[tmpl_name] = hit

    detections = apply_detection_fallbacks(detections)
    detections = apply_exclusive_detections(detections)
    if hasattr(vision, "min_confidence_for"):
        for name in list(detections):
            min_conf = vision.min_confidence_for(name)
            if min_conf is not None and float(detections[name].get("confidence", 0)) < min_conf:
                del detections[name]
    if hasattr(vision, "tap_offset_for"):
        detections = apply_tap_offsets(detections, vision.tap_offset_for)

    if detection not in detections:
        if not tap:
            await _log_detect_result(
                app,
                device_id=device_id,
                test_id=test_id,
                detection=detection,
                found=False,
                screenshot=shot.get("file_path"),
                other_detections=list(detections.keys()),
            )
            label = _detect_activity_label(test_id, detection)
            return {
                "success": False,
                "message": f"{label}: NOT FOUND — {hint}",
                "detection": detection,
                "detections": list(detections.keys()),
            }
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
    via = hit.get("matched_via")
    via_note = f" via {via}" if via else ""
    if not tap:
        conf = float(hit.get("confidence", 0))
        await _log_detect_result(
            app,
            device_id=device_id,
            test_id=test_id,
            detection=detection,
            found=True,
            hit=hit,
            screenshot=shot.get("file_path"),
        )
        label = _detect_activity_label(test_id, detection)
        return {
            "success": True,
            "message": (
                f"{label}: SUCCESS at ({hit['x']}, {hit['y']}) "
                f"confidence {conf:.2f}{via_note}"
            ),
            "detection": detection,
            "x": int(hit["x"]),
            "y": int(hit["y"]),
            "confidence": conf,
            "detections": list(detections.keys()),
        }

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
        f"Debug tap {detection}{via_note} {'OK' if success else 'failed'} at ({hit['x']}, {hit['y']})",
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
