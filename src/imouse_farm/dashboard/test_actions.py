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
import hashlib
import time
from pathlib import Path
from typing import Any, Literal, TypedDict

import yaml
from fastapi import HTTPException

from imouse_farm.actions.permission_prompts import (
    UPLOAD_PERMISSION_TEXTS,
    analyze_popup_screen,
    known_popup_watcher_button_labels,
    tiktok_security_checkup_dismiss_coords,
    tiktok_add_phone_dismiss_coords,
)
from imouse_farm.config.models import ActionType
from imouse_farm.vision.fallbacks import (
    apply_detection_fallbacks,
    apply_exclusive_detections,
    apply_tap_offsets,
    expand_template_names,
)
from imouse_farm.vision.template_scan import (
    ocr_rect_from_pct,
    pick_detection_hit,
    stronger_hit,
)

from imouse_farm.post.post_caption_store import (
    device_storage_key,
    get_final_caption,
    get_onscreen_text,
)
from imouse_farm.utils.gallery import list_media_files, phone_gallery_folder, slots_with_media
from imouse_farm.utils.logging import get_logger
from imouse_farm.actions.vpn_shadowrocket import (
    TIKTOK_HOME_ICON_X,
    TIKTOK_HOME_ICON_Y,
)
from imouse_farm.dashboard.flow_debug import (
    FLOW_DEBUG_STEPS,
    FLOW_DEBUG_WARMUP_STEPS,
    flow_step_letter,
    resolve_flow_debug_test_id,
)

# Re-export for tests.
FULL_FLOW_DEBUG_STEPS = FLOW_DEBUG_STEPS

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
    "tiktok_popup_scan",
    "permission_watcher_run",
    "close_app",
    "kill_app",
    "home",
    "vpn_shortcut",
    "vpn_off_before_album",
    "account_switch_step",
    "slideshow_generate",
    "vision_navigate",
]

_POST_TEMPLATE_NAMES = frozenset({"plus", "aa", "continuearrow"})

_POST_TEMPLATE_LABELS: dict[str, str] = {
    "plus": "Post: Tap plus (+ button) ×2",
    "aa": "Post: Tap aa (add text) — polls every 2s after dismissing music",
    "continuearrow": "Post: Tap continue arrow — after drag trim",
}

_POST_DEBUG_LIST_PRIORITY = (
    "tap-plus",
    "detect-tiktok-popups",
    "dismiss-tiktok-popup",
    "run-permission-watcher",
    "post-dismiss-security-checkup",
    "post-dismiss-add-phone",
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
    "prep-vpn-shortcut-off",
)

_ACCOUNT_SWITCH_DEBUG_LIST_PRIORITY = (
    # Step-by-step switch (A→Z from step 1)
    "account-tap-profile-tab",
    "account-switcher-tap-primary",
    "account-switcher-tap-alt",
    "account-switcher-verify-handle",
    "account-pick-handle",
    "account-tap-home-tab",
    # Optional recovery after switch
    "account-swipe-continue-editing",
    "account-scan-popups",
    "account-dismiss-popup",
    "account-run-permission-watcher",
    "account-dismiss-security-checkup",
    "account-dismiss-add-phone",
    # Production shortcuts (run alone — not part of step chain)
    "account-open-switcher",
    "account-ensure-current",
    "account-ensure-full",
)

OFFLINE_HINT = "Device offline — click Connect AirPlay first"

_SECURITY_CHECKUP_DISMISS_X, _SECURITY_CHECKUP_DISMISS_Y = tiktok_security_checkup_dismiss_coords()
_ADD_PHONE_DISMISS_X, _ADD_PHONE_DISMISS_Y = tiktok_add_phone_dismiss_coords()

HVITSERK_CHOICE_TEXTS = [
    "Hvitserk's choice",
    "Hvitserk's Choice",
    "Hvitserks choice",
    "Hvitserks Choice",
    "HVITSERK'S CHOICE",
    "Hvitserk",
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
    group: str  # prep | post | end | account_switch | slideshow
    brand: str  # labely | valcoin — for slideshow_generate
    step: str
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
    apply_watcher: bool
    skip_vpn_off: bool


# Manual tests override auto-generated template entries with the same id.
MANUAL_DEBUG_TESTS: dict[str, DebugTest] = {
    "upload-gallery": {
        "label": "Upload gallery files",
        "kind": "upload_gallery",
        "group": "prep",
        "offline_hint": OFFLINE_HINT,
    },
    "clear-album": {
        "label": "Clear photo library (VPN off first)",
        "kind": "album_clear",
        "group": "prep",
        "offline_hint": OFFLINE_HINT,
    },
    "prep-kill-apps": {
        "label": "Prep: Force-quit apps (App btn, swipe up ×5)",
        "kind": "kill_app",
        "group": "prep",
        "offline_hint": OFFLINE_HINT,
    },
    "prep-swipe-unlock": {
        "label": "Prep: Swipe unlock (200,500)→(200,200)",
        "kind": "swipe",
        "group": "prep",
        "x1": 200,
        "y1": 500,
        "x2": 200,
        "y2": 200,
        "duration_ms": 300,
        "offline_hint": OFFLINE_HINT,
    },
    "prep-home": {
        "label": "Prep: Press home",
        "kind": "home",
        "group": "prep",
        "offline_hint": OFFLINE_HINT,
    },
    "tap-tiktok": {
        "label": f"Prep: Tap TikTok icon ({TIKTOK_HOME_ICON_X}, {TIKTOK_HOME_ICON_Y})",
        "kind": "tap_xy",
        "group": "prep",
        "x": TIKTOK_HOME_ICON_X,
        "y": TIKTOK_HOME_ICON_Y,
        "wait_for_tiktok_ready": True,
        "tiktok_ready_timeout_seconds": 120.0,
        "hint": "Home screen — opens TikTok and waits for the + button (home feed ready).",
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
        "hint": "Opens Shadowrocket via URL shortcut; VPN is on when Not Connected is absent.",
        "offline_hint": OFFLINE_HINT,
    },
    "detect-vpn-off": {
        "label": "Detect VPN not connected (Shadowrocket — Not Connected)",
        "kind": "detect_ocr",
        "group": "prep",
        "texts": ["Not Connected", "NOT CONNECTED"],
        "open_shadowrocket": True,
        "hint": "Opens Shadowrocket via URL shortcut; VPN is off when Not Connected is visible.",
        "offline_hint": OFFLINE_HINT,
    },
    "prep-vpn-shortcut-on": {
        "label": "Prep: VPN ON via URL shortcut (browser)",
        "kind": "vpn_shortcut",
        "group": "prep",
        "mode": "on",
        "hint": (
            "Opens vpn.shortcut_url_on via iMouse shortcut_exec_url. "
            "Default: shadowrocket://connect — edit config.yaml if you use a custom Shortcuts URL."
        ),
        "offline_hint": OFFLINE_HINT,
    },
    "prep-open-shadowrocket-shortcut": {
        "label": "Prep: Open Shadowrocket via URL shortcut (browser)",
        "kind": "vpn_shortcut",
        "group": "prep",
        "mode": "open",
        "press_home_after": False,
        "hint": (
            "Opens vpn.shortcut_url_open via iMouse shortcut_exec_url. "
            "Default: shadowrocket:// — stays on Shadowrocket (no home press)."
        ),
        "offline_hint": OFFLINE_HINT,
    },
    "prep-vpn-shortcut-off": {
        "label": "Prep: VPN OFF via URL shortcut (browser)",
        "kind": "vpn_shortcut",
        "group": "prep",
        "mode": "off",
        "hint": (
            "Opens vpn.shortcut_url_off via iMouse shortcut_exec_url. "
            "Default: shadowrocket://disconnect. "
            "For the exact clear_album production preamble, use "
            "'VPN OFF before album (production)' instead."
        ),
        "offline_hint": OFFLINE_HINT,
    },
    "prep-vpn-off-before-album": {
        "label": "Prep: VPN OFF before album (production clear_album path)",
        "kind": "vpn_off_before_album",
        "group": "prep",
        "hint": (
            "Exact production path: tiktok_prep clear_album → ensure_vpn_off_before_album → "
            "shortcut_exec_url(vpn.shortcut_url_off). Default shadowrocket://disconnect. "
            "Run after kill-apps + home, before clear gallery. Logs each SDK step."
        ),
        "offline_hint": OFFLINE_HINT,
    },
    "prep-vpn-shortcut-toggle": {
        "label": "Prep: VPN toggle via URL shortcut (browser)",
        "kind": "vpn_shortcut",
        "group": "prep",
        "mode": "toggle",
        "hint": (
            "Opens vpn.shortcut_url_toggle via iMouse shortcut_exec_url. "
            "Default: shadowrocket://toggle."
        ),
        "offline_hint": OFFLINE_HINT,
    },
    "tap-vpntoggle": {
        "label": "VPN toggle via URL shortcut (browser)",
        "kind": "vpn_shortcut",
        "group": "prep",
        "mode": "toggle",
        "hint": "Alias for prep-vpn-shortcut-toggle (backward-compatible API).",
        "offline_hint": OFFLINE_HINT,
    },
}

SLIDESHOW_DEBUG_TESTS: dict[str, DebugTest] = {
    "slideshow-generate-labely": {
        "label": "Generate Labely slideshow (1 video, ingest only)",
        "kind": "slideshow_generate",
        "group": "slideshow",
        "brand": "labely",
        "hint": "Opens autoslideshow for this phone slot; MP4s land in gallery/<slot>/.",
        "offline_hint": "Uses Playwright on this PC — phone does not need AirPlay.",
    },
    "slideshow-generate-valcoin": {
        "label": "Generate ValCoin slideshow (1 video, ingest only)",
        "kind": "slideshow_generate",
        "group": "slideshow",
        "brand": "valcoin",
        "hint": "ValCoin receipt-style slideshow for this slot; ingest only, no batch.",
        "offline_hint": "Uses Playwright on this PC — phone does not need AirPlay.",
    },
    "slideshow-upload-gallery": {
        "label": "Upload gallery files to phone",
        "kind": "upload_gallery",
        "group": "slideshow",
        "offline_hint": OFFLINE_HINT,
    },
}

TIKTOK_POST_DEBUG_TESTS: dict[str, DebugTest] = {
    "detect-tiktok-popups": {
        "label": "Scan TikTok / permission popups (detect only — no tap)",
        "kind": "tiktok_popup_scan",
        "group": "post",
        "hint": "Open TikTok with a popup on screen. Reports what the watcher would do — does not tap.",
        "offline_hint": OFFLINE_HINT,
    },
    "dismiss-tiktok-popup": {
        "label": "Dismiss TikTok / permission popup (watcher apply)",
        "kind": "tiktok_popup_scan",
        "group": "post",
        "apply_watcher": True,
        "hint": "Same as scan, but runs one permission-watcher cycle and taps if a known popup is found.",
        "offline_hint": OFFLINE_HINT,
    },
    "run-permission-watcher": {
        "label": "Run permission watcher (full cycle — detect + tap)",
        "kind": "permission_watcher_run",
        "group": "post",
        "hint": "Runs the live watcher once: all popup handlers, security checkup OCR, find-contacts loop — taps/swipes if anything matches (no pre-scan).",
        "offline_hint": OFFLINE_HINT,
    },
    "post-dismiss-security-checkup": {
        "label": f"Post: Dismiss security checkup X ({_SECURITY_CHECKUP_DISMISS_X}, {_SECURITY_CHECKUP_DISMISS_Y})",
        "kind": "tap_xy",
        "group": "post",
        "x": _SECURITY_CHECKUP_DISMISS_X,
        "y": _SECURITY_CHECKUP_DISMISS_Y,
        "hint": "Show TikTok's 'Let's do a quick security checkup?' sheet first, then run.",
        "offline_hint": OFFLINE_HINT,
    },
    "post-dismiss-add-phone": {
        "label": f"Post: Dismiss Add phone X ({_ADD_PHONE_DISMISS_X}, {_ADD_PHONE_DISMISS_Y})",
        "kind": "tap_xy",
        "group": "post",
        "x": _ADD_PHONE_DISMISS_X,
        "y": _ADD_PHONE_DISMISS_Y,
        "hint": "Show TikTok's 'Add phone' sheet first, then run.",
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-gallery-only": {
        "label": "Post: Tap gallery (58,1035) ×2",
        "kind": "tap_xy",
        "group": "post",
        "x": 58,
        "y": 1035,
        "tap_count": 2,
        "tap_interval_seconds": 0.5,
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-next-only": {
        "label": "Post: Tap Next (OCR, optional)",
        "kind": "tap_ocr",
        "group": "post",
        "texts": ["Next", "NEXT"],
        "optional": True,
        "require_dark_text": True,
        "max_text_luminance": 110,
        "wait_timeout_seconds": 30,
        "poll_interval_seconds": 1,
        "threshold": 0.65,
        "contain": True,
        "hint": "After selecting gallery video; skips if Your Story is visible.",
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-gallery-recents": {
        "label": "Post: Tap gallery (58,1035)×2 + Recents (fallback 527,940)×2",
        "kind": "gallery_then_recents",
        "group": "post",
        "x": 58,
        "y": 1035,
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
        "fallback_tap": {"x": 527, "y": 940, "tap_count": 2, "tap_interval_seconds": 0.5},
        "fallback_tap_delay_seconds": 1,
        "fallback_after_tap_seconds": 1.5,
        "fallback_retry_seconds": 10,
        "hint": "Run after plus: gallery 2× then OCR Recents; fallback gallery 2× at (527,940) if picker did not open.",
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-gallery-item": {
        "label": "Post 1: Tap gallery item (513, 267) — rightmost / post 1 file",
        "kind": "tap_xy",
        "group": "post",
        "x": 513,
        "y": 267,
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-gallery-item-2": {
        "label": "Post 2: Tap gallery item (305, 291) — middle",
        "kind": "tap_xy",
        "group": "post",
        "x": 305,
        "y": 291,
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-gallery-item-3": {
        "label": "Post 3: Tap gallery item (95, 295) — leftmost / post 3 file",
        "kind": "tap_xy",
        "group": "post",
        "x": 95,
        "y": 295,
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-next-after-media": {
        "label": "Post: Tap gallery item (513, 267) then black Next (OCR, optional)",
        "kind": "media_then_next",
        "group": "post",
        "x": 513,
        "y": 267,
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
        "fallback_tap": {"x": 527, "y": 940, "tap_count": 2, "tap_interval_seconds": 0.5},
        "fallback_tap_delay_seconds": 1,
        "fallback_after_tap_seconds": 1.5,
        "fallback_retry_seconds": 10,
        "hint": "Gallery picker already open — waits for Recents; fallback gallery 2× at (527,940) if needed.",
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-music": {
        "label": "Post: Tap music gallery (310, 62) — after 6s load wait",
        "kind": "tap_xy",
        "group": "post",
        "x": 310,
        "y": 62,
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-favorites": {
        "label": "Post: Wait + tap Favorites ×2 — after tapping music",
        "kind": "tap_ocr",
        "group": "post",
        "texts": ["Favorites", "FAVORITES"],
        "wait_timeout_seconds": 60,
        "tap_count": 2,
        "tap_interval_seconds": 0.5,
        "hint": "Open the music picker and wait for Favorites to appear.",
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-hvitserk": {
        "label": "Post: Wait for Hvitserk — poll loading / unstable retry (after Favorites)",
        "kind": "hvitserk_after_favorites",
        "group": "post",
        "texts": list(HVITSERK_CHOICE_TEXTS),
        "unstable_texts": list(UNSTABLE_NETWORK_TEXTS),
        "wait_timeout_seconds": 120,
        "after_retry_wait_seconds": 60,
        "max_wait_timeout_seconds": 300,
        "poll_interval_seconds": 1.5,
        "threshold": 0.6,
        "hint": "After Favorites: poll until Hvitserk appears (tap it) or unstable-network retry (tap retry, keep waiting up to 5 min).",
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
    "tap-aa": {
        "label": "Post: Tap Aa (566, 422) — single tap, after dismissing music",
        "kind": "tap_xy",
        "group": "post",
        "x": 566,
        "y": 422,
        "tap_count": 1,
        "hint": "TikTok editor with text overlay controls visible.",
        "offline_hint": OFFLINE_HINT,
    },
    "post-type-caption": {
        "label": "Post 1: Type onscreen text — after tapping aa",
        "kind": "type_caption",
        "group": "post",
        "post_num": 1,
        "offline_hint": OFFLINE_HINT,
    },
    "post-type-caption-1": {
        "label": "Post 1: Type onscreen text",
        "kind": "type_caption",
        "group": "post",
        "post_num": 1,
        "offline_hint": OFFLINE_HINT,
    },
    "post-type-caption-2": {
        "label": "Post 2: Type onscreen text",
        "kind": "type_caption",
        "group": "post",
        "post_num": 2,
        "offline_hint": OFFLINE_HINT,
    },
    "post-type-caption-3": {
        "label": "Post 3: Type onscreen text",
        "kind": "type_caption",
        "group": "post",
        "post_num": 3,
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-border2-coord": {
        "label": "Post 1: Tap white background (303, 63) ×2 — after typing caption (post 1 only)",
        "kind": "tap_xy",
        "group": "post",
        "x": 303,
        "y": 63,
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
        "wait_timeout_seconds": 60,
        "hint": "Show the text editor with Done in the top-right.",
        "offline_hint": OFFLINE_HINT,
    },
    "tap-editor": {
        "label": "Post: Tap editor (566, 247) — after Done",
        "kind": "tap_xy",
        "group": "post",
        "x": 566,
        "y": 247,
        "hint": "Show the post editor screen after tapping Done.",
        "offline_hint": OFFLINE_HINT,
    },
    "post-swipe-left": {
        "label": "Post: Swipe left (526,922)→(40,922) ×2 — after tapping editor",
        "kind": "swipe",
        "group": "post",
        "direction": "left",
        "sx": 526,
        "sy": 922,
        "ex": 40,
        "ey": 922,
        "swipe_count": 2,
        "swipe_interval_seconds": 1.5,
        "offline_hint": OFFLINE_HINT,
    },
    "post-tap-text-scrub": {
        "label": "Post: Tap text scrub (240, 846) — after swiping left",
        "kind": "tap_xy",
        "group": "post",
        "x": 240,
        "y": 846,
        "offline_hint": OFFLINE_HINT,
    },
    "post-drag-trim": {
        "label": "Post: Drag trim (320,771)→(55,765), 0.9s — after text scrub",
        "kind": "drag",
        "group": "post",
        "x1": 320,
        "y1": 771,
        "x2": 55,
        "y2": 765,
        "duration_ms": 900,
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
    "post-type-final-caption-1": {
        "label": "Post 1: Type final caption + hashtags",
        "kind": "type_final_caption",
        "group": "post",
        "post_num": 1,
        "offline_hint": OFFLINE_HINT,
    },
    "post-type-final-caption-2": {
        "label": "Post 2: Type final caption + hashtags",
        "kind": "type_final_caption",
        "group": "post",
        "post_num": 2,
        "offline_hint": OFFLINE_HINT,
    },
    "post-type-final-caption-3": {
        "label": "Post 3: Type final caption + hashtags",
        "kind": "type_final_caption",
        "group": "post",
        "post_num": 3,
        "offline_hint": OFFLINE_HINT,
    },
    "post-go-home": {
        "label": "Post 3: Press home after publish (wait for upload in production)",
        "kind": "home",
        "group": "post",
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
        "label": "Post: Tap post (544, 68) — after typing final caption",
        "kind": "tap_xy",
        "group": "post",
        "x": 544,
        "y": 68,
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
}

TIKTOK_ACCOUNT_SWITCH_DEBUG_TESTS: dict[str, DebugTest] = {
    "account-ensure-current": {
        "label": "Account: Ensure current brand @ (stay on same account)",
        "kind": "account_switch_step",
        "group": "account_switch",
        "step": "ensure",
        "toggle_to_opposite": False,
        "hint": (
            "Opens profile tab and OCR-scans for the current brand @ only. "
            "If already correct → home. If wrong @ → full switch sequence."
        ),
        "offline_hint": OFFLINE_HINT,
    },
    "account-ensure-full": {
        "label": "Account: Full switch (toggle to other brand @)",
        "kind": "account_switch_step",
        "group": "account_switch",
        "step": "ensure",
        "toggle_to_opposite": True,
        "hint": "Labely dashboard → switches to ValCoin @ (and vice versa). Skips only if already on that @.",
        "offline_hint": OFFLINE_HINT,
    },
    "account-tap-profile-tab": {
        "label": "Account: Tap profile tab",
        "kind": "account_switch_step",
        "group": "account_switch",
        "step": "tap_profile",
        "hint": "TikTok must be open. Opens the profile tab (coords from tiktok_navigation.yaml).",
        "offline_hint": OFFLINE_HINT,
    },
    "account-tap-home-tab": {
        "label": "Account: Tap home tab (60, 1041)",
        "kind": "tap_xy",
        "group": "account_switch",
        "x": 60,
        "y": 1041,
        "hint": "TikTok must be open. Returns to the home feed.",
        "offline_hint": OFFLINE_HINT,
    },
    "account-open-switcher": {
        "label": "Account: Open switcher (production — primary → alt)",
        "kind": "account_switch_step",
        "group": "account_switch",
        "step": "open_switcher",
        "hint": (
            "Taps profile tab, then primary (293,249) and alt (301,288) openers. "
            "Phone 16 uses alternate UI (101,147) only."
        ),
        "offline_hint": OFFLINE_HINT,
    },
    "account-switcher-tap-primary": {
        "label": "Account: Switcher opener — primary tap (293, 249)",
        "kind": "account_switch_step",
        "group": "account_switch",
        "step": "tap_opener_primary",
        "hint": "Profile tab must be open. First opener in production — taps (293, 249); reports if @ list visible.",
        "offline_hint": OFFLINE_HINT,
    },
    "account-switcher-tap-alt": {
        "label": "Account: Switcher opener — alt tap (301, 288)",
        "kind": "account_switch_step",
        "group": "account_switch",
        "step": "tap_opener_alt",
        "hint": "Profile tab must be open. Second opener if primary missed — taps (301, 288); reports if @ list visible.",
        "offline_hint": OFFLINE_HINT,
    },
    "account-switcher-verify-handle": {
        "label": "Account: Switcher — OCR check other brand @ visible",
        "kind": "account_switch_step",
        "group": "account_switch",
        "step": "verify_switcher",
        "hint": "Switcher should be open. OCR scan only — does not tap.",
        "offline_hint": OFFLINE_HINT,
    },
    "account-pick-handle": {
        "label": "Account: Tap other brand @ in dropdown",
        "kind": "account_switch_step",
        "group": "account_switch",
        "step": "pick_handle",
        "hint": "Switcher must be open. On Labely taps ValCoin @ for this phone (and vice versa).",
        "offline_hint": OFFLINE_HINT,
    },
    "account-swipe-continue-editing": {
        "label": "Account: Swipe up dismiss — Continue editing this post? (65, 151)",
        "kind": "swipe",
        "group": "account_switch",
        "direction": "up",
        "sx": 65,
        "sy": 151,
        "ex": 65,
        "ey": 0,
        "hint": "Show the Continue editing this post? sheet first.",
        "offline_hint": OFFLINE_HINT,
    },
    "account-scan-popups": {
        "label": "Account: Scan TikTok popups (detect only)",
        "kind": "tiktok_popup_scan",
        "group": "account_switch",
        "hint": "Reports what the popup watcher would do — does not tap.",
        "offline_hint": OFFLINE_HINT,
    },
    "account-dismiss-popup": {
        "label": "Account: Dismiss TikTok popup (watcher apply)",
        "kind": "tiktok_popup_scan",
        "group": "account_switch",
        "apply_watcher": True,
        "hint": "Runs one watcher cycle; swipes/taps if a known popup is found.",
        "offline_hint": OFFLINE_HINT,
    },
    "account-run-permission-watcher": {
        "label": "Account: Run permission watcher (full cycle)",
        "kind": "permission_watcher_run",
        "group": "account_switch",
        "hint": "Same as Post → Run permission watcher: full popup scan + find-contacts, tap/swipe if matched.",
        "offline_hint": OFFLINE_HINT,
    },
    "account-dismiss-security-checkup": {
        "label": f"Account: Dismiss security checkup X ({_SECURITY_CHECKUP_DISMISS_X}, {_SECURITY_CHECKUP_DISMISS_Y})",
        "kind": "tap_xy",
        "group": "account_switch",
        "x": _SECURITY_CHECKUP_DISMISS_X,
        "y": _SECURITY_CHECKUP_DISMISS_Y,
        "hint": "Show TikTok's 'Let's do a quick security checkup?' sheet first, then run.",
        "offline_hint": OFFLINE_HINT,
    },
    "account-dismiss-add-phone": {
        "label": f"Account: Dismiss Add phone X ({_ADD_PHONE_DISMISS_X}, {_ADD_PHONE_DISMISS_Y})",
        "kind": "tap_xy",
        "group": "account_switch",
        "x": _ADD_PHONE_DISMISS_X,
        "y": _ADD_PHONE_DISMISS_Y,
        "hint": "Show TikTok's 'Add phone' sheet first, then run.",
        "offline_hint": OFFLINE_HINT,
    },
}

_VALCOIN_PREP_DEBUG_LIST_PRIORITY = (
    "valcoin-prep-vpn-shortcut-off",
    "valcoin-prep-clear-album",
    "valcoin-prep-upload-gallery",
    "valcoin-prep-tap-allow",
    "valcoin-prep-vpn-shortcut-on",
    "valcoin-prep-tap-tiktok",
)

TIKTOK_VALCOIN_PREP_DEBUG_TESTS: dict[str, DebugTest] = {
    "valcoin-prep-vpn-shortcut-off": {
        "label": "ValCoin prep: VPN OFF via URL shortcut",
        "kind": "vpn_shortcut",
        "group": "valcoin_prep",
        "mode": "off",
        "hint": "After Labely posts. Opens vpn.shortcut_url_off on the phone.",
        "offline_hint": OFFLINE_HINT,
    },
    "valcoin-prep-clear-album": {
        "label": "ValCoin prep: Clear photo library (VPN off first)",
        "kind": "album_clear",
        "group": "valcoin_prep",
        "hint": "Clears Labely videos before ValCoin upload. Sends VPN disconnect shortcut first.",
        "offline_hint": OFFLINE_HINT,
    },
    "valcoin-prep-upload-gallery": {
        "label": "ValCoin prep: Upload gallery/<slot>/valcoin/",
        "kind": "upload_gallery",
        "group": "valcoin_prep",
        "brand": "valcoin",
        "hint": "After ValCoin clear in same prep. Upload only — VPN off already sent on clear.",
        "offline_hint": OFFLINE_HINT,
    },
    "valcoin-prep-tap-allow": {
        "label": "ValCoin prep: Tap Allow / Always Allow",
        "kind": "tap_ocr",
        "group": "valcoin_prep",
        "texts": list(UPLOAD_PERMISSION_TEXTS),
        "hint": "After ValCoin gallery upload if iOS asks for photo access.",
        "offline_hint": OFFLINE_HINT,
    },
    "valcoin-prep-vpn-shortcut-on": {
        "label": "ValCoin prep: VPN ON via URL shortcut",
        "kind": "vpn_shortcut",
        "group": "valcoin_prep",
        "mode": "on",
        "hint": "After ValCoin upload. Opens vpn.shortcut_url_on before TikTok.",
        "offline_hint": OFFLINE_HINT,
    },
    "valcoin-prep-tap-tiktok": {
        "label": f"ValCoin prep: Tap TikTok icon ({TIKTOK_HOME_ICON_X}, {TIKTOK_HOME_ICON_Y})",
        "kind": "tap_xy",
        "group": "valcoin_prep",
        "x": TIKTOK_HOME_ICON_X,
        "y": TIKTOK_HOME_ICON_Y,
        "wait_for_tiktok_ready": True,
        "tiktok_ready_timeout_seconds": 120.0,
        "hint": "Home screen — opens TikTok and waits for the + button (home feed ready).",
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
        if name == "plus":
            tests[f"tap-{name}"]["tap_count"] = 2
            tests[f"tap-{name}"]["tap_interval_seconds"] = 0.5
            tests[f"tap-{name}"]["poll_interval_seconds"] = 2
            tests[f"tap-{name}"]["wait_timeout_seconds"] = 30
            tests[f"tap-{name}"]["post_tap_delay_seconds"] = 3
        elif name == "aa":
            tests[f"tap-{name}"]["poll_interval_seconds"] = 2
            tests[f"tap-{name}"]["wait_timeout_seconds"] = 60
            tests[f"tap-{name}"]["samples_per_poll"] = 4
            tests[f"tap-{name}"]["sample_interval_seconds"] = 0.45
            tests[f"tap-{name}"]["ocr_fallback_texts"] = ["Aa", "AA"]
            tests[f"tap-{name}"]["ocr_threshold"] = 0.48
            tests[f"tap-{name}"]["ocr_ex"] = True
            tests[f"tap-{name}"]["prefer_top"] = True
            tests[f"tap-{name}"]["ocr_search_rect_pct"] = [0.78, 0.0, 1.0, 0.28]
            tests[f"tap-{name}"]["hint"] = (
                "After dismissing music — 4 captures every 2s; template + OCR for Aa."
            )
    return tests


WARMUP_DEBUG_TESTS: dict[str, DebugTest] = {
    "warmup-run": {
        "label": "Warmup: Run 2min ValCoin feed scroll (debug)",
        "kind": "warmup_run",
        "group": "warmup",
        "brand": "valcoin",
        "duration_seconds": 120,
        "skip_setup": True,
        "hint": "TikTok must already be open on ValCoin account. Scrolls feed for 60s.",
        "offline_hint": OFFLINE_HINT,
    },
}


VISION_DEBUG_TESTS: dict[str, DebugTest] = {
    "vision-navigate": {
        "label": "Vision: Tap to create a new note (Notes app test)",
        "kind": "vision_navigate",
        "group": "manual",
        "prompt": "Tap the button that creates a new note",
        "hint": "Takes a screenshot, asks GPT for the tap coordinate, then taps it.",
        "offline_hint": OFFLINE_HINT,
    },
}


def get_debug_registry(workflows_dir: str = "config/workflows") -> dict[str, DebugTest]:
    registry = _template_debug_tests(workflows_dir)
    registry.update(MANUAL_DEBUG_TESTS)
    registry.update(TIKTOK_POST_DEBUG_TESTS)
    registry.update(TIKTOK_END_DEBUG_TESTS)
    registry.update(TIKTOK_ACCOUNT_SWITCH_DEBUG_TESTS)
    registry.update(TIKTOK_VALCOIN_PREP_DEBUG_TESTS)
    registry.update(SLIDESHOW_DEBUG_TESTS)
    registry.update(WARMUP_DEBUG_TESTS)
    registry.update(VISION_DEBUG_TESTS)
    return registry


# Backward-compatible alias used by tests.
DEBUG_TESTS = get_debug_registry()

_DEBUG_LIST_PRIORITY = (
    "upload-gallery",
    "run-permission-watcher",
    "prep-kill-apps",
    "clear-album",
    "list-album",
    "prep-open-shadowrocket-shortcut",
    "prep-vpn-shortcut-on",
    "prep-vpn-off-before-album",
    "prep-vpn-shortcut-off",
    "prep-vpn-shortcut-toggle",
    "detect-vpn-on",
    "detect-vpn-off",
    "open-photos-spotlight",
    "tap-ocr-allow",
    "tap-ocr-delete",
)

_SLIDESHOW_DEBUG_LIST_PRIORITY = (
    "slideshow-generate-labely",
    "slideshow-generate-valcoin",
    "slideshow-upload-gallery",
)


def list_debug_tests(group: str | None = None) -> list[dict[str, str]]:
    registry = get_debug_registry()
    key = (group or "flow").strip().lower()
    if key in ("flow", "full_flow"):
        items: list[dict[str, str]] = []
        for idx, (short, test_id) in enumerate(FLOW_DEBUG_STEPS):
            spec = registry.get(test_id)
            if not spec:
                continue
            flow_id = f"flow:{idx + 1:03d}:{test_id}"
            items.append(
                {
                    "id": flow_id,
                    "test_id": test_id,
                    "label": f"{flow_step_letter(idx)}. {short}",
                    "group": "flow",
                    "step": str(idx + 1),
                }
            )
        return items
    if key == "warmup_flow":
        items = []
        for idx, (short, test_id) in enumerate(FLOW_DEBUG_WARMUP_STEPS):
            spec = registry.get(test_id)
            if not spec:
                continue
            flow_id = f"warmup:{idx + 1:03d}:{test_id}"
            items.append(
                {
                    "id": flow_id,
                    "test_id": test_id,
                    "label": f"{flow_step_letter(idx)}. {short}",
                    "group": "warmup_flow",
                    "step": str(idx + 1),
                }
            )
        return items
    if key == "all":
        priority = _DEBUG_LIST_PRIORITY
        ordered = [i for i in priority if i in registry]
        ordered.extend(i for i in registry if i not in ordered)
        return [
            {
                "id": test_id,
                "label": registry[test_id]["label"],
                "group": registry[test_id].get("group", "prep"),
            }
            for test_id in ordered
        ]
    ordered: list[str] = []
    if key == "post":
        priority = _POST_DEBUG_LIST_PRIORITY
        ordered = [i for i in priority if i in registry]
        ordered.extend(
            i for i in registry if registry[i].get("group") == "post" and i not in ordered
        )
    elif key == "end":
        priority = _END_DEBUG_LIST_PRIORITY
        ordered = [i for i in priority if i in registry]
        ordered.extend(
            i for i in registry if registry[i].get("group") == "end" and i not in ordered
        )
    elif key == "account_switch":
        priority = _ACCOUNT_SWITCH_DEBUG_LIST_PRIORITY
        ordered = [i for i in priority if i in registry]
        ordered.extend(
            i
            for i in registry
            if registry[i].get("group") == "account_switch" and i not in ordered
        )
    elif key == "slideshow":
        priority = _SLIDESHOW_DEBUG_LIST_PRIORITY
        ordered = [i for i in priority if i in registry]
        ordered.extend(
            i
            for i in registry
            if registry[i].get("group") == "slideshow" and i not in ordered
        )
    elif key == "valcoin_prep":
        priority = _VALCOIN_PREP_DEBUG_LIST_PRIORITY
        ordered = [i for i in priority if i in registry]
        ordered.extend(
            i
            for i in registry
            if registry[i].get("group") == "valcoin_prep" and i not in ordered
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
    if key == "prep":
        items = [item for item in items if item["group"] == "prep"]
    elif key == "post":
        items = [item for item in items if item["group"] == "post"]
    elif key == "end":
        items = [item for item in items if item["group"] == "end"]
    elif key == "account_switch":
        items = [item for item in items if item["group"] == "account_switch"]
        return [
            {**item, "label": f"{idx + 1}. {item['label']}"}
            for idx, item in enumerate(items)
        ]
    elif key == "slideshow":
        items = [item for item in items if item["group"] == "slideshow"]
    elif key == "valcoin_prep":
        items = [item for item in items if item["group"] == "valcoin_prep"]
    return items


DEBUG_SKIP_MEDIA_KINDS = frozenset({
    "upload_gallery",
    "slideshow_generate",
    "album_clear",
})

DEBUG_SKIP_MEDIA_TEST_IDS = frozenset({
    "tap-post",
    "post-go-home",
})


def debug_test_skips_media(resolved_id: str, spec: DebugTest) -> bool:
    """True when UI-only debug should not generate, upload, delete, or publish."""
    if resolved_id in DEBUG_SKIP_MEDIA_TEST_IDS:
        return True
    return str(spec.get("kind") or "tap") in DEBUG_SKIP_MEDIA_KINDS


async def run_debug_test(
    app: Any, device_id: str, test_id: str, *, brand: str = "labely", skip_media: bool = False
) -> dict[str, Any]:
    from imouse_farm.actions.cancel import clear_cancelled

    clear_cancelled(device_id)
    resolved_id = resolve_flow_debug_test_id(test_id)
    spec = dict(get_debug_registry().get(resolved_id) or {})
    if not spec:
        raise HTTPException(404, f"Unknown debug test: {test_id}")
    if skip_media and debug_test_skips_media(resolved_id, spec):
        label = str(spec.get("label") or resolved_id)
        message = f"Skipped (UI-only): {label}"
        await app.db.log_activity(
            "info",
            "test",
            message,
            device_id,
            {"test_id": test_id, "resolved_id": resolved_id, "skipped": True, "skip_media": True},
        )
        return {"success": True, "message": message, "skipped": True}
    spec["_workflow_id"] = _workflow_id_for_debug(app, device_id, spec)
    kind = spec.get("kind", "tap")
    if kind == "upload_gallery":
        return await upload_gallery_debug(app, device_id, test_id, spec)
    if kind == "slideshow_generate":
        return await slideshow_generate_debug(app, device_id, test_id, spec)
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
    if kind == "home":
        return await home_debug(app, device_id, test_id, spec)
    if kind == "vpn_shortcut":
        return await vpn_shortcut_debug(app, device_id, test_id, spec)
    if kind == "vpn_off_before_album":
        return await vpn_off_before_album_debug(app, device_id, test_id, spec)
    if kind == "detect_ocr":
        return await detect_ocr_debug(app, device_id, test_id, spec)
    if kind == "warmup_run":
        warmup_brand = str(spec.get("brand") or brand)
        return await warmup_run_debug(app, device_id, test_id, spec, brand=warmup_brand)
    if kind == "vision_navigate":
        return await vision_navigate_debug(app, device_id, test_id, spec)
    if kind == "tiktok_popup_scan":
        return await tiktok_popup_scan_debug(app, device_id, test_id, spec)
    if kind == "permission_watcher_run":
        return await permission_watcher_run_debug(app, device_id, test_id, spec)
    if kind == "account_switch_step":
        return await account_switch_step_debug(app, device_id, test_id, spec, brand=brand)
    if kind == "detect":
        if spec.get("open_shadowrocket"):
            open_err = await _open_shadowrocket_via_shortcut_debug(app, device_id, spec, test_id)
            if open_err:
                return {**open_err, "detection": spec["detection"]}
        return await tap_detection(
            app,
            device_id,
            spec["detection"],
            hint=spec.get("hint", ""),
            offline_hint=spec.get("offline_hint", OFFLINE_HINT),
            test_id=test_id,
            tap=False,
            spec=spec,
        )
    return await tap_detection(
        app,
        device_id,
        spec["detection"],
        hint=spec.get("hint", ""),
        offline_hint=spec.get("offline_hint", OFFLINE_HINT),
        test_id=test_id,
        spec=spec,
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

    await _debug_execute_direct(
        app, device_id, spec, test_id, ActionType.HOME, {}, step_name=f"debug_{test_id}_home"
    )
    await asyncio.sleep(2)
    sequence: list[tuple[ActionType, dict[str, Any]]] = [
        (ActionType.SWIPE, dict(SPOTLIGHT_SWIPE)),
        (ActionType.CLEAR_TEXT, {}),
        (ActionType.TEXT_INPUT, {"text": "photos"}),
        (ActionType.TAP_OCR, {"texts": ["Photos", "photos"], "prefer_top": True, "optional": False}),
    ]
    for action_type, params in sequence:
        ok = await _debug_execute_direct(
            app,
            device_id,
            spec,
            test_id,
            action_type,
            params,
            step_name=f"debug_{test_id}_{action_type.value}",
        )
        if not ok:
            return {"success": False, "message": f"Failed at {action_type.value}"}
        await asyncio.sleep(2 if action_type == ActionType.SWIPE else 1)
    await app.screenshot_service.capture(device_id)
    await app.db.log_activity(
        "info", "test", "Debug open Photos via Spotlight OK", device_id, {"test_id": test_id}
    )
    return {"success": True, "message": "Opened Photos via Spotlight search"}


async def permission_watcher_run_debug(
    app: Any,
    device_id: str,
    test_id: str,
    spec: DebugTest,
) -> dict[str, Any]:
    """Run one full permission-watcher poll (same handlers as production background loop)."""
    from imouse_farm.permissions.watcher import PermissionWatcher, PermissionWatcherManager

    await _require_online_device(app, device_id, spec)
    await app.screenshot_service.capture(device_id)

    managers = getattr(app, "permission_watchers", None)
    if isinstance(managers, PermissionWatcherManager):
        handled = await managers.run_watcher_cycle(device_id)
    else:
        watcher = PermissionWatcher(
            app.device_manager.controller,
            device_id,
            device_manager=app.device_manager,
        )
        handled = await watcher.run_full_cycle()

    await app.screenshot_service.capture(device_id)
    message = (
        "Permission watcher handled a popup (tap/swipe applied)"
        if handled
        else "Permission watcher: no known popup handled this cycle"
    )
    payload = {"success": True, "message": message, "handled": handled}
    await app.db.log_activity(
        "info" if handled else "warn",
        "test",
        message,
        device_id,
        {"test_id": test_id, **payload},
    )
    return payload


async def tiktok_popup_scan_debug(
    app: Any,
    device_id: str,
    test_id: str,
    spec: DebugTest,
) -> dict[str, Any]:
    """OCR the screen and report how PermissionWatcher would handle known popups."""
    from imouse_farm.actions.permission_prompts import detect_tiktok_ai_pick_on_device
    from imouse_farm.permissions.watcher import (
        PermissionWatcher,
        detect_tiktok_add_phone_on_device,
        detect_tiktok_security_checkup_on_device,
    )

    await _require_online_device(app, device_id, spec)
    ctrl = app.device_manager.controller
    await app.screenshot_service.capture(device_id)

    screen = await ctrl.ocr_on_device(device_id)
    checkup_visible, checkup_ocr = await detect_tiktok_security_checkup_on_device(
        ctrl,
        device_id,
        screen=screen or "",
        device_manager=app.device_manager,
    )
    add_phone_visible, add_phone_ocr = await detect_tiktok_add_phone_on_device(
        ctrl,
        device_id,
        screen=screen or "",
        device_manager=app.device_manager,
    )
    ai_pick_visible, ai_pick_ocr = await detect_tiktok_ai_pick_on_device(
        ctrl,
        device_id,
        screen=screen or "",
        device_manager=app.device_manager,
    )
    extra_ocr = "\n".join(
        part for part in (checkup_ocr, add_phone_ocr, ai_pick_ocr) if part
    )
    analysis = analyze_popup_screen(screen or "")
    if analysis.get("dialog") == "none":
        analysis = analyze_popup_screen(extra_ocr or screen or "")

    button_matches: list[dict[str, Any]] = []
    labels = known_popup_watcher_button_labels()
    if labels:
        raw = await ctrl.find_text_on_device(device_id, labels, threshold=0.65)
        seen: set[tuple[str, int, int]] = set()
        for match in raw:
            text = str(match.get("text", "")).strip()
            x, y = int(match.get("x", 0)), int(match.get("y", 0))
            key = (text.lower(), x, y)
            if key in seen:
                continue
            seen.add(key)
            button_matches.append(
                {
                    "text": text,
                    "x": x,
                    "y": y,
                    "confidence": float(match.get("confidence", 0)),
                }
            )
        button_matches.sort(key=lambda m: (-m["confidence"], m["text"]))

    dialog = str(analysis.get("dialog", "none"))
    watcher_detail = str(analysis.get("watcher_detail", ""))
    if dialog == "none":
        headline = "No known TikTok / permission popup detected"
        success = False
        ocr_sample = (extra_ocr or screen or "").strip()
        if ocr_sample:
            snippet = ocr_sample[:280] + ("…" if len(ocr_sample) > 280 else "")
            watcher_detail = f"No popup matched. OCR sample: {snippet}"
    elif dialog == "photo_delete_sheet":
        headline = "Photo delete sheet (watcher skips)"
        success = True
    else:
        headline = f"Popup: {dialog.replace('_', ' ')} — {watcher_detail}"
        success = True

    button_bits = [
        f"{m['text']} @ ({m['x']}, {m['y']})" for m in button_matches[:8]
    ]
    parts = [headline]
    if button_bits:
        parts.append("Visible buttons: " + "; ".join(button_bits))
    elif analysis.get("tap_x") is not None and analysis.get("tap_y") is not None:
        parts.append(f"Watcher would tap coord ({analysis['tap_x']}, {analysis['tap_y']})")
    elif dialog == "tiktok_continue_editing":
        sx, sy = analysis.get("swipe_sx"), analysis.get("swipe_sy")
        ex, ey = analysis.get("swipe_ex"), analysis.get("swipe_ey")
        parts.append(f"Watcher would swipe up ({sx}, {sy}) → ({ex}, {ey})")
    planned = analysis.get("button_labels") or []
    if planned and dialog not in ("none", "photo_delete_sheet"):
        parts.append("Watcher search order: " + " → ".join(planned))
    message = " | ".join(parts)

    if spec.get("apply_watcher") and dialog not in ("none", "photo_delete_sheet"):
        watcher = PermissionWatcher(
            ctrl, device_id, device_manager=app.device_manager
        )
        handled = await watcher._check_once()
        await app.screenshot_service.capture(device_id)
        if handled:
            parts.append("Watcher applied: tapped dismiss button")
            message = " | ".join(parts)
            payload = {
                "success": True,
                "message": message,
                "dialog": dialog,
                "watcher_action": analysis.get("watcher_action"),
                "watcher_detail": watcher_detail,
                "visible_buttons": button_matches,
                "ocr_snippet": analysis.get("ocr_snippet", ""),
                "applied": True,
            }
            await app.db.log_activity(
                "info", "test", message, device_id, {"test_id": test_id, **payload}
            )
            return payload
        parts.append("Watcher applied: no tap (OCR/button miss)")
        message = " | ".join(parts)
        success = False

    payload = {
        "success": success,
        "message": message,
        "dialog": dialog,
        "watcher_action": analysis.get("watcher_action"),
        "watcher_detail": watcher_detail,
        "visible_buttons": button_matches,
        "ocr_snippet": analysis.get("ocr_snippet", ""),
    }
    level = "info" if success else "warn"
    await app.db.log_activity(level, "test", message, device_id, {"test_id": test_id, **payload})
    return payload


async def _open_shadowrocket_via_shortcut_debug(
    app: Any,
    device_id: str,
    spec: DebugTest,
    test_id: str,
) -> dict[str, Any] | None:
    """Open Shadowrocket via URL shortcut; return error dict on failure."""
    from imouse_farm.actions.vpn_shadowrocket import open_shadowrocket_via_shortcut

    try:
        await open_shadowrocket_via_shortcut(
            app.device_manager.controller,
            app.config,
            device_id,
        )
    except Exception as exc:
        return {"success": False, "message": str(exc)}
    await asyncio.sleep(1)
    return None


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
        open_err = await _open_shadowrocket_via_shortcut_debug(app, device_id, spec, test_id)
        if open_err:
            return open_err

    expect_missing = bool(spec.get("expect_missing"))
    try:
        ok = await _debug_execute_direct(
            app,
            device_id,
            spec,
            test_id,
            ActionType.TAP_OCR,
            {
                "texts": texts,
                "verify_only": True,
                "optional": False,
                "expect_missing": expect_missing,
            },
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


async def vision_navigate_debug(
    app: Any,
    device_id: str,
    test_id: str,
    spec: DebugTest,
) -> dict[str, Any]:
    """
    Screenshot → GPT decides tap or done → tap → screenshot again → repeat.
    Stops when GPT says done or after MAX_STEPS taps.
    """
    from openai import AsyncOpenAI

    from imouse_farm.workflows.vision_recovery import ask_vision_for_tap

    MAX_STEPS = 6

    dm = app.device_manager
    device = dm.get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not device.is_online:
        raise HTTPException(503, spec.get("offline_hint", OFFLINE_HINT))

    ctrl = app.device_manager.controller
    goal = str(spec.get("prompt") or "Navigate to the next step")

    openai_cfg = app.config.openai
    import os
    api_key = (os.environ.get("OPENAI_API_KEY") or openai_cfg.api_key or "").strip()
    client = AsyncOpenAI(api_key=api_key)

    await app.db.log_activity("info", "test", f"Vision: goal → {goal}", device_id)

    steps_taken = []
    for step in range(1, MAX_STEPS + 1):
        await app.db.log_activity("info", "test", f"Vision step {step}: taking screenshot…", device_id)

        try:
            x, y, reason = await ask_vision_for_tap(
                ctrl, device_id, goal=goal, app_config=app.config, client=client
            )
        except Exception as exc:
            msg = f"Vision step {step} failed: {type(exc).__name__}: {exc}"
            await app.db.log_activity("warn", "test", msg, device_id)
            return {"success": False, "message": msg, "steps": steps_taken}

        if x is None:
            await app.db.log_activity("info", "test", f"Vision: done — {reason}", device_id)
            return {"success": True, "message": f"Goal reached: {reason}", "steps": steps_taken}

        log_msg = f"Vision step {step}: tapping ({x}, {y}) — {reason}"
        await app.db.log_activity("info", "test", log_msg, device_id)
        steps_taken.append({"step": step, "x": x, "y": y, "reason": reason})

        await ctrl.tap(device_id, x, y)
        await __import__("asyncio").sleep(1.2)

    await app.db.log_activity("warn", "test", f"Vision: reached max {MAX_STEPS} steps without done", device_id)
    return {"success": False, "message": f"Max steps ({MAX_STEPS}) reached", "steps": steps_taken}


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
            "optional": bool(spec.get("optional", False)),
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
            "tap_count",
            "tap_interval_seconds",
            "require_dark_text",
            "max_text_luminance",
            "skip_if_texts_present",
            "skip_if_all_texts_present",
            "skip_if_story_button",
            "skip_if_threshold",
            "skip_if_ocr_ex",
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
        ok = await _debug_execute_direct(
            app, device_id, spec, test_id, ActionType.TAP_OCR, params
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
    """Poll after Favorites for Hvitserk or unstable-network retry while music loads."""
    await _require_online_device(app, device_id, spec)
    ctrl = app.device_manager.controller

    hvitserk_texts = list(spec.get("texts") or HVITSERK_CHOICE_TEXTS)
    unstable_texts = list(spec.get("unstable_texts") or UNSTABLE_NETWORK_TEXTS)
    total_wait = float(spec.get("wait_timeout_seconds", 0))
    after_retry_seconds = float(spec.get("after_retry_wait_seconds", 60))
    if total_wait <= 0:
        total_wait = float(spec.get("initial_wait_seconds", 30)) + after_retry_seconds
    max_wall = float(spec.get("max_wait_timeout_seconds", 0))
    if max_wall <= 0:
        max_wall = max(total_wait + after_retry_seconds * 3, 300.0)
    poll_interval = float(spec.get("poll_interval_seconds", 1.5))
    threshold = float(spec.get("threshold", 0.6))
    unstable_cooldown = float(spec.get("unstable_retry_cooldown_seconds", 2.0))

    steps: list[str] = []
    started_at = time.monotonic()
    deadline = started_at + total_wait
    last_unstable_tap_at = 0.0

    while time.monotonic() < deadline:
        hvitserk = await _best_ocr_match(
            ctrl, device_id, hvitserk_texts, threshold=threshold, contain=True
        )
        if hvitserk:
            tapped = await _tap_ocr_match(ctrl, device_id, hvitserk)
            await app.screenshot_service.capture(device_id)
            message = (
                f"Found Hvitserk ({hvitserk.get('text', '')!r}) and tapped"
                if tapped
                else f"Found Hvitserk ({hvitserk.get('text', '')!r}) but tap failed"
            )
            if steps:
                message = f"{' → '.join(steps)}; {message}"
            await app.db.log_activity(
                "info" if tapped else "warn",
                "test",
                f"Debug Hvitserk after Favorites: {message}",
                device_id,
                {"test_id": test_id, "text": hvitserk.get("text"), "steps": steps},
            )
            return {"success": tapped, "message": message, "steps": steps}

        now = time.monotonic()
        if now - last_unstable_tap_at >= unstable_cooldown:
            unstable = await _best_ocr_match(
                ctrl, device_id, unstable_texts, threshold=threshold, contain=True
            )
            if unstable:
                tapped_unstable = await _tap_ocr_match(ctrl, device_id, unstable)
                step = (
                    f"tapped unstable-network retry ({unstable.get('text', '')!r})"
                    if tapped_unstable
                    else "found unstable-network prompt but tap failed"
                )
                if step not in steps:
                    steps.append(step)
                if tapped_unstable:
                    last_unstable_tap_at = now
                    old_deadline = deadline
                    deadline = min(deadline + after_retry_seconds, started_at + max_wall)
                    if deadline > old_deadline:
                        steps.append(
                            f"extended wait +{deadline - old_deadline:.0f}s "
                            f"(up to {max_wall:.0f}s total)"
                        )
                    await asyncio.sleep(unstable_cooldown)
                    continue

        await asyncio.sleep(poll_interval)

    await app.screenshot_service.capture(device_id)
    elapsed = time.monotonic() - started_at
    message = (
        f"{' → '.join(steps)}; Hvitserk not found within {elapsed:.0f}s"
        if steps
        else f"Still loading — neither Hvitserk nor unstable retry within {elapsed:.0f}s"
    )
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
    """Clear photo library — VPN disconnect shortcut first, then album clear."""
    dm = app.device_manager
    device = dm.get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not device.is_online:
        raise HTTPException(503, spec.get("offline_hint", OFFLINE_HINT))

    timeout_ms = 60000
    params: dict[str, Any] = {
        "timeout_ms": timeout_ms,
        "sheet_appear_timeout_seconds": 18,
        "round_active_timeout_seconds": 60,
        "sheet_poll_interval_seconds": 5,
    }
    if spec.get("skip_vpn_off"):
        params["skip_vpn_off"] = True

    start = time.monotonic()
    error_detail = ""
    success = await _debug_execute_direct(
        app,
        device_id,
        spec,
        test_id,
        ActionType.ALBUM_CLEAR,
        params,
        step_name="clear_album",
    )
    duration_ms = int((time.monotonic() - start) * 1000)
    if not success:
        error_detail = await _latest_action_error(app, device_id, "album_clear")
        if not error_detail:
            error_detail = "album_clear returned false (items may remain in Recents)"

    if success:
        await app.screenshot_service.capture(device_id)

    if success:
        message = f"Cleared photo library on slot {device.user_name}"
    else:
        message = f"Album clear failed after {duration_ms // 1000}s"
        if error_detail:
            message += f" — {error_detail}"

    await app.db.log_activity(
        "info" if success else "warn",
        "test",
        f"Debug clear album {'OK' if success else 'failed'} — {message}",
        device_id,
        {"test_id": test_id, "duration_ms": duration_ms, "error": error_detail or None},
    )

    return {
        "success": success,
        "message": message,
        "error": error_detail or None,
        "timeout_ms": timeout_ms,
        "duration_ms": duration_ms,
        "slot": str(device.user_name or ""),
    }


async def slideshow_generate_debug(
    app: Any,
    device_id: str,
    test_id: str,
    spec: DebugTest,
) -> dict[str, Any]:
    """Start autoslideshow for one slot; ingest MP4s without running farm batch."""
    dm = app.device_manager
    device = dm.get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    slot = str(device.user_name or "").strip()
    if not slot:
        raise HTTPException(400, "Device has no farm slot (user_name) — register in iMouse first")

    brand = str(spec.get("brand") or "labely").strip().lower()
    if not app.config.slideshow.enabled:
        raise HTTPException(503, "Slideshow integration is disabled in config.yaml")

    await app.slideshow_orchestrator.cancel_running_jobs()

    try:
        result = await app.slideshow_orchestrator.start_job(
            brand=brand,
            slots=[slot],
            run_batch=False,
            videos_per_slot=max(1, int(app.config.slideshow.debug_slideshows_per_slot)),
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc

    job = result.get("job") or {}
    message = f"Started {brand} slideshow for slot {slot} (ingest only)"
    await app.db.log_activity(
        "info",
        "test",
        message,
        device_id,
        {
            "test_id": test_id,
            "brand": brand,
            "slot": slot,
            "job_id": job.get("id"),
            "automation_url": result.get("automation_url"),
        },
    )
    return {
        "success": True,
        "message": message,
        "job": job,
        "automation_url": result.get("automation_url"),
    }


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _latest_action_error(app: Any, device_id: str, action_type: str) -> str:
    history = await app.db.get_action_history(device_id, limit=8)
    for row in history:
        if str(row.get("action_type") or "") == action_type and row.get("status") == "failed":
            return str(row.get("error_message") or "").strip()
    return ""


def _upload_file_details(files: list[str]) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for raw in files:
        path = Path(raw)
        size_bytes = path.stat().st_size if path.is_file() else 0
        details.append(
            {
                "name": path.name,
                "path": str(path.resolve()),
                "size_bytes": size_bytes,
                "size_mb": round(size_bytes / (1024 * 1024), 2),
            }
        )
    return details


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
    brand = str(spec.get("brand") or "labely").strip().lower()
    folder = phone_gallery_folder(
        gallery.base_directory,
        device.user_name,
        device.phone_name,
        brand=brand,
    )
    files = list_media_files(folder, gallery.media_extensions)
    if not files:
        other_slots = slots_with_media(
            gallery.base_directory,
            gallery.media_extensions,
            brand=brand,
        )
        hint = (
            f"Run Generate & Run with slot {device.user_name} ticked, "
            f"or copy MP4s into {folder}"
        )
        if other_slots:
            slots_line = ", ".join(
                f"{item['slot']} ({item['file_count']} file(s))"
                for item in other_slots[:8]
            )
            hint += f". Media exists for other slot(s): {slots_line}"
        message = (
            f"No media files in {folder} — add videos/images for slot {device.user_name}. "
            f"{hint}"
        )
        await app.db.log_activity(
            "warn",
            "test",
            f"Debug upload: {message}",
            device_id,
            {
                "test_id": test_id,
                "folder": str(folder),
                "brand": brand,
                "slots_with_media": other_slots,
            },
        )
        return {
            "success": False,
            "message": message,
            "folder": str(folder),
            "file_count": 0,
            "brand": brand,
            "hint": hint,
            "slots_with_media": other_slots,
        }

    file_details = _upload_file_details(files)
    total_bytes = sum(int(item["size_bytes"]) for item in file_details)
    timeout_ms = int(gallery.upload_timeout_ms)
    file_sha256 = _file_sha256(files[0]) if files else ""

    # Upload follows clear in prep — VPN disconnect already ran on album_clear.
    upload_params: dict[str, Any] = {
        "folder": str(folder),
    }

    await app.db.log_activity(
        "info",
        "test",
        (
            f"Debug upload: {len(files)} file(s), "
            f"{round(total_bytes / (1024 * 1024), 1)} MB from {folder} "
            f"(timeout {timeout_ms // 1000}s, sha256={file_sha256[:12]}…)"
        ),
        device_id,
        {
            "test_id": test_id,
            "folder": str(folder),
            "brand": brand,
            "file_count": len(files),
            "files": [item["name"] for item in file_details],
            "total_bytes": total_bytes,
            "timeout_ms": timeout_ms,
            "file_sha256": file_sha256,
            "upload_params": upload_params,
        },
    )

    ctrl = dm.controller
    start = time.monotonic()
    success = await _debug_execute_direct(
        app,
        device_id,
        spec,
        test_id,
        ActionType.ALBUM_UPLOAD,
        upload_params,
        step_name="upload_gallery",
    )
    duration_ms = int((time.monotonic() - start) * 1000)
    error_detail = ""
    if not success:
        error_detail = await _latest_action_error(app, device_id, "album_upload")
        if not error_detail:
            error_detail = "album_upload returned false (files not confirmed on device)"

    album_count: int | None = None
    tapped_permissions: list[str] = []
    if success:
        try:
            album_count = len(await ctrl.album_list(device_id, album_name=None))
        except Exception as exc:
            logger.warning("debug_upload_album_list_failed", device_id=device_id, error=str(exc))
        await asyncio.sleep(10)
        tapped_permissions = await tap_permission_prompts(
            app, device_id, UPLOAD_PERMISSION_TEXTS, test_id=test_id
        )
        await app.screenshot_service.capture(device_id)

    if success:
        message = f"Uploaded {len(files)} file(s) from {folder}"
        if album_count is not None:
            message += f" — Recents has {album_count} item(s)"
    else:
        message = f"Gallery upload failed after {duration_ms // 1000}s"
        if error_detail:
            message += f" — {error_detail}"

    await app.db.log_activity(
        "info" if success else "warn",
        "test",
        f"Debug upload gallery {'OK' if success else 'failed'} — {message}",
        device_id,
        {
            "test_id": test_id,
            "folder": str(folder),
            "file_count": len(files),
            "duration_ms": duration_ms,
            "error": error_detail or None,
            "album_count": album_count,
        },
    )

    if tapped_permissions:
        message += f" — tapped {', '.join(tapped_permissions)}"

    return {
        "success": success,
        "message": message,
        "error": error_detail or None,
        "folder": str(folder),
        "brand": brand,
        "file_count": len(files),
        "files": [item["name"] for item in file_details],
        "file_details": file_details,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "timeout_ms": timeout_ms,
        "duration_ms": duration_ms,
        "album_count": album_count,
        "tapped_permissions": tapped_permissions,
        "file_sha256": file_sha256,
        "upload_params": upload_params,
    }


def _workflow_id_for_debug(app: Any, device_id: str, spec: DebugTest) -> str | None:
    """Active workflow name, or infer prep/post/end from debug tab group."""
    device = app.device_manager.get_device(device_id)
    if device and device.workflow_name:
        return device.workflow_name
    return {
        "prep": "tiktok_prep",
        "post": "tiktok_post",
        "end": "tiktok_end",
        "account_switch": "tiktok_account_switch",
        "valcoin_prep": "tiktok_valcoin_prep",
    }.get(str(spec.get("group", "")))


async def _debug_execute_direct(
    app: Any,
    device_id: str,
    spec: DebugTest,
    test_id: str,
    action_type: ActionType,
    params: dict[str, Any] | None = None,
    *,
    step_name: str | None = None,
) -> bool:
    workflow_id = spec.get("_workflow_id") or _workflow_id_for_debug(app, device_id, spec)
    return await app.action_engine.execute_direct(
        device_id,
        action_type,
        params or {},
        workflow_id=str(workflow_id) if workflow_id else None,
        step_name=step_name or f"debug_{test_id}",
    )


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
    ok = await _debug_execute_direct(
        app, device_id, spec, test_id, ActionType.TAP, params
    )
    if not ok:
        await app.screenshot_service.capture(device_id)
        return {"success": False, "message": f"Tap failed at ({x}, {y})"}
    if spec.get("wait_for_tiktok_ready"):
        try:
            await _wait_for_tiktok_ready_debug(app, device_id, test_id, spec)
        except RuntimeError as exc:
            await app.screenshot_service.capture(device_id)
            return {"success": False, "message": str(exc)}
    await app.screenshot_service.capture(device_id)
    count = int(params.get("tap_count", 1))
    msg = f"Tapped ({x}, {y}) ×{count}" if count > 1 else f"Tapped ({x}, {y})"
    if spec.get("wait_for_tiktok_ready"):
        msg += " — TikTok + visible (home feed ready)"
    return {"success": True, "message": msg, "x": x, "y": y}


async def _wait_for_tiktok_ready_debug(
    app: Any,
    device_id: str,
    test_id: str,
    spec: DebugTest,
) -> None:
    from imouse_farm.workflows.tiktok_plus_ready import wait_for_tiktok_plus_visible

    timeout = float(spec.get("tiktok_ready_timeout_seconds") or 120.0)

    async def _log(
        level: str,
        category: str,
        message: str,
        *args: Any,
        **details: Any,
    ) -> None:
        await app.db.log_activity(
            level,
            category,
            message,
            device_id,
            {"test_id": test_id, **details},
        )

    await wait_for_tiktok_plus_visible(
        app.device_manager.controller,
        device_id,
        device_manager=app.device_manager,
        vision=app.vision,
        app_config=app.config,
        templates_directory=app.config.analysis.templates_directory,
        log_activity=_log,
        timeout_seconds=timeout,
    )


async def swipe_debug(app: Any, device_id: str, test_id: str, spec: DebugTest) -> dict[str, Any]:
    await _require_online_device(app, device_id, spec)
    params = {
        "direction": spec.get("direction", "left"),
        "sx": spec.get("sx"),
        "sy": spec.get("sy"),
        "ex": spec.get("ex"),
        "ey": spec.get("ey"),
    }
    if "swipe_count" in spec:
        params["swipe_count"] = int(spec["swipe_count"])
    if "swipe_interval_seconds" in spec:
        params["swipe_interval_seconds"] = float(spec["swipe_interval_seconds"])
    ok = await _debug_execute_direct(
        app, device_id, spec, test_id, ActionType.SWIPE, params
    )
    await app.screenshot_service.capture(device_id)
    count = int(params.get("swipe_count", 1))
    msg = f"Swipe {params['direction']} ×{count}" if count > 1 else f"Swipe {params['direction']}"
    return {"success": ok, "message": msg}


async def account_switch_step_debug(
    app: Any,
    device_id: str,
    test_id: str,
    spec: DebugTest,
    *,
    brand: str = "labely",
) -> dict[str, Any]:
    """Isolated account-switch steps for dashboard debug."""
    from imouse_farm.post.account_profile_store import (
        get_profile_for_device,
        handle_match_queries,
        opposite_brand,
    )
    from imouse_farm.workflows.tiktok_device_ui import (
        alternate_account_switcher_opener,
        uses_alternate_account_switcher_ui,
    )
    from imouse_farm.workflows.account_switch import (
        _switcher_shows_account,
        _tap_account_switcher_opener,
        _tap_handle_in_list,
        ensure_tiktok_account,
    )

    device = await _require_online_device(app, device_id, spec)
    ctrl = app.device_manager.controller
    nav = app.config.tiktok_navigation
    step = str(spec.get("step") or "ensure")
    toggle_to_opposite = bool(spec.get("toggle_to_opposite"))
    profile = get_profile_for_device(device_id, device.user_name, brand=brand)
    handle = str(profile.get("tiktok_handle") or "").strip()
    other_profile = get_profile_for_device(
        device_id, device.user_name, brand=opposite_brand(brand)
    )
    switch_tap_handle = str(other_profile.get("tiktok_handle") or "").strip()
    dest_handle = switch_tap_handle if toggle_to_opposite else handle

    switch_queries = handle_match_queries(switch_tap_handle) if switch_tap_handle else []

    async def _tap_nav_xy(x: int, y: int, *, step_suffix: str) -> bool:
        return await _debug_execute_direct(
            app,
            device_id,
            spec,
            test_id,
            ActionType.TAP,
            {"x": x, "y": y},
            step_name=f"debug_{test_id}_{step_suffix}",
        )

    async def _switcher_visibility_message(prefix: str) -> tuple[str, bool | None]:
        if not switch_queries:
            return prefix, None
        visible = await _switcher_shows_account(ctrl, device_id, switch_queries)
        suffix = f" — @ list {'visible' if visible else 'not visible'}"
        if switch_tap_handle:
            suffix += f" ({switch_tap_handle})"
        return prefix + suffix, visible

    if step == "tap_profile":
        ok = await _tap_nav_xy(nav.profile_tab_x, nav.profile_tab_y, step_suffix="profile")
        await app.screenshot_service.capture(device_id)
        if not ok:
            return {"success": False, "message": "Failed to tap profile tab"}
        message = f"Tapped profile tab ({nav.profile_tab_x}, {nav.profile_tab_y})"
        await app.db.log_activity(
            "info", "test", message, device_id, {"test_id": test_id}
        )
        return {"success": True, "message": message}

    if step == "tap_opener_primary":
        if uses_alternate_account_switcher_ui(app.config, device.user_name):
            opener = alternate_account_switcher_opener(app.config, device.user_name)
            x, y = int(opener.x), int(opener.y) if opener else (0, 0)
            label = f"alternate UI opener ({x}, {y})"
        else:
            x, y = nav.account_switcher_opener_x, nav.account_switcher_opener_y
            label = f"primary opener ({x}, {y})"
        ok = await _tap_nav_xy(x, y, step_suffix="opener_primary")
        await asyncio.sleep(1.0)
        await app.screenshot_service.capture(device_id)
        if not ok:
            return {"success": False, "message": f"Failed to tap {label}"}
        message, visible = await _switcher_visibility_message(f"Tapped {label}")
        await app.db.log_activity(
            "info", "test", message, device_id, {"test_id": test_id, "visible": visible}
        )
        return {"success": True, "message": message, "switcher_visible": visible}

    if step == "tap_opener_alt":
        if uses_alternate_account_switcher_ui(app.config, device.user_name):
            return {
                "success": True,
                "message": (
                    f"Phone {device.user_name} uses alternate UI — "
                    "alt opener (301/293) not used; run primary step instead"
                ),
                "skipped": True,
            }
        x, y = nav.account_switcher_opener_alt_x, nav.account_switcher_opener_alt_y
        ok = await _tap_nav_xy(x, y, step_suffix="opener_alt")
        await asyncio.sleep(1.0)
        await app.screenshot_service.capture(device_id)
        if not ok:
            return {"success": False, "message": f"Failed to tap alt opener ({x}, {y})"}
        message, visible = await _switcher_visibility_message(
            f"Tapped alt opener ({x}, {y})"
        )
        await app.db.log_activity(
            "info", "test", message, device_id, {"test_id": test_id, "visible": visible}
        )
        return {"success": True, "message": message, "switcher_visible": visible}

    if step == "verify_switcher":
        if not switch_queries:
            return {
                "success": False,
                "message": (
                    f"No @ handle saved for {opposite_brand(brand)} on this slot — "
                    "set it on the other dashboard first."
                ),
            }
        visible = await _switcher_shows_account(ctrl, device_id, switch_queries)
        await app.screenshot_service.capture(device_id)
        message = (
            f"Switcher OCR: {switch_tap_handle} {'found' if visible else 'not found'}"
        )
        await app.db.log_activity(
            "info" if visible else "warn",
            "test",
            message,
            device_id,
            {"test_id": test_id, "handle": switch_tap_handle, "visible": visible},
        )
        return {
            "success": visible,
            "message": message,
            "handle": switch_tap_handle,
            "switcher_visible": visible,
        }

    if step == "ensure":
        if toggle_to_opposite:
            if not switch_tap_handle:
                return {
                    "success": False,
                    "message": (
                        f"No @ handle saved for {opposite_brand(brand)} on this slot — "
                        "set it on the other dashboard first."
                    ),
                }
        elif not handle:
            return {
                "success": False,
                "message": "No @ handle saved for this slot — set it in Content panel first.",
            }

        async def _log(
            level: str,
            category: str,
            message: str,
            *args: Any,
            **details: Any,
        ) -> None:
            await app.db.log_activity(
                level,
                category,
                message,
                device_id,
                {"test_id": test_id, **details},
            )

        async def _clear_popups(context: str) -> bool:
            watchers = getattr(app, "permission_watchers", None)
            if watchers is None:
                return False
            cleared = 0
            for _ in range(5):
                if not await watchers.try_dismiss(device_id):
                    break
                cleared += 1
                await asyncio.sleep(1.0)
            return cleared > 0

        try:
            await ensure_tiktok_account(
                controller=ctrl,
                device_id=device_id,
                tiktok_handle=handle,
                navigation=nav,
                log_activity=_log,
                device_manager=app.device_manager,
                templates_dir=app.config.analysis.templates_directory,
                vision=app.vision,
                app_config=app.config,
                brand=brand,
                device_user_name=device.user_name,
                toggle_to_opposite=toggle_to_opposite,
                tiktok_ready_timeout_seconds=180.0,
                clear_popups=_clear_popups,
            )
        except RuntimeError as exc:
            await app.screenshot_service.capture(device_id)
            return {"success": False, "message": str(exc), "handle": dest_handle}
        except Exception as exc:
            await app.screenshot_service.capture(device_id)
            return {
                "success": False,
                "message": f"Account switch error: {exc}",
                "handle": dest_handle,
            }
        await app.screenshot_service.capture(device_id)
        await app.db.log_activity(
            "info",
            "test",
            f"Account switch OK for {dest_handle}",
            device_id,
            {"test_id": test_id, "handle": dest_handle},
        )
        return {
            "success": True,
            "message": f"Account switch completed for {dest_handle}",
            "handle": dest_handle,
        }

    if step == "open_switcher":
        ok = await _debug_execute_direct(
            app,
            device_id,
            spec,
            test_id,
            ActionType.TAP,
            {"x": nav.profile_tab_x, "y": nav.profile_tab_y},
            step_name=f"debug_{test_id}_profile",
        )
        if not ok:
            return {"success": False, "message": "Failed to tap profile tab"}
        await asyncio.sleep(2.0)
        opened = await _tap_account_switcher_opener(
            ctrl,
            device_id,
            nav,
            switch_queries,
            app_config=app.config,
            device_user_name=device.user_name,
        )
        await app.screenshot_service.capture(device_id)
        if not opened:
            return {
                "success": False,
                "message": (
                    "Failed to open account switcher — tried primary "
                    f"({nav.account_switcher_opener_x}, {nav.account_switcher_opener_y}) "
                    f"then alt ({nav.account_switcher_opener_alt_x}, {nav.account_switcher_opener_alt_y})"
                ),
            }
        await app.db.log_activity(
            "info",
            "test",
            "Opened account switcher (production sequence)",
            device_id,
            {"test_id": test_id},
        )
        return {
            "success": True,
            "message": "Tapped profile then production switcher opener sequence",
        }

    if step == "pick_handle":
        if not switch_tap_handle:
            return {
                "success": False,
                "message": (
                    f"No @ handle saved for {opposite_brand(brand)} on this slot — "
                    "set it on the other dashboard first."
                ),
            }

        queries = handle_match_queries(switch_tap_handle)
        picked = await _tap_handle_in_list(ctrl, device_id, queries)
        await app.screenshot_service.capture(device_id)
        if not picked:
            return {
                "success": False,
                "message": f"Could not find {switch_tap_handle} on screen via OCR",
                "handle": switch_tap_handle,
            }
        await app.db.log_activity(
            "info",
            "test",
            f"Tapped {switch_tap_handle} in account list",
            device_id,
            {"test_id": test_id, "handle": switch_tap_handle, "brand": opposite_brand(brand)},
        )
        return {
            "success": True,
            "message": f"Tapped {switch_tap_handle} ({opposite_brand(brand)})",
            "handle": switch_tap_handle,
        }

    raise HTTPException(400, f"Unknown account_switch step: {step}")


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
    ok = await _debug_execute_direct(
        app, device_id, spec, test_id, ActionType.DRAG, params
    )
    await app.screenshot_service.capture(device_id)
    if "x2" in params and "y2" in params:
        msg = f"Drag ({params['x1']},{params['y1']})→({params['x2']},{params['y2']})"
    else:
        msg = "Drag complete"
    if params.get("duration_ms"):
        msg += f", hold {int(params['duration_ms'])}ms"
    return {"success": ok, "message": msg, **params}


async def type_caption_debug(app: Any, device_id: str, test_id: str, spec: DebugTest) -> dict[str, Any]:
    device = await _require_online_device(app, device_id, spec)
    post_num = int(spec.get("post_num", 1))
    text_key = device_storage_key(device.device_id, device.user_name)
    text = get_onscreen_text(text_key, post_num)
    ok = await _debug_execute_direct(
        app, device_id, spec, test_id, ActionType.TEXT_INPUT, {"text": text}
    )
    await app.screenshot_service.capture(device_id)
    return {"success": ok, "message": f"Typed onscreen text ({len(text)} chars)", "text": text}


async def type_final_caption_debug(app: Any, device_id: str, test_id: str, spec: DebugTest) -> dict[str, Any]:
    device = await _require_online_device(app, device_id, spec)
    post_num = int(spec.get("post_num", 1))
    text_key = device_storage_key(device.device_id, device.user_name)
    text = get_final_caption(text_key, post_num)
    ok = await _debug_execute_direct(
        app,
        device_id,
        spec,
        test_id,
        ActionType.TEXT_INPUT,
        {"text": text, "single_line": True},
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

    tap_params: dict[str, Any] = {"x": x, "y": y, "tap_count": 2, "tap_interval_seconds": 0.5}
    if "tap_count" in spec:
        tap_params["tap_count"] = max(2, int(spec["tap_count"]))
    if "tap_interval_seconds" in spec:
        tap_params["tap_interval_seconds"] = float(spec["tap_interval_seconds"])

    tapped = await _debug_execute_direct(
        app,
        device_id,
        spec,
        test_id,
        ActionType.TAP,
        tap_params,
        step_name=f"{step}_gallery",
    )
    if not tapped:
        from imouse_farm.actions.cancel import is_cancelled

        device = app.device_manager.get_device(device_id)
        if is_cancelled(device_id):
            reason = "device actions were cancelled (run again after Stop)"
        elif not device or not device.is_online:
            reason = "device is offline — reconnect AirPlay first"
        else:
            reason = "iMouse tap failed (try Restart server if this persists)"
        return {
            "success": False,
            "message": f"Failed to tap gallery at ({x}, {y}) — {reason}",
        }

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

    ok = await _debug_execute_direct(
        app,
        device_id,
        spec,
        test_id,
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
    ctrl = app.device_manager.controller

    tapped_media = await _debug_execute_direct(
        app,
        device_id,
        spec,
        test_id,
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
    await _debug_execute_direct(
        app,
        device_id,
        spec,
        test_id,
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

    step = f"debug_{test_id}"

    tapped = await _debug_execute_direct(
        app,
        device_id,
        spec,
        test_id,
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

    typed = await _debug_execute_direct(
        app,
        device_id,
        spec,
        test_id,
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
            f"Use Tap post (544, 68) to finish."
        ),
        "post_num": post_num,
        "char_count": len(flat),
        "text_preview": flat[:120] + ("…" if len(flat) > 120 else ""),
    }


async def home_debug(app: Any, device_id: str, test_id: str, spec: DebugTest) -> dict[str, Any]:
    await _require_online_device(app, device_id, spec)
    ok = await _debug_execute_direct(
        app, device_id, spec, test_id, ActionType.HOME, {}
    )
    await app.screenshot_service.capture(device_id)
    return {"success": ok, "message": "Pressed home"}


async def vpn_off_before_album_debug(
    app: Any, device_id: str, test_id: str, spec: DebugTest
) -> dict[str, Any]:
    """Run ensure_vpn_off_before_album — the exact VPN-off preamble before album clear."""
    from imouse_farm.actions.vpn_shadowrocket import (
        ensure_vpn_off_before_album,
        vpn_shortcut_url,
    )

    await _require_online_device(app, device_id, spec)
    url = vpn_shortcut_url(app.config, "off")
    settle = float(app.config.vpn.shortcut_settle_seconds)

    async def _log(
        level: str,
        category: str,
        message: str,
        *args: Any,
        **details: Any,
    ) -> None:
        await app.db.log_activity(
            level,
            category,
            message,
            device_id,
            {"test_id": test_id, **details},
        )

    await _log(
        "info",
        "test",
        (
            f"Production clear_album VPN preamble — URL {url!r}, "
            f"settle {settle:g}s, SDK shortcut_exec_url"
        ),
        url=url,
        settle_seconds=settle,
        production_step="clear_album",
    )

    start = time.monotonic()
    try:
        await ensure_vpn_off_before_album(
            app.device_manager.controller,
            app.config,
            app.device_manager,
            device_id,
            log_activity=_log,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        message = f"VPN off before album failed after {duration_ms // 1000}s — {exc}"
        await _log("error", "test", message, url=url, error=str(exc))
        await app.screenshot_service.capture(device_id)
        return {
            "success": False,
            "message": message,
            "url": url,
            "error": str(exc),
            "duration_ms": duration_ms,
        }

    duration_ms = int((time.monotonic() - start) * 1000)
    await app.screenshot_service.capture(device_id)
    message = f"VPN off before album OK ({url}) — same path as production clear_album"
    await _log("info", "test", message, url=url, duration_ms=duration_ms)
    return {
        "success": True,
        "message": message,
        "url": url,
        "duration_ms": duration_ms,
    }


async def vpn_shortcut_debug(
    app: Any, device_id: str, test_id: str, spec: DebugTest
) -> dict[str, Any]:
    from imouse_farm.actions.vpn_shadowrocket import (
        VpnShortcutMode,
        exec_vpn_shortcut_url,
        vpn_shortcut_url,
    )

    await _require_online_device(app, device_id, spec)
    mode = str(spec.get("mode") or "toggle").strip().lower()
    if mode not in ("on", "off", "toggle", "open"):
        raise HTTPException(400, f"Invalid VPN shortcut mode: {mode}")
    url = str(spec.get("url") or "").strip() or vpn_shortcut_url(
        app.config, mode  # type: ignore[arg-type]
    )
    if not url:
        config_key = "open" if mode == "open" else mode
        raise HTTPException(
            400,
            f"VPN shortcut URL for mode={mode!r} is empty — set vpn.shortcut_url_{config_key} in config.yaml",
        )
    settle = float(spec.get("settle_seconds") or app.config.vpn.shortcut_settle_seconds)
    outtime_ms = int(app.config.vpn.shortcut_url_timeout_ms)
    press_home_after = bool(spec.get("press_home_after", mode != "open"))
    try:
        await exec_vpn_shortcut_url(
            app.device_manager.controller,
            device_id,
            url,
            settle_seconds=settle,
            outtime_ms=outtime_ms,
            press_home_after=press_home_after,
        )
    except Exception as exc:
        await app.db.log_activity(
            "error",
            "test",
            f"VPN shortcut failed: {exc}",
            device_id,
            {"test_id": test_id, "url": url, "mode": mode},
        )
        return {"success": False, "message": str(exc), "url": url, "mode": mode}
    await app.screenshot_service.capture(device_id)
    label = {"on": "ON", "off": "OFF", "toggle": "toggle", "open": "open"}[mode]
    message = f"VPN shortcut {label}: opened {url}"
    await app.db.log_activity(
        "info",
        "test",
        message,
        device_id,
        {"test_id": test_id, "url": url, "mode": mode},
    )
    return {"success": True, "message": message, "url": url, "mode": mode}


async def kill_app_debug(app: Any, device_id: str, test_id: str, spec: DebugTest) -> dict[str, Any]:
    await _require_online_device(app, device_id, spec)
    ok = await _debug_execute_direct(
        app, device_id, spec, test_id, ActionType.KILL_APP, {}
    )
    await app.screenshot_service.capture(device_id)
    return {"success": ok, "message": "Force-quit: App button + 5 swipe ups"}


async def close_app_debug(app: Any, device_id: str, test_id: str, spec: DebugTest) -> dict[str, Any]:
    await _require_online_device(app, device_id, spec)
    ok = await _debug_execute_direct(
        app, device_id, spec, test_id, ActionType.CLOSE_APP, {}
    )
    await app.screenshot_service.capture(device_id)
    return {"success": ok, "message": "Closed app (pressed home)"}


async def _scan_template_detection(
    app: Any,
    device_id: str,
    detection: str,
    spec: DebugTest | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Capture one or more frames and return the strongest template/OCR hit."""
    dm = app.device_manager
    device = dm.get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")

    samples = max(1, int(spec.get("samples_per_poll", 1))) if spec else 1
    sample_interval = float(spec.get("sample_interval_seconds", 0.45)) if spec else 0.45
    ocr_texts = [
        str(t).strip()
        for t in (spec.get("ocr_fallback_texts") or []) if spec
        if str(t).strip()
    ]
    ocr_threshold = float(spec.get("ocr_threshold", 0.48)) if spec else 0.48
    ocr_ex = bool(spec.get("ocr_ex", False)) if spec else False
    prefer_top = bool(spec.get("prefer_top", True)) if spec else True
    raw_rect = spec.get("ocr_search_rect_pct") if spec else None
    ocr_rect: list[int] | None = None
    if isinstance(raw_rect, list) and len(raw_rect) == 4:
        ocr_rect = ocr_rect_from_pct(device.screen_width, device.screen_height, raw_rect)

    shot: dict[str, Any] | None = None
    detections: dict[str, dict[str, Any]] = {}
    best_hit: dict[str, Any] | None = None

    for sample_idx in range(samples):
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
        sample_detections: dict[str, dict[str, Any]] = {
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
                existing = sample_detections.get(tmpl_name)
                if not existing or hit["confidence"] >= existing.get("confidence", 0):
                    sample_detections[tmpl_name] = hit

        sample_detections = apply_detection_fallbacks(sample_detections)
        sample_detections = apply_exclusive_detections(sample_detections)
        if hasattr(vision, "min_confidence_for"):
            for name in list(sample_detections):
                min_conf = vision.min_confidence_for(name)
                if min_conf is not None and float(sample_detections[name].get("confidence", 0)) < min_conf:
                    del sample_detections[name]
        if hasattr(vision, "tap_offset_for"):
            sample_detections = apply_tap_offsets(sample_detections, vision.tap_offset_for)

        template_hit = pick_detection_hit(sample_detections, detection)
        if template_hit:
            template_hit = dict(template_hit)
            template_hit.setdefault("detection_type", "template")
            best_hit = stronger_hit(best_hit, template_hit)

        if ocr_texts:
            for query in ocr_texts:
                matches = await dm.controller.find_text_on_device(
                    device_id,
                    [query],
                    threshold=ocr_threshold,
                    contain=True,
                    rect=ocr_rect,
                    is_ex=ocr_ex,
                )
                if not matches:
                    continue
                if prefer_top:
                    ocr_match = min(matches, key=lambda m: int(m.get("y", 9999)))
                else:
                    ocr_match = max(matches, key=lambda m: float(m.get("confidence", 0)))
                ocr_entry = {
                    "x": int(ocr_match["x"]),
                    "y": int(ocr_match["y"]),
                    "confidence": float(ocr_match.get("confidence", 0.85)),
                    "matched_via": "ocr",
                    "detection_type": "ocr",
                    "text": ocr_match.get("text") or query,
                }
                best_hit = stronger_hit(best_hit, ocr_entry)
                break

        detections = sample_detections
        if sample_idx < samples - 1:
            await asyncio.sleep(sample_interval)

    if best_hit:
        detections[detection] = best_hit
    if not shot:
        raise HTTPException(500, "Screenshot failed")
    return shot, detections


async def tap_detection(
    app: Any,
    device_id: str,
    detection: str,
    *,
    hint: str,
    offline_hint: str = OFFLINE_HINT,
    test_id: str | None = None,
    tap: bool = True,
    spec: DebugTest | None = None,
) -> dict[str, Any]:
    """Screenshot → find template → tap (or detect-only when ``tap=False``)."""
    device = app.device_manager.get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not device.is_online:
        raise HTTPException(503, offline_hint)

    poll_interval = float(spec.get("poll_interval_seconds", 0)) if spec else 0.0
    wait_timeout = float(spec.get("wait_timeout_seconds", 60)) if spec else 0.0
    poll = poll_interval > 0 and wait_timeout > 0
    deadline = time.monotonic() + wait_timeout if poll else None
    attempt = 0
    shot: dict[str, Any] | None = None
    detections: dict[str, dict[str, Any]] = {}

    while True:
        attempt += 1
        shot, detections = await _scan_template_detection(
            app, device_id, detection, spec
        )
        if detection in detections:
            break
        if not poll or (deadline is not None and time.monotonic() >= deadline):
            break
        await app.db.log_activity(
            "info",
            "test",
            f"Waiting for {detection} (attempt {attempt}, retry in {poll_interval:.0f}s)",
            device_id,
            {"test_id": test_id, "template": detection, "attempt": attempt},
        )
        await asyncio.sleep(poll_interval)

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
    tap_params: dict[str, Any] = {"detection": detection, "refind_on_device": True}
    if spec:
        if "tap_count" in spec:
            tap_params["tap_count"] = int(spec["tap_count"])
        if "tap_interval_seconds" in spec:
            tap_params["tap_interval_seconds"] = float(spec["tap_interval_seconds"])
    if spec and test_id:
        success = await _debug_execute_direct(
            app,
            device_id,
            spec,
            test_id,
            ActionType.TAP_DETECTION,
            tap_params,
            step_name=f"debug_{test_id or detection}",
        )
    else:
        success = await app.action_engine.execute_direct(
            device_id,
            ActionType.TAP_DETECTION,
            tap_params,
            step_name=f"debug_{test_id or detection}",
        )

    post_tap_delay = float(spec.get("post_tap_delay_seconds", 0)) if spec else 0.0
    if post_tap_delay > 0:
        await app.db.log_activity(
            "info",
            "test",
            f"Settling {post_tap_delay:.0f}s after tapping {detection}",
            device_id,
            {"test_id": test_id, "delay_seconds": post_tap_delay},
        )
        await asyncio.sleep(post_tap_delay)

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


async def warmup_run_debug(
    app: Any,
    device_id: str,
    test_id: str,
    spec: DebugTest,
    *,
    brand: str = "valcoin",
) -> dict[str, Any]:
    """Run the warmup scroll for the device (TikTok must already be open on correct account)."""
    from imouse_farm.workflows.warmup import run_tiktok_warmup

    device = await _require_online_device(app, device_id, spec)
    duration_override = float(spec["duration_seconds"]) if "duration_seconds" in spec else None
    skip_setup = bool(spec.get("skip_setup", False))

    async def _log(level: str, category: str, message: str, *_args: Any, **_kw: Any) -> None:
        await app.db.log_activity(level, category, message, device_id, {"test_id": test_id})

    try:
        await run_tiktok_warmup(
            app.device_manager.controller,
            device,
            brand=brand,
            app_config=app.config,
            device_manager=app.device_manager,
            log_activity=_log,
            duration_override=duration_override,
            skip_setup=skip_setup,
        )
    except Exception as exc:
        return {"success": False, "message": str(exc)}
    return {"success": True, "message": f"Warmup complete for {device_id}"}


async def tap_vpntoggle(app: Any, device_id: str) -> dict[str, Any]:
    """Backward-compatible alias for the VPN toggle debug test."""
    return await run_debug_test(app, device_id, "tap-vpntoggle")
