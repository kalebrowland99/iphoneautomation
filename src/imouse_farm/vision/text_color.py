"""Sample on-screen text darkness from OCR match regions."""

from __future__ import annotations

import cv2
import numpy as np


def decode_screenshot(image_bytes: bytes) -> np.ndarray | None:
    if not image_bytes:
        return None
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def sample_text_luminance(
    image: np.ndarray,
    x: int,
    y: int,
    *,
    rect: list[int] | None = None,
) -> float:
    """Return 0–255 luminance; lower values mean darker (black) text."""
    h, w = image.shape[:2]
    if rect and len(rect) == 4:
        x1, y1, x2, y2 = (int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))
        x1, x2 = max(0, min(x1, x2)), min(w, max(x1, x2))
        y1, y2 = max(0, min(y1, y2)), min(h, max(y1, y2))
    else:
        half_w, half_h = 25, 12
        x1, y1 = max(0, x - half_w), max(0, y - half_h)
        x2, y2 = min(w, x + half_w), min(h, y + half_h)
    patch = image[y1:y2, x1:x2]
    if patch.size == 0:
        return 255.0
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    return float(np.percentile(gray, 15))


def is_text_dark_enough(
    image: np.ndarray,
    x: int,
    y: int,
    *,
    rect: list[int] | None = None,
    max_luminance: float = 110.0,
) -> bool:
    """True when sampled text is dark (enabled black), not light grey."""
    return sample_text_luminance(image, x, y, rect=rect) <= max_luminance


def sample_bright_text_luminance(
    image: np.ndarray,
    x: int,
    y: int,
    *,
    rect: list[int] | None = None,
) -> float:
    """Return 0–255 luminance of bright pixels (e.g. white label on a colored button)."""
    h, w = image.shape[:2]
    if rect and len(rect) == 4:
        x1, y1, x2, y2 = (int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))
        x1, x2 = max(0, min(x1, x2)), min(w, max(x1, x2))
        y1, y2 = max(0, min(y1, y2)), min(h, max(y1, y2))
    else:
        half_w, half_h = 25, 12
        x1, y1 = max(0, x - half_w), max(0, y - half_h)
        x2, y2 = min(w, x + half_w), min(h, y + half_h)
    patch = image[y1:y2, x1:x2]
    if patch.size == 0:
        return 0.0
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    return float(np.percentile(gray, 85))


def is_text_light_enough(
    image: np.ndarray,
    x: int,
    y: int,
    *,
    rect: list[int] | None = None,
    min_luminance: float = 175.0,
) -> bool:
    """True when sampled text is bright (e.g. white Save on a primary button)."""
    return sample_bright_text_luminance(image, x, y, rect=rect) >= min_luminance
