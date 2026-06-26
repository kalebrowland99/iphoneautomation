"""Detect on-screen text that should block an optional OCR tap."""

from __future__ import annotations

from typing import Any, Protocol


class OcrSkipController(Protocol):
    async def find_text_on_device(
        self,
        device_id: str,
        texts: list[str],
        *,
        threshold: float = 0.75,
        contain: bool = True,
        rect: list[int] | None = None,
        is_ex: bool = False,
    ) -> list[dict[str, Any]]: ...

    async def ocr_items_on_device(
        self,
        device_id: str,
        *,
        is_ex: bool = False,
        rect: list[int] | None = None,
    ) -> list[dict[str, Any]]: ...


def normalize_ocr_text(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum())


def rect_from_pct(screen_width: int, screen_height: int, pct: list[float]) -> list[int]:
    return [
        int(screen_width * float(pct[0])),
        int(screen_height * float(pct[1])),
        int(screen_width * float(pct[2])),
        int(screen_height * float(pct[3])),
    ]


def story_button_visible_in_items(
    items: list[dict[str, Any]],
    *,
    screen_width: int = 406,
    screen_height: int = 720,
    left_pct: float = 0.55,
    top_pct: float = 0.58,
) -> bool:
    """True when Story / Your Story appears in the bottom-left share row."""
    x_max = int(screen_width * left_pct)
    y_min = int(screen_height * top_pct)
    region_items = [
        item
        for item in items
        if int(item.get("x", 0)) <= x_max and int(item.get("y", 0)) >= y_min
    ]
    if not region_items:
        return False
    tokens = [normalize_ocr_text(str(item.get("text", ""))) for item in region_items]
    combined = "".join(tokens)
    if "yourstory" in combined:
        return True
    if any("story" in token for token in tokens):
        return True
    has_your = any("your" in token for token in tokens)
    has_story = any("story" in token for token in tokens)
    return has_your and has_story


def phrase_in_ocr_items(items: list[dict[str, Any]], phrase: str) -> bool:
    """True when phrase appears in OCR output (joined or split across boxes)."""
    norm_phrase = normalize_ocr_text(phrase)
    if not norm_phrase:
        return False
    combined = normalize_ocr_text(
        " ".join(str(item.get("text", "")) for item in items)
    )
    if norm_phrase in combined:
        return True
    tokens = [normalize_ocr_text(str(item.get("text", ""))) for item in items]
    if "your" in norm_phrase and "story" in norm_phrase:
        has_your = any("your" in token for token in tokens)
        has_story = any("story" in token for token in tokens)
        return has_your and has_story
    return False


def _wants_story_share_skip(
    any_texts: list[str],
    phrases: list[str],
    all_texts: list[str],
    params: dict[str, Any],
) -> bool:
    if params.get("skip_if_story_button"):
        return True
    haystack = " ".join([*any_texts, *phrases, *all_texts]).lower()
    return "story" in haystack


async def _story_button_skip(
    ctrl: OcrSkipController,
    device_id: str,
    params: dict[str, Any],
    *,
    screen_width: int,
    screen_height: int,
    skip_contain: bool,
    skip_ex: bool,
) -> bool:
    story_rect_pct = params.get("skip_if_story_rect_pct") or [0.0, 0.58, 0.52, 1.0]
    story_rect = rect_from_pct(screen_width, screen_height, story_rect_pct)
    region_threshold = float(params.get("skip_if_story_threshold", 0.4))
    region_queries = ["Story", "STORY", "Your Story", "YOUR STORY", "Your story"]

    for use_ex in (True, skip_ex):
        for query in region_queries:
            matches = await ctrl.find_text_on_device(
                device_id,
                [query],
                threshold=region_threshold,
                contain=skip_contain,
                rect=story_rect,
                is_ex=use_ex,
            )
            if matches:
                return True
        items = await ctrl.ocr_items_on_device(
            device_id, is_ex=use_ex, rect=story_rect
        )
        if story_button_visible_in_items(
            items, screen_width=screen_width, screen_height=screen_height
        ):
            return True

    for use_ex in (True, skip_ex):
        items = await ctrl.ocr_items_on_device(device_id, is_ex=use_ex, rect=None)
        if story_button_visible_in_items(
            items, screen_width=screen_width, screen_height=screen_height
        ):
            return True
    return False


async def should_skip_tap_ocr(
    ctrl: OcrSkipController,
    device_id: str,
    params: dict[str, Any],
    *,
    default_threshold: float,
    default_contain: bool,
    skip_rect: list[int] | None,
    screen_width: int = 406,
    screen_height: int = 720,
) -> bool:
    """Return True when skip-if rules say we should not tap the target OCR text."""
    any_texts = [
        str(t).strip()
        for t in (params.get("skip_if_texts_present") or [])
        if str(t).strip()
    ]
    all_texts = [
        str(t).strip()
        for t in (params.get("skip_if_all_texts_present") or [])
        if str(t).strip()
    ]
    phrases = [
        str(t).strip()
        for t in (params.get("skip_if_phrases") or [])
        if str(t).strip()
    ]
    if not any_texts and not all_texts and not phrases and not params.get(
        "skip_if_story_button"
    ):
        return False

    skip_threshold = float(params.get("skip_if_threshold", default_threshold))
    skip_contain = bool(params.get("skip_if_contain", default_contain))
    skip_ex = bool(params.get("skip_if_ocr_ex", params.get("ocr_ex", False)))

    if any_texts:
        batch = await ctrl.find_text_on_device(
            device_id,
            any_texts,
            threshold=skip_threshold,
            contain=skip_contain,
            rect=skip_rect,
            is_ex=skip_ex,
        )
        if batch:
            return True
        for text in any_texts:
            matches = await ctrl.find_text_on_device(
                device_id,
                [text],
                threshold=skip_threshold,
                contain=skip_contain,
                rect=skip_rect,
                is_ex=skip_ex,
            )
            if matches:
                return True
        if not skip_ex:
            for text in any_texts:
                matches = await ctrl.find_text_on_device(
                    device_id,
                    [text],
                    threshold=skip_threshold,
                    contain=skip_contain,
                    rect=skip_rect,
                    is_ex=True,
                )
                if matches:
                    return True

    if all_texts:
        found_all = True
        for text in all_texts:
            matches = await ctrl.find_text_on_device(
                device_id,
                [text],
                threshold=skip_threshold,
                contain=skip_contain,
                rect=skip_rect,
                is_ex=skip_ex,
            )
            if not matches and not skip_ex:
                matches = await ctrl.find_text_on_device(
                    device_id,
                    [text],
                    threshold=skip_threshold,
                    contain=skip_contain,
                    rect=skip_rect,
                    is_ex=True,
                )
            if not matches:
                found_all = False
                break
        if found_all:
            return True

    phrase_targets = phrases or (["Your Story"] if any_texts else [])
    for use_ex in (skip_ex, True):
        items = await ctrl.ocr_items_on_device(device_id, is_ex=use_ex, rect=skip_rect)
        for phrase in phrase_targets:
            if phrase_in_ocr_items(items, phrase):
                return True
        if skip_ex and use_ex:
            break

    if _wants_story_share_skip(any_texts, phrases, all_texts, params):
        if await _story_button_skip(
            ctrl,
            device_id,
            params,
            screen_width=screen_width,
            screen_height=screen_height,
            skip_contain=skip_contain,
            skip_ex=skip_ex,
        ):
            return True

    return False
