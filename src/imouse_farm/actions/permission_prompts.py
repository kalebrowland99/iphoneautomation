"""iOS permission dialog handling for TikTok and system alerts."""

from __future__ import annotations

import re

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
# Offset below "Don't Delete" when OCR sees the sheet but not the confirm label.
DELETE_BELOW_DONT_DELETE_OFFSET_Y = 65

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

TIKTOK_NOT_NOW_BUTTON_TEXTS = [
    "Not Now",
    "NOT NOW",
    "Not now",
]

# TikTok in-app prompt: "Get notified of post interactions?" → tap dismiss coord.
TIKTOK_POST_NOTIFY_DISMISS_X = 196
TIKTOK_POST_NOTIFY_DISMISS_Y = 193

TIKTOK_POST_NOTIFY_KEYWORDS = (
    "get notified of post interactions",
    "notified of post interactions",
    "post interactions?",
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
        or re.search(r"delete\s+all(?:\s+photos)?(?:\s|$)", joined)
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
    for match in matches:
        text = str(match.get("text", ""))
        if is_delete_confirm_label(text) or is_negated_delete_label(text):
            return True
    joined = _joined_match_text(matches)
    return any(phrase in joined for phrase in delete_sheet_title_phrases())


def is_delete_distractor_label(text: str) -> bool:
    """True for sheet labels like Show All that sit near the delete button."""
    label = str(text or "").strip().lower()
    if not label:
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


def infer_delete_button_from_sheet(matches: list[dict]) -> tuple[int, int] | None:
    """Guess delete button coords when the sheet is visible but OCR missed the label."""
    negated = [
        m for m in matches if is_negated_delete_label(str(m.get("text", "")))
    ]
    if negated:
        ref = max(negated, key=lambda m: int(m.get("y", 0)))
        return (
            int(ref["x"]),
            int(ref["y"]) + DELETE_BELOW_DONT_DELETE_OFFSET_Y,
        )
    return None


def resolve_delete_tap(
    matches: list[dict],
    *,
    min_y: int = DELETE_SHEET_MIN_Y,
    relaxed_min_y: int = DELETE_SHEET_RELAXED_MIN_Y,
) -> dict | None | tuple[str, tuple[int, int]]:
    """Return an OCR delete match, a smart fallback coordinate, or None."""
    matches = enrich_delete_sheet_matches(matches)
    if not delete_sheet_is_visible(matches):
        return None
    picked = pick_delete_confirm_match(matches, min_y=min_y)
    if picked:
        return picked
    picked = pick_delete_confirm_match(matches, min_y=relaxed_min_y)
    if picked:
        return picked
    if sheet_text_has_bulk_delete_option(matches):
        return None
    inferred = infer_delete_button_from_sheet(matches)
    if inferred is not None:
        return ("fallback", inferred)
    return None


def delete_match_is_stable(first: dict, second: dict, *, tolerance: int = 45) -> bool:
    """True when two scans found the same delete button location."""
    return (
        abs(int(first.get("x", 0)) - int(second.get("x", 0))) <= tolerance
        and abs(int(first.get("y", 0)) - int(second.get("y", 0))) <= tolerance
    )


def is_permission_dialog_text(ocr_text: str) -> bool:
    """True when on-screen OCR looks like an iOS permission alert."""
    text = ocr_text.lower()
    has_buttons = "allow" in text and (
        "don't allow" in text or "dont allow" in text or "ask app not to track" in text
    )
    has_dialog_phrase = any(kw in text for kw in PERMISSION_DIALOG_KEYWORDS)
    return has_buttons or has_dialog_phrase


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


def is_tiktok_post_notify_dialog(ocr_text: str) -> bool:
    """True when TikTok asks to get notified of post interactions."""
    text = ocr_text.lower()
    return any(kw in text for kw in TIKTOK_POST_NOTIFY_KEYWORDS)


def tiktok_post_notify_dismiss_coords() -> tuple[int, int]:
    return TIKTOK_POST_NOTIFY_DISMISS_X, TIKTOK_POST_NOTIFY_DISMISS_Y


def tiktok_not_now_button_texts() -> list[str]:
    """Button labels to tap when dismissing TikTok optional prompts."""
    return list(TIKTOK_NOT_NOW_BUTTON_TEXTS)


def is_not_now_label(text: str) -> bool:
    """True when OCR text is a Not Now button (not e.g. Update Not Now elsewhere)."""
    label = str(text or "").strip().lower()
    return label in ("not now", "notnow") or label.endswith(" not now")
