"""Tests for OCR skip-if detection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.vision.ocr_skip import (
    phrase_in_ocr_items,
    should_skip_tap_ocr,
    story_button_visible_in_items,
)


def test_story_button_visible_bottom_left_story() -> None:
    items = [{"text": "Story", "x": 80, "y": 650}]
    assert story_button_visible_in_items(items)


def test_story_button_ignores_story_top_right() -> None:
    items = [{"text": "Story", "x": 350, "y": 40}]
    assert not story_button_visible_in_items(items)


def test_story_button_split_your_story() -> None:
    items = [{"text": "Your", "x": 60, "y": 640}, {"text": "Story", "x": 110, "y": 640}]
    assert story_button_visible_in_items(items)


def test_phrase_in_joined_ocr_items() -> None:
    items = [{"text": "Your Story"}, {"text": "Next"}]
    assert phrase_in_ocr_items(items, "Your Story")


def test_phrase_in_split_ocr_items() -> None:
    items = [{"text": "Your"}, {"text": "Story"}, {"text": "Next"}]
    assert phrase_in_ocr_items(items, "Your Story")


def test_phrase_not_in_ocr_items() -> None:
    items = [{"text": "Next"}]
    assert not phrase_in_ocr_items(items, "Your Story")


@pytest.mark.asyncio
async def test_should_skip_via_split_words() -> None:
    ctrl = MagicMock()
    ctrl.find_text_on_device = AsyncMock(
        side_effect=[
            [],
            [{"text": "Your", "x": 1, "y": 1, "confidence": 0.9}],
            [{"text": "Story", "x": 2, "y": 2, "confidence": 0.9}],
        ]
    )
    ctrl.ocr_items_on_device = AsyncMock(return_value=[])

    assert await should_skip_tap_ocr(
        ctrl,
        "device-1",
        {
            "skip_if_all_texts_present": ["Your", "Story"],
            "skip_if_threshold": 0.5,
        },
        default_threshold=0.65,
        default_contain=True,
        skip_rect=None,
    )


@pytest.mark.asyncio
async def test_should_skip_via_story_button_region() -> None:
    ctrl = MagicMock()
    ctrl.find_text_on_device = AsyncMock(
        side_effect=lambda _id, texts, **_kw: (
            [{"text": texts[0], "x": 90, "y": 650, "confidence": 0.8}]
            if texts[0] in {"Story", "STORY"}
            else []
        )
    )
    ctrl.ocr_items_on_device = AsyncMock(return_value=[])

    assert await should_skip_tap_ocr(
        ctrl,
        "device-1",
        {"skip_if_story_button": True, "skip_if_story_threshold": 0.4},
        default_threshold=0.65,
        default_contain=True,
        skip_rect=None,
    )


@pytest.mark.asyncio
async def test_should_skip_via_full_ocr_phrase() -> None:
    ctrl = MagicMock()
    ctrl.find_text_on_device = AsyncMock(return_value=[])
    ctrl.ocr_items_on_device = AsyncMock(
        return_value=[
            {"text": "Your"},
            {"text": "Story"},
            {"text": "Next"},
        ]
    )

    assert await should_skip_tap_ocr(
        ctrl,
        "device-1",
        {
            "skip_if_phrases": ["Your Story"],
            "skip_if_ocr_ex": True,
        },
        default_threshold=0.65,
        default_contain=True,
        skip_rect=None,
    )
