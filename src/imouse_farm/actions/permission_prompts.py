"""iOS permission dialog handling for TikTok and system alerts."""

from __future__ import annotations

import re
from typing import Any

from imouse_farm.vision.ocr_match import ocr_compact, ocr_contains_phrase

# Prefer specific labels first (e.g. "Always Allow" before bare "Allow").
UPLOAD_PERMISSION_TEXTS = [
    "Always Allow",
    "Allow Full Access",
    "Allow Access to All Photos",
    "Allow Paste",
    "Allow",
]

DELETE_ALL_COUNT_RE = re.compile(r"delete\s+all\s*[\(\[]?\s*\d+", re.IGNORECASE)
DELETE_EVERYTHING_RE = re.compile(r"delete\s+everything", re.IGNORECASE)

DELETE_CONFIRM_TEXTS = [
    "Delete Everything",
    "DELETE EVERYTHING",
    "Delete Always",
    "Delete All Photos",
    "Delete All (",
    "Delete All",
    "Delete Items",
    "Delete Photos",
    "Delete Photo",
    "Delete",
]

# Longer / more specific labels win when multiple delete buttons match.
DELETE_LABEL_PRIORITY: tuple[tuple[str, int], ...] = (
    ("delete everything", 9),
    ("delete all (", 8),
    ("delete all", 7),
    ("delete always", 6),
    ("delete all photos", 5),
    ("delete items", 3),
    ("delete photos", 3),
    ("delete photo", 2),
    ("delete", 1),
)

# Bulk-delete labels — prefer these over bare "Delete" when both are on screen.
BULK_DELETE_PHRASES = (
    "delete everything",
    "delete always",
    "delete all photos",
    "delete all",
    "delete items",
    "delete photos",
)

DELETE_SHEET_DISTRACTOR_TEXTS = [
    "Show All",
    "See All Photos",
    "View All Photos",
]

# Delete confirm sits in the bottom action sheet on typical iPhone layouts (406×720).
DELETE_SHEET_MIN_Y = 500
DELETE_SHEET_RELAXED_MIN_Y = 460
DELETE_SHEET_SIGNAL_MIN_Y = 380

# Labels that must never be tapped during album clear.
DELETE_DISTRACTOR_SUBSTRINGS = (
    "show all",
    "see all",
    "view all",
    "see all photos",
    "view all photos",
    "select",
    "cancel",
    "keep",
)

# Tap these to deny unwanted permissions (most specific first).
DENY_BUTTON_TEXTS = [
    "Ask App Not to Track",
    "Don't Allow",
    "Dont Allow",
]

# TikTok in-app prompts we dismiss with "Not Now" (not iOS system sheets).
TIKTOK_EMAIL_CONFIRM_KEYWORDS = (
    "confirm use of email",
    "confirm your email",
    "use your email",
    "use of email",
    "link your email",
    "verify your email",
    "add your email",
)

TIKTOK_SAVE_LOGIN_KEYWORDS = (
    "save login for next time",
    "save login for next",
    "save your login",
)

TIKTOK_NOT_NOW_BUTTON_TEXTS = [
    "Not Now",
    "NOT NOW",
    "Not now",
]

# TikTok in-app prompt: "Get notified …" → tap above center near top to dismiss.
TIKTOK_POST_NOTIFY_DISMISS_X = 203
TIKTOK_POST_NOTIFY_DISMISS_Y = 63

TIKTOK_POST_NOTIFY_KEYWORDS = (
    "get notified of post interactions",
    "notified of post interactions",
    "post interactions?",
)

TIKTOK_CONTINUE_EDITING_KEYWORDS = (
    "continue editing this post",
    "continue editing",
)

TIKTOK_CONTINUE_EDITING_SWIPE_X = 65
TIKTOK_CONTINUE_EDITING_SWIPE_Y = 151
TIKTOK_CONTINUE_EDITING_SWIPE_DISTANCE = 200

TIKTOK_GET_NOTIFIED_BUTTON_LABELS = (
    "get notified",
    "get notified!",
)

# Apple Passkeys sheet: "Passkeys require a passcode and work best with Touch ID" → tap X.
IOS_PASSKEYS_PASSCODE_DISMISS_X = 563
IOS_PASSKEYS_PASSCODE_DISMISS_Y = 592

IOS_PASSKEYS_PASSCODE_KEYWORDS = (
    "passkeys require a passcode",
    "require a passcode and work best with touch id",
    "work best with touch id",
)

# TikTok: "Viewer history turned on" sheet → tap white-text Save button.
TIKTOK_VIEWER_HISTORY_KEYWORDS = (
    "viewer history turned on",
    "viewer history is turned on",
    "view history turned on",
)

TIKTOK_VIEWER_HISTORY_SAVE_TEXTS = [
    "Save",
    "SAVE",
]

# TikTok: "Your avatar, your style" promo sheet → tap upper-top dismiss (X / close).
TIKTOK_AVATAR_STYLE_DISMISS_X = 563
TIKTOK_AVATAR_STYLE_DISMISS_Y = 92

TIKTOK_AVATAR_STYLE_KEYWORDS = (
    "your avatar, your style",
    "your avatar your style",
)

# TikTok: "Virtual Items and Rewards Policies update" → tap Got it.
TIKTOK_VIRTUAL_ITEMS_POLICIES_KEYWORDS = (
    "virtual items and rewards policies update",
    "virtual items and rewards policies",
    "rewards policies update",
)

TIKTOK_GOT_IT_BUTTON_TEXTS = [
    "Got it",
    "GOT IT",
    "Got It",
]

# Tap these on TikTok in-app permission modals (contacts, etc.) — not iOS system sheets.
TIKTOK_DONT_ALLOW_BUTTON_TEXTS = [
    "Don't allow",
    "Don't Allow",
    "DONT ALLOW",
    "Dont allow",
]

# TikTok in-app sheets that offer "Don't allow" (OCR may glue words together).
TIKTOK_IN_APP_DENY_KEYWORDS = (
    "find contacts",
    "access to your contacts",
    "allow access to your contacts",
    "tiktok contacts",
    "connect with people you know",
    "sync your contacts",
    "find facebook friends",
)

# iOS permission dialogs we should auto-allow (camera, mic, photos).
ALLOW_RESOURCE_KEYWORDS = (
    "camera",
    "microphone",
    "micro phone",
    "photos",
    "photo library",
    "photo lib",
    "media library",
    "your photo",
    "add photos",
)

# Signals that a system permission sheet is on screen.
PERMISSION_DIALOG_KEYWORDS = (
    "would like to",
    "would like access",
    "like to access",
    "wants to access",
    "allow tiktok",
    "track your activity",
    "access your",
)

NEGATIVE_BUTTON_WORDS = ("don't", "dont", "not to track", "ask app")


def _has_deny_permission_button(ocr_text: str) -> bool:
    compact = ocr_compact(ocr_text)
    return (
        "dontallow" in compact
        or "askapnottotrack" in compact
        or "don't allow" in str(ocr_text or "").lower()
        or "dont allow" in str(ocr_text or "").lower()
        or "ask app not to track" in str(ocr_text or "").lower()
    )


def is_negated_delete_label(text: str) -> bool:
    """True for Don't Delete / Do Not Delete style labels."""
    label = str(text or "").strip().lower()
    return bool(re.search(r"(don't|dont|do not|never|not)\s*delet", label))


def is_deny_permission_label(text: str) -> bool:
    """True for Don't Allow / Ask App Not to Track — not photo delete cancel buttons."""
    label = str(text or "").strip().lower()
    if not label or is_negated_delete_label(text):
        return False
    if "delet" in label:
        return False
    compact = ocr_compact(label)
    if compact in ("dontallow", "askapnottotrack"):
        return True
    if "allow" in label or "track" in label:
        return any(neg in label for neg in NEGATIVE_BUTTON_WORDS)
    return label in ("ask app not to track", "don't allow", "dont allow")


def is_photo_delete_sheet_text(ocr_text: str) -> bool:
    """True when OCR looks like the iOS Photos delete confirmation sheet."""
    text = ocr_text.lower()
    if "delet" not in text:
        return False
    return any(
        phrase in text
        for phrase in (
            "delete photo",
            "delete photos",
            "to delete",
            "delete items",
            "delete item",
            "delete always",
            "delete all",
            "delete everything",
            "from library",
            "don't delete",
            "dont delete",
        )
    )


def is_delete_confirm_label(text: str) -> bool:
    """True when OCR text is the destructive delete button, not e.g. 'Show All'."""
    label = str(text or "").strip().lower()
    if "delet" not in label:
        return False
    if is_negated_delete_label(text):
        return False
    blocked = (
        "show all",
        "see all",
        "view all",
        "select",
        "keep",
        "cancel",
        "not now",
    )
    return not any(b in label for b in blocked)


def delete_label_priority(text: str) -> int:
    """Higher rank = more specific destructive delete label."""
    if is_delete_all_with_count(text):
        return 10
    if is_delete_everything_label(text):
        return 9
    label = str(text or "").strip().lower()
    if not is_delete_confirm_label(text):
        return 0
    best = 0
    for needle, rank in DELETE_LABEL_PRIORITY:
        if needle in label:
            best = max(best, rank)
    return best


def is_delete_all_with_count(text: str) -> bool:
    return bool(DELETE_ALL_COUNT_RE.search(str(text or "")))


def is_delete_everything_label(text: str) -> bool:
    return bool(DELETE_EVERYTHING_RE.search(str(text or "")))


def is_final_bulk_delete_label(text: str) -> bool:
    """True for one-shot bulk delete buttons — no second confirm expected."""
    if not is_delete_confirm_label(text):
        return False
    label = str(text or "").strip().lower()
    return (
        is_delete_everything_label(text)
        or is_delete_all_with_count(text)
        or label == "delete all"
        or label.startswith("delete all photos")
        or label == "delete always"
    )


def sheet_text_has_bulk_delete_option(matches: list[dict]) -> bool:
    joined = _joined_match_text(matches)
    return bool(
        DELETE_EVERYTHING_RE.search(joined)
        or DELETE_ALL_COUNT_RE.search(joined)
        or re.search(r"delete\s+all\s+photos", joined)
    )


def is_bare_delete_label(text: str) -> bool:
    label = str(text or "").strip().lower()
    return label == "delete"


def enrich_delete_sheet_matches(matches: list[dict]) -> list[dict]:
    """Merge split OCR (e.g. ``Delete All`` + ``(20)``) into one bulk button."""
    enriched = list(matches)
    delete_all_rows = [
        m
        for m in matches
        if re.search(r"delete\s+all", str(m.get("text", "")), re.IGNORECASE)
        and not is_delete_all_with_count(str(m.get("text", "")))
    ]
    count_rows = [
        m
        for m in matches
        if re.search(r"[\(\[]?\s*\d+\s*[\)\]]?", str(m.get("text", "")))
    ]
    for row in delete_all_rows:
        row_y = int(row.get("y", 0))
        for count_row in count_rows:
            if abs(row_y - int(count_row.get("y", 0))) > 45:
                continue
            count = re.search(r"\d+", str(count_row.get("text", "")))
            if not count:
                continue
            enriched.append(
                {
                    **row,
                    "text": f"Delete All ({count.group()})",
                    "confidence": max(
                        float(row.get("confidence", 0)),
                        float(count_row.get("confidence", 0)),
                    )
                    + 0.05,
                }
            )
            break
    return enriched


def is_bulk_delete_label(text: str) -> bool:
    label = str(text or "").strip().lower()
    if not is_delete_confirm_label(text):
        return False
    if is_delete_all_with_count(text) or is_delete_everything_label(text):
        return True
    return any(phrase in label for phrase in BULK_DELETE_PHRASES)


def delete_sheet_title_phrases() -> tuple[str, ...]:
    return (
        "from library",
        "delete photo",
        "delete photos",
        "delete items",
        "delete item",
        "delete always",
        "delete all",
        "delete everything",
        "will be deleted",
        "this photo will",
    )


def delete_sheet_body_phrases() -> tuple[str, ...]:
    """Sheet body copy — not button labels (avoids Show All ↔ Delete All OCR false positives)."""
    return (
        "from library",
        "will be deleted",
        "this photo will",
        "remove from",
    )


def delete_sheet_has_body_copy(matches: list[dict]) -> bool:
    """True when OCR includes sheet body text above the action buttons."""
    body_min_y = DELETE_SHEET_SIGNAL_MIN_Y - 80
    for match in matches:
        text = str(match.get("text", "")).lower()
        if int(match.get("y", 0)) >= body_min_y:
            continue
        if any(phrase in text for phrase in delete_sheet_body_phrases()):
            return True
    joined = _joined_match_text(matches)
    return any(phrase in joined for phrase in delete_sheet_body_phrases())


def _joined_match_text(matches: list[dict]) -> str:
    return " ".join(str(m.get("text", "")) for m in matches).lower()


def delete_sheet_is_visible(
    matches: list[dict],
    *,
    min_y: int = DELETE_SHEET_SIGNAL_MIN_Y,
) -> bool:
    """True when the iOS delete confirmation sheet appears to be on screen."""
    if not matches:
        return False
    if any(is_negated_delete_label(str(m.get("text", ""))) for m in matches):
        return True
    bottom_deletes = [
        m
        for m in matches
        if is_delete_confirm_label(str(m.get("text", "")))
        and not is_delete_distractor_label(str(m.get("text", "")))
        and int(m.get("y", 0)) >= min_y
    ]
    if not bottom_deletes:
        return False
    if delete_sheet_has_body_copy(matches):
        return True
    if sheet_text_has_bulk_delete_option(matches):
        return True
    return any(
        is_bulk_delete_label(str(m.get("text", "")))
        and not is_bare_delete_label(str(m.get("text", "")))
        for m in bottom_deletes
    )


def is_delete_distractor_label(text: str) -> bool:
    """True for sheet labels like Show All that sit near the delete button."""
    label = str(text or "").strip().lower()
    if not label:
        return True
    if re.search(r"show\s*all", label):
        return True
    if "delet" in label and is_delete_confirm_label(text):
        return False
    return any(sub in label for sub in DELETE_DISTRACTOR_SUBSTRINGS)


def filter_delete_confirm_matches(
    matches: list[dict],
    *,
    min_y: int = DELETE_SHEET_MIN_Y,
) -> list[dict]:
    """Keep only bottom-sheet delete buttons, excluding Show All and similar."""
    filtered: list[dict] = []
    for match in matches:
        text = str(match.get("text", ""))
        if not is_delete_confirm_label(text):
            continue
        if is_delete_distractor_label(text):
            continue
        if int(match.get("y", 0)) < min_y:
            continue
        filtered.append(match)
    return filtered


def pick_delete_confirm_match(
    matches: list[dict],
    *,
    min_y: int = DELETE_SHEET_MIN_Y,
) -> dict | None:
    """Pick the best delete button from OCR matches, or None if unsafe."""
    matches = enrich_delete_sheet_matches(matches)
    candidates = filter_delete_confirm_matches(matches, min_y=min_y)
    if not candidates:
        return None

    dont_delete_rows = [
        m for m in matches if is_negated_delete_label(str(m.get("text", "")))
    ]
    distractor_rows = [
        m for m in matches if is_delete_distractor_label(str(m.get("text", "")))
    ]
    if dont_delete_rows or distractor_rows:
        floor_y = 0
        if dont_delete_rows:
            floor_y = max(int(m.get("y", 0)) for m in dont_delete_rows)
        if distractor_rows:
            floor_y = max(
                floor_y,
                max(int(m.get("y", 0)) for m in distractor_rows),
            )
        below_floor = [
            m for m in candidates if int(m.get("y", 0)) > floor_y + 15
        ]
        if below_floor:
            candidates = below_floor

    if sheet_text_has_bulk_delete_option(matches) or any(
        is_bulk_delete_label(str(m.get("text", ""))) for m in candidates
    ):
        bulk_only = [
            m
            for m in candidates
            if is_bulk_delete_label(str(m.get("text", "")))
            and not is_bare_delete_label(str(m.get("text", "")))
        ]
        if bulk_only:
            candidates = bulk_only
        else:
            without_bare = [
                m for m in candidates if not is_bare_delete_label(str(m.get("text", "")))
            ]
            if without_bare:
                candidates = without_bare
    return max(
        candidates,
        key=lambda m: (
            delete_label_priority(str(m.get("text", ""))),
            len(str(m.get("text", ""))),
            int(m.get("y", 0)),
            float(m.get("confidence", 0)),
        ),
    )


def delete_confirmation_sheet_present(matches: list[dict]) -> bool:
    """True when the iOS delete confirmation sheet is up (not Recents / Show All)."""
    return any(is_negated_delete_label(str(m.get("text", ""))) for m in matches)


def delete_tap_ready_in_one_scan(matches: list[dict]) -> bool:
    """True when cancel + delete buttons are both visible — safe to tap without waiting."""
    if not delete_confirmation_sheet_present(matches):
        return False
    return resolve_delete_tap(matches, min_y=DELETE_SHEET_RELAXED_MIN_Y) is not None


def resolve_delete_tap(
    matches: list[dict],
    *,
    min_y: int = DELETE_SHEET_MIN_Y,
    relaxed_min_y: int = DELETE_SHEET_RELAXED_MIN_Y,
) -> dict | None:
    """Return an on-screen delete button OCR match, or None if not found safely."""
    matches = enrich_delete_sheet_matches(matches)
    if not delete_sheet_is_visible(matches):
        return None
    picked = pick_delete_confirm_match(matches, min_y=min_y)
    if picked:
        return picked
    return pick_delete_confirm_match(matches, min_y=relaxed_min_y)


def delete_match_is_stable(first: dict, second: dict, *, tolerance: int = 45) -> bool:
    """True when two scans found the same delete button location."""
    return (
        abs(int(first.get("x", 0)) - int(second.get("x", 0))) <= tolerance
        and abs(int(first.get("y", 0)) - int(second.get("y", 0))) <= tolerance
    )


def is_permission_dialog_text(ocr_text: str) -> bool:
    """True when on-screen OCR looks like an iOS permission alert."""
    text = ocr_text.lower()
    has_buttons = "allow" in text and _has_deny_permission_button(ocr_text)
    has_dialog_phrase = any(
        ocr_contains_phrase(ocr_text, kw) for kw in PERMISSION_DIALOG_KEYWORDS
    )
    return has_buttons or has_dialog_phrase


def is_tiktok_in_app_deny_dialog(ocr_text: str) -> bool:
    """True for TikTok in-app modals with Don't allow (contacts, sync friends, etc.)."""
    if not any(ocr_contains_phrase(ocr_text, kw) for kw in TIKTOK_IN_APP_DENY_KEYWORDS):
        return False
    return _has_deny_permission_button(ocr_text)


def tiktok_dont_allow_button_texts() -> list[str]:
    """Button labels for TikTok in-app Don't allow prompts."""
    return list(TIKTOK_DONT_ALLOW_BUTTON_TEXTS)


def find_contacts_search_texts() -> list[str]:
    """OCR queries to spot the find-contacts sheet and its Don't allow button in one scan."""
    seen: set[str] = set()
    out: list[str] = []
    for label in (*TIKTOK_IN_APP_DENY_KEYWORDS, *TIKTOK_DONT_ALLOW_BUTTON_TEXTS):
        key = label.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(label)
    return out


def is_find_contacts_context_label(text: str) -> bool:
    """True when an OCR line is find-contacts sheet body copy (not the button)."""
    label = str(text or "").lower()
    if not label:
        return False
    compact = ocr_compact(label)
    for keyword in TIKTOK_IN_APP_DENY_KEYWORDS:
        if keyword in label or ocr_compact(keyword) in compact:
            return True
    return False


def should_allow_permission(ocr_text: str) -> bool:
    """Allow only camera, microphone, and photo-library permission requests."""
    text = ocr_text.lower()
    return any(kw in text for kw in ALLOW_RESOURCE_KEYWORDS)


def button_texts_for_permission(allow: bool) -> list[str]:
    """OCR button labels to search for, in tap priority order."""
    return list(UPLOAD_PERMISSION_TEXTS) if allow else list(DENY_BUTTON_TEXTS)


def is_tiktok_email_confirm_dialog(ocr_text: str) -> bool:
    """True when on-screen OCR looks like TikTok's confirm-use-of-email sheet."""
    text = ocr_text.lower()
    return any(kw in text for kw in TIKTOK_EMAIL_CONFIRM_KEYWORDS)


def is_tiktok_save_login_dialog(ocr_text: str) -> bool:
    """True when on-screen OCR looks like TikTok's save-login-for-next-time sheet."""
    text = ocr_text.lower()
    if any(kw in text for kw in TIKTOK_SAVE_LOGIN_KEYWORDS):
        return True
    compact = ocr_compact(text)
    return "savelogin" in compact and "nexttime" in compact


def is_tiktok_post_notify_dialog(ocr_text: str) -> bool:
    """True when TikTok shows a get-notified prompt (any casing)."""
    text = str(ocr_text or "").lower()
    if "get notified" in text:
        return True
    return any(kw in text for kw in TIKTOK_POST_NOTIFY_KEYWORDS)


def tiktok_post_notify_dismiss_coords() -> tuple[int, int]:
    return TIKTOK_POST_NOTIFY_DISMISS_X, TIKTOK_POST_NOTIFY_DISMISS_Y


def is_ios_passkeys_passcode_dialog(ocr_text: str) -> bool:
    """True when Apple shows the Passkeys require a passcode / Touch ID sheet."""
    text = str(ocr_text or "").lower()
    if any(kw in text for kw in IOS_PASSKEYS_PASSCODE_KEYWORDS):
        return True
    if "passkey" in text and "passcode" in text:
        return True
    if "passkey" in text and "touch id" in text:
        return True
    return False


def ios_passkeys_passcode_dismiss_coords() -> tuple[int, int]:
    return IOS_PASSKEYS_PASSCODE_DISMISS_X, IOS_PASSKEYS_PASSCODE_DISMISS_Y


def is_tiktok_viewer_history_dialog(ocr_text: str) -> bool:
    """True when TikTok shows the viewer history turned on sheet."""
    text = str(ocr_text or "").lower()
    if "viewer history" in text and "turned on" in text:
        return True
    return any(kw in text for kw in TIKTOK_VIEWER_HISTORY_KEYWORDS)


def tiktok_viewer_history_save_button_texts() -> list[str]:
    return list(TIKTOK_VIEWER_HISTORY_SAVE_TEXTS)


def is_save_button_label(text: str) -> bool:
    """Exact Save CTA — not Save draft / autosave snippets."""
    return str(text or "").strip().lower() == "save"


def is_tiktok_avatar_style_dialog(ocr_text: str) -> bool:
    """True when TikTok shows the avatar / style promo sheet."""
    text = ocr_compact(str(ocr_text or ""))
    if "youravatar" in text and "yourstyle" in text:
        return True
    lowered = str(ocr_text or "").lower()
    return any(kw in lowered for kw in TIKTOK_AVATAR_STYLE_KEYWORDS)


def tiktok_avatar_style_dismiss_coords() -> tuple[int, int]:
    return TIKTOK_AVATAR_STYLE_DISMISS_X, TIKTOK_AVATAR_STYLE_DISMISS_Y


def is_tiktok_virtual_items_policies_dialog(ocr_text: str) -> bool:
    """True when TikTok shows the Virtual Items and Rewards Policies update sheet."""
    compact = ocr_compact(str(ocr_text or ""))
    if "virtualitems" in compact and "policies" in compact:
        return True
    lowered = str(ocr_text or "").lower()
    return any(kw in lowered for kw in TIKTOK_VIRTUAL_ITEMS_POLICIES_KEYWORDS)


def tiktok_got_it_button_texts() -> list[str]:
    return list(TIKTOK_GOT_IT_BUTTON_TEXTS)


def is_got_it_label(text: str) -> bool:
    """True when OCR text is a Got it button."""
    label = str(text or "").strip().lower()
    return label in ("got it", "gotit") or ocr_compact(label) == "gotit"


def is_tiktok_continue_editing_dialog(ocr_text: str) -> bool:
    """True when TikTok shows 'Continue editing this post?' draft recovery sheet."""
    text = str(ocr_text or "").lower()
    if any(kw in text for kw in TIKTOK_CONTINUE_EDITING_KEYWORDS):
        return True
    return "continue editing" in text and "post" in text


def tiktok_continue_editing_swipe_coords() -> tuple[int, int, int, int]:
    """Swipe up from (x, y) to dismiss continue-editing sheet."""
    x = TIKTOK_CONTINUE_EDITING_SWIPE_X
    y = TIKTOK_CONTINUE_EDITING_SWIPE_Y
    ey = max(0, y - TIKTOK_CONTINUE_EDITING_SWIPE_DISTANCE)
    return x, y, x, ey


def is_tiktok_live_feed_dialog(ocr_text: str) -> bool:
    """True when the feed shows a LIVE stream overlay to skip."""
    text = str(ocr_text or "").lower()
    if "live now" in text:
        return True
    if "tap to watch live" in text:
        return True
    compact = ocr_compact(text)
    return "livenow" in compact or "taptowatchlive" in compact


def tiktok_not_now_button_texts() -> list[str]:
    """Button labels to tap when dismissing TikTok optional prompts."""
    return list(TIKTOK_NOT_NOW_BUTTON_TEXTS)


def is_not_now_label(text: str) -> bool:
    """True when OCR text is a Not Now button (not e.g. Update Not Now elsewhere)."""
    label = str(text or "").strip().lower()
    return label in ("not now", "notnow") or label.endswith(" not now")


def known_popup_watcher_button_labels() -> list[str]:
    """OCR button labels the permission watcher may tap for TikTok / iOS popups."""
    seen: set[str] = set()
    out: list[str] = []
    for label in (
        *TIKTOK_NOT_NOW_BUTTON_TEXTS,
        *TIKTOK_DONT_ALLOW_BUTTON_TEXTS,
        *TIKTOK_VIEWER_HISTORY_SAVE_TEXTS,
        *TIKTOK_GOT_IT_BUTTON_TEXTS,
        *UPLOAD_PERMISSION_TEXTS,
        *DENY_BUTTON_TEXTS,
    ):
        key = label.strip().lower()
        if key not in seen:
            seen.add(key)
            out.append(label)
    return out


def analyze_popup_screen(ocr_text: str) -> dict[str, Any]:
    """Classify on-screen OCR the same way PermissionWatcher does (detect only)."""
    text = ocr_text or ""
    snippet = text[:400] + ("…" if len(text) > 400 else "")

    if is_photo_delete_sheet_text(text):
        return {
            "dialog": "photo_delete_sheet",
            "watcher_action": "skip",
            "watcher_detail": "Photo delete sheet — permission watcher ignores this.",
            "button_labels": [],
            "ocr_snippet": snippet,
        }

    if is_tiktok_email_confirm_dialog(text):
        return {
            "dialog": "tiktok_email_confirm",
            "watcher_action": "tap_not_now",
            "watcher_detail": "Tap Not Now on TikTok email confirm sheet.",
            "button_labels": tiktok_not_now_button_texts(),
            "ocr_snippet": snippet,
        }

    if is_tiktok_save_login_dialog(text):
        return {
            "dialog": "tiktok_save_login",
            "watcher_action": "tap_not_now",
            "watcher_detail": "Tap Not now on Save login for next time sheet.",
            "button_labels": tiktok_not_now_button_texts(),
            "ocr_snippet": snippet,
        }

    if is_tiktok_continue_editing_dialog(text):
        sx, sy, ex, ey = tiktok_continue_editing_swipe_coords()
        return {
            "dialog": "tiktok_continue_editing",
            "watcher_action": "swipe_up",
            "watcher_detail": f"Swipe up from ({sx}, {sy}) to dismiss draft sheet.",
            "button_labels": [],
            "swipe_sx": sx,
            "swipe_sy": sy,
            "swipe_ex": ex,
            "swipe_ey": ey,
            "ocr_snippet": snippet,
        }

    if is_tiktok_live_feed_dialog(text):
        return {
            "dialog": "tiktok_live_feed",
            "watcher_action": "swipe_up_random",
            "watcher_detail": "Swipe up to skip LIVE now / Tap to watch LIVE.",
            "button_labels": [],
            "ocr_snippet": snippet,
        }

    if is_tiktok_post_notify_dialog(text):
        x, y = tiktok_post_notify_dismiss_coords()
        return {
            "dialog": "tiktok_post_notify",
            "watcher_action": "tap_coord",
            "watcher_detail": f"Tap dismiss at ({x}, {y}) — no button OCR.",
            "button_labels": [],
            "tap_x": x,
            "tap_y": y,
            "ocr_snippet": snippet,
        }

    if is_ios_passkeys_passcode_dialog(text):
        x, y = ios_passkeys_passcode_dismiss_coords()
        return {
            "dialog": "ios_passkeys_passcode",
            "watcher_action": "tap_coord",
            "watcher_detail": f"Tap dismiss at ({x}, {y}) on Passkeys passcode sheet.",
            "button_labels": [],
            "tap_x": x,
            "tap_y": y,
            "ocr_snippet": snippet,
        }

    if is_tiktok_viewer_history_dialog(text):
        return {
            "dialog": "tiktok_viewer_history",
            "watcher_action": "tap_save_white",
            "watcher_detail": "Tap Save (white text) on viewer history sheet.",
            "button_labels": tiktok_viewer_history_save_button_texts(),
            "ocr_snippet": snippet,
        }

    if is_tiktok_avatar_style_dialog(text):
        x, y = tiktok_avatar_style_dismiss_coords()
        return {
            "dialog": "tiktok_avatar_style",
            "watcher_action": "tap_coord",
            "watcher_detail": f"Tap dismiss at ({x}, {y}) on avatar/style sheet.",
            "button_labels": [],
            "tap_x": x,
            "tap_y": y,
            "ocr_snippet": snippet,
        }

    if is_tiktok_virtual_items_policies_dialog(text):
        return {
            "dialog": "tiktok_virtual_items_policies",
            "watcher_action": "tap_got_it",
            "watcher_detail": "Tap Got it on Virtual Items and Rewards Policies update.",
            "button_labels": tiktok_got_it_button_texts(),
            "ocr_snippet": snippet,
        }

    if is_tiktok_in_app_deny_dialog(text):
        return {
            "dialog": "tiktok_in_app_deny",
            "watcher_action": "tap_dont_allow",
            "watcher_detail": "Tap Don't allow on TikTok in-app permission sheet (e.g. contacts).",
            "button_labels": tiktok_dont_allow_button_texts(),
            "ocr_snippet": snippet,
        }

    if is_permission_dialog_text(text):
        allow = should_allow_permission(text)
        labels = button_texts_for_permission(allow)
        action = "tap_allow" if allow else "tap_deny"
        detail = (
            "Tap Allow / photos permission labels."
            if allow
            else "Tap Don't Allow / Ask App Not to Track."
        )
        return {
            "dialog": "ios_permission",
            "watcher_action": action,
            "watcher_detail": detail,
            "button_labels": labels,
            "allow_resource": allow,
            "ocr_snippet": snippet,
        }

    return {
        "dialog": "none",
        "watcher_action": "none",
        "watcher_detail": "No known TikTok popup or iOS permission dialog detected.",
        "button_labels": [],
        "ocr_snippet": snippet,
    }
