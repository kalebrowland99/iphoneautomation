"""Tests for compact OCR matching."""

from imouse_farm.vision.ocr_match import (
    filter_matches_for_queries,
    match_ocr_items_to_queries,
    ocr_compact,
    ocr_contains_phrase,
    ocr_text_matches_query,
)


def test_ocr_compact_strips_punctuation() -> None:
    assert ocr_compact("Don't allow") == "dontallow"
    assert ocr_compact("Find contacts!") == "findcontacts"


def test_ocr_contains_phrase_glued_blob() -> None:
    blob = "Findcontacts Toconnect allowaccesstoyourcontacts Don'tallow"
    assert ocr_contains_phrase(blob, "Find contacts")
    assert ocr_contains_phrase(blob, "Don't allow")
    assert ocr_contains_phrase(blob, "access to your contacts")


def test_short_query_exact_only() -> None:
    assert ocr_text_matches_query("Done", "Done")
    assert not ocr_text_matches_query("Done editing", "Done")
    assert ocr_text_matches_query("Done editing", "Done", contain=True) is False


def test_allow_does_not_match_inside_dontallow() -> None:
    assert not ocr_text_matches_query("Don'tallow", "Allow", contain=True)
    assert ocr_text_matches_query("Don'tallow", "Don't allow", contain=True)


def test_phrase_query_substring() -> None:
    assert ocr_text_matches_query("Hvitserkschoice", "Hvitserk's choice", contain=True)
    assert ocr_text_matches_query("YournetworkisunstableTaptoretry", "Tap to retry", contain=True)


def test_filter_matches_for_queries() -> None:
    matches = [
        {"text": "Don'tallow", "x": 10, "y": 20, "confidence": 0.9},
        {"text": "Opensettings", "x": 30, "y": 20, "confidence": 0.8},
    ]
    filtered = filter_matches_for_queries(matches, ["Don't allow"])
    assert len(filtered) == 1
    assert filtered[0]["text"] == "Don'tallow"


def test_match_ocr_items_to_queries() -> None:
    items = [
        {"text": "Don'tallow", "x": 10, "y": 20},
        {"text": "Opensettings", "x": 30, "y": 20},
    ]
    hits = match_ocr_items_to_queries(items, ["Don't allow", "Open settings"])
    assert len(hits) == 2
