"""Stub for future local vision model provider (v2)."""

from __future__ import annotations

from typing import Any

from imouse_farm.config.models import DeviceState
from imouse_farm.utils.logging import get_logger
from imouse_farm.vision.base import VisionAnalysis, VisionProvider
from imouse_farm.vision.opencv_provider import OpenCVVisionProvider

logger = get_logger(__name__)


class LocalModelVisionProvider(VisionProvider):
    """Version 2 placeholder — delegates to OpenCV until a model is configured."""

    def __init__(self, fallback: OpenCVVisionProvider, model_path: str = "") -> None:
        self._fallback = fallback
        self._model_path = model_path

    @property
    def name(self) -> str:
        return "local_model"

    def analyze(
        self,
        device_id: str,
        screenshot_path: str,
        *,
        template_names: list[str] | None = None,
        ocr_regions: list[dict[str, Any]] | None = None,
        ocr_keywords: list[str] | None = None,
        popup_definitions: dict[str, Any] | None = None,
    ) -> VisionAnalysis:
        # TODO: integrate local vision model when model_path is set
        if self._model_path:
            logger.info("local_model_not_implemented", model_path=self._model_path)
        result = self._fallback.analyze(
            device_id, screenshot_path,
            template_names=template_names,
            ocr_regions=ocr_regions,
            ocr_keywords=ocr_keywords,
            popup_definitions=popup_definitions,
        )
        result.provider = self.name
        return result
