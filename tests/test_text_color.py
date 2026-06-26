"""Tests for OCR text darkness sampling."""

from __future__ import annotations

import cv2
import numpy as np

from imouse_farm.vision.text_color import is_text_dark_enough, sample_text_luminance


def _text_patch(color: int) -> np.ndarray:
    image = np.full((720, 406, 3), 255, dtype=np.uint8)
    cv2.putText(image, "Next", (300, 650), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (color, color, color), 2)
    return image


def test_black_text_is_dark_enough() -> None:
    image = _text_patch(20)
    assert is_text_dark_enough(image, 320, 650, max_luminance=110)


def test_grey_text_is_not_dark_enough() -> None:
    image = _text_patch(170)
    assert not is_text_dark_enough(image, 320, 650, max_luminance=110)


def test_grey_is_lighter_than_black() -> None:
    black = sample_text_luminance(_text_patch(20), 320, 650)
    grey = sample_text_luminance(_text_patch(170), 320, 650)
    assert black < grey
