"""Vision provider protocol and shared models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from imouse_farm.config.models import DetectionResult, DeviceState
from imouse_farm.vision.ocr_match import ocr_contains_phrase


class VisionAnalysis(BaseModel):
    """Result from any vision provider."""

    device_id: str
    screenshot_path: str
    detections: list[DetectionResult] = Field(default_factory=list)
    detected_state: DeviceState | None = None
    ocr_text: str = ""
    popup_type: str | None = None
    provider: str = "unknown"


class VisionProvider(ABC):
    """Abstract vision provider — swap without changing workflow logic."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def analyze(
        self,
        device_id: str,
        screenshot_path: str,
        *,
        template_names: list[str] | None = None,
        ocr_regions: list[dict[str, Any]] | None = None,
        popup_definitions: dict[str, Any] | None = None,
    ) -> VisionAnalysis: ...

    def evaluate_state_rules(
        self, rules: list[dict[str, Any]], analysis: VisionAnalysis
    ) -> DeviceState:
        detection_names = {d.name for d in analysis.detections}
        for rule in rules:
            condition = rule.get("condition", "default")
            if condition == "template_match":
                if rule.get("template", "") in detection_names:
                    return DeviceState(rule.get("state", "UNKNOWN_SCREEN"))
            elif condition == "ocr_contains":
                if ocr_contains_phrase(analysis.ocr_text, rule.get("text", "")):
                    return DeviceState(rule.get("state", "UNKNOWN_SCREEN"))
            elif condition == "ocr_missing":
                text = rule.get("text", "")
                if text and not ocr_contains_phrase(analysis.ocr_text, text):
                    return DeviceState(rule.get("state", "UNKNOWN_SCREEN"))
            elif condition == "default":
                return DeviceState(rule.get("state", "UNKNOWN_SCREEN"))
        return DeviceState.UNKNOWN_SCREEN

    def verify_condition(
        self, condition: str, template: str | None, analysis: VisionAnalysis
    ) -> bool:
        if condition == "template_match" and template:
            return any(d.name == template for d in analysis.detections)
        if condition == "template_missing" and template:
            return not any(d.name == template for d in analysis.detections)
        if condition == "ocr_contains" and template:
            return ocr_contains_phrase(analysis.ocr_text, template)
        if condition == "ocr_missing" and template:
            return not ocr_contains_phrase(analysis.ocr_text, template)
        return False

    def find_detection(self, analysis: VisionAnalysis, name: str) -> DetectionResult | None:
        for d in analysis.detections:
            if d.name == name:
                return d
        return None
