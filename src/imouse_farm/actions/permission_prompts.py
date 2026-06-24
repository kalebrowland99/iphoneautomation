"""iOS permission dialog handling for TikTok and system alerts."""

from __future__ import annotations

# Prefer specific labels first (e.g. "Always Allow" before bare "Allow").
UPLOAD_PERMISSION_TEXTS = [
    "Always Allow",
    "Allow Full Access",
    "Allow Access to All Photos",
    "Allow Paste",
    "Allow",
]

DELETE_CONFIRM_TEXTS = [
    "Delete Items",
    "Delete Photos",
    "Delete Photo",
    "Delete",
]

# Delete confirm sits in the bottom action sheet on typical iPhone layouts.
DELETE_SHEET_MIN_Y = 580

# Labels that must never be tapped during album clear.
DELETE_DISTRACTOR_SUBSTRINGS = (
    "show all",
    "see all",
    "view all",
    "show",
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


def is_delete_confirm_label(text: str) -> bool:
    """True when OCR text is the destructive delete button, not e.g. 'Show All'."""
    label = str(text or "").strip().lower()
    if "delet" not in label:
        return False
    blocked = (
        "show all",
        "see all",
        "view all",
        "select",
        "keep",
        "cancel",
        "don't delete",
        "dont delete",
        "not now",
    )
    return not any(b in label for b in blocked)


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
    candidates = filter_delete_confirm_matches(matches, min_y=min_y)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda m: (
            len(str(m.get("text", ""))),
            int(m.get("y", 0)),
            float(m.get("confidence", 0)),
        ),
    )


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
