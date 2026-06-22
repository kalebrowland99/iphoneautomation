"""OCR utilities using Tesseract."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
import pytesseract

from imouse_farm.config.models import DetectionResult
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


def configure_tesseract(cmd: str | None) -> None:
    """Set Tesseract executable path if provided."""
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


def extract_text(
    image: np.ndarray,
    language: str = "eng",
    regions: list[dict[str, Any]] | None = None,
) -> str:
    """Extract text from image or specific regions."""
    if image is None:
        return ""

    if not regions:
        try:
            return pytesseract.image_to_string(image, lang=language).strip()
        except Exception as exc:
            logger.warning("ocr_failed", error=str(exc))
            return ""

    texts: list[str] = []
    for region in regions:
        x = region.get("x", 0)
        y = region.get("y", 0)
        w = region.get("width", image.shape[1])
        h = region.get("height", image.shape[0])
        roi = image[y : y + h, x : x + w]
        try:
            text = pytesseract.image_to_string(roi, lang=language).strip()
            if text:
                texts.append(text)
        except Exception as exc:
            logger.warning("ocr_region_failed", region=region, error=str(exc))
    return "\n".join(texts)


def find_keywords(
    image: np.ndarray,
    keywords: list[str],
    language: str = "eng",
    min_confidence: float = 60.0,
) -> list[DetectionResult]:
    """Find OCR keywords and return detections with confidence."""
    if image is None or not keywords:
        return []

    detections: list[DetectionResult] = []
    try:
        data = pytesseract.image_to_data(
            image, lang=language, output_type=pytesseract.Output.DICT
        )
        for i, word in enumerate(data["text"]):
            if not word.strip():
                continue
            conf = float(data["conf"][i])
            if conf < min_confidence:
                continue
            for keyword in keywords:
                if keyword.lower() in word.lower():
                    detections.append(
                        DetectionResult(
                            name=keyword,
                            confidence=conf / 100.0,
                            x=data["left"][i] + data["width"][i] // 2,
                            y=data["top"][i] + data["height"][i] // 2,
                            width=data["width"][i],
                            height=data["height"][i],
                            detection_type="ocr",
                        )
                    )
    except Exception as exc:
        logger.warning("ocr_keyword_search_failed", error=str(exc))

    return detections


def preprocess_for_ocr(image: np.ndarray) -> np.ndarray:
    """Apply preprocessing to improve OCR accuracy."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
