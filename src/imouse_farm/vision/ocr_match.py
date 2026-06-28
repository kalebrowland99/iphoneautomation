"""Compact OCR text matching — tolerates glued words from mirrored phone OCR."""

from __future__ import annotations

import re
from typing import Any


def ocr_compact(text: str) -> str:
    """Lowercase alphanumeric only (e.g. ``Don't allow`` → ``dontallow``)."""
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def ocr_contains_phrase(ocr_text: str, phrase: str) -> bool:
    """True when ``phrase`` appears in ``ocr_text``, ignoring spaces/punctuation."""
    needle = ocr_compact(phrase)
    return bool(needle) and needle in ocr_compact(ocr_text)


def ocr_text_matches_query(
    haystack: str,
    query: str,
    *,
    contain: bool = True,
) -> bool:
    """Match on-device OCR text to a search label.

  Short single-word queries (``Done``, ``Allow``) require exact compact equality so
  ``allow`` does not match inside ``dontallow``. Longer or multi-word phrases use
  compact substring matching for glued OCR blobs.
    """
    compact_hay = ocr_compact(haystack)
    compact_query = ocr_compact(query)
    if not compact_query or not compact_hay:
        return False
    if compact_hay == compact_query:
        return True
    if not contain:
        return False
    raw = str(query or "").strip()
    is_phrase = len(raw) > 1 and (
        len(compact_query) >= 6
        or " " in raw
        or "'" in raw
        or "." in raw
    )
    return is_phrase and compact_query in compact_hay


def filter_matches_for_queries(
    matches: list[dict[str, Any]],
    queries: list[str],
    *,
    contain: bool = True,
) -> list[dict[str, Any]]:
    """Keep SDK OCR hits that compact-match at least one query."""
    if not matches or not queries:
        return []
    out: list[dict[str, Any]] = []
    for match in matches:
        text = str(match.get("text", ""))
        if any(ocr_text_matches_query(text, q, contain=contain) for q in queries):
            out.append(match)
    return out


def match_ocr_items_to_queries(
    items: list[dict[str, Any]],
    queries: list[str],
    *,
    contain: bool = True,
) -> list[dict[str, Any]]:
    """Find OCR line items matching any query via compact rules."""
    if not items or not queries:
        return []
    hits: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for item in items:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        if not any(ocr_text_matches_query(text, q, contain=contain) for q in queries):
            continue
        x, y = int(item.get("x", 0)), int(item.get("y", 0))
        key = (ocr_compact(text), x, y)
        if key in seen:
            continue
        seen.add(key)
        hits.append(item)
    return hits
