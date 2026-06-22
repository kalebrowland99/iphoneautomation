"""Screen state detection combining templates, OCR, and UI elements."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

from imouse_farm.analysis.ocr import configure_tesseract, extract_text, find_keywords, preprocess_for_ocr
from imouse_farm.analysis.template import load_image, match_all_templates, match_template
from imouse_farm.config.models import AnalysisConfig, DetectionResult, DeviceState, ScreenAnalysisResult
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


class ScreenAnalyzer:
    """Analyze screenshots for known states, buttons, and UI elements."""

    def __init__(self, config: AnalysisConfig, workflows_dir: str = "config/workflows") -> None:
        self._config = config
        self._templates_dir = Path(config.templates_directory)
        self._screen_states = self._load_screen_states(workflows_dir)
        configure_tesseract(config.tesseract_cmd)

    def _load_screen_states(self, workflows_dir: str) -> dict[str, Any]:
        path = Path(workflows_dir) / "screen_states.yaml"
        if not path.exists():
            return {}
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data

    def analyze(
        self,
        device_id: str,
        screenshot_path: str,
        template_names: list[str] | None = None,
        ocr_regions: list[dict[str, Any]] | None = None,
    ) -> ScreenAnalysisResult:
        """Run full screen analysis pipeline."""
        screen = load_image(screenshot_path)
        if screen is None:
            logger.error("screenshot_load_failed", path=screenshot_path)
            return ScreenAnalysisResult(
                device_id=device_id,
                screenshot_path=screenshot_path,
                detected_state=DeviceState.ERROR,
            )

        detections: list[DetectionResult] = []

        # Template matching
        templates = self._resolve_templates(template_names)
        detections.extend(match_all_templates(screen, templates))

        # UI element detection
        ui_elements = self._screen_states.get("ui_elements", {})
        if isinstance(ui_elements, list):
            ui_iter = [(e.get("name", ""), e) for e in ui_elements]
        elif isinstance(ui_elements, dict):
            ui_iter = [
                (element.get("name", category), element)
                for category, elements in ui_elements.items()
                for element in elements
            ]
        else:
            ui_iter = []
        for category, element in ui_iter:
            template_path = self._templates_dir / element.get("template", "")
            if template_path.exists():
                tmpl = load_image(template_path)
                if tmpl is not None:
                    result = match_template(
                        screen,
                        tmpl,
                        element.get("threshold", self._config.template_match_threshold),
                        element.get("name", category),
                    )
                    if result:
                        result.detection_type = "ui_element"
                        detections.append(result)

        # OCR
        processed = preprocess_for_ocr(screen)
        ocr_text = extract_text(
            processed,
            language=self._config.ocr_language,
            regions=ocr_regions,
        )

        # OCR keyword detection from screen states
        for state_name, state_def in self._screen_states.get("screen_states", {}).items():
            keywords = state_def.get("ocr_keywords", [])
            if keywords:
                detections.extend(
                    find_keywords(processed, keywords, self._config.ocr_language)
                )

        detected_state = self._determine_state(detections, ocr_text)

        return ScreenAnalysisResult(
            device_id=device_id,
            screenshot_path=screenshot_path,
            detections=detections,
            detected_state=detected_state,
            ocr_text=ocr_text,
        )

    def _resolve_templates(
        self, template_names: list[str] | None
    ) -> dict[str, tuple[np.ndarray, float]]:
        templates: dict[str, tuple[np.ndarray, float]] = {}

        names_to_load = template_names or []
        screen_states = self._screen_states.get("screen_states", {})

        if not names_to_load:
            for state_def in screen_states.values():
                for tmpl in state_def.get("templates", []):
                    names_to_load.append(tmpl.get("name", ""))

        for name in names_to_load:
            if not name:
                continue
            threshold = self._config.template_match_threshold
            filename = f"{name}.png"

            for state_def in screen_states.values():
                for tmpl in state_def.get("templates", []):
                    if tmpl.get("name") == name:
                        threshold = tmpl.get("threshold", threshold)
                        filename = tmpl.get("path", filename)
                        break

            path = self._templates_dir / filename
            if path.exists():
                img = load_image(path)
                if img is not None:
                    templates[name] = (img, threshold)
            else:
                logger.debug("template_not_found", name=name, path=str(path))

        return templates

    def _determine_state(
        self,
        detections: list[DetectionResult],
        ocr_text: str,
    ) -> DeviceState | None:
        screen_states = self._screen_states.get("screen_states", {})
        detection_names = {d.name for d in detections}

        for state_name, state_def in screen_states.items():
            templates = state_def.get("templates", [])
            if templates:
                template_names = {t.get("name") for t in templates}
                if template_names & detection_names:
                    state_map = {
                        "home_screen": DeviceState.IDLE,
                        "lock_screen": DeviceState.WAITING,
                        "settings_screen": DeviceState.ACTIVE,
                    }
                    return state_map.get(state_name, DeviceState.ACTIVE)

            keywords = state_def.get("ocr_keywords", [])
            for keyword in keywords:
                if keyword.lower() in ocr_text.lower():
                    state_map = {
                        "lock_screen": DeviceState.WAITING,
                        "home_screen": DeviceState.IDLE,
                    }
                    return state_map.get(state_name, DeviceState.ACTIVE)

        if detections:
            return DeviceState.ACTIVE
        return DeviceState.UNKNOWN_SCREEN

    def evaluate_state_rules(
        self,
        rules: list[dict[str, Any]],
        analysis: ScreenAnalysisResult,
    ) -> DeviceState:
        """Evaluate workflow state rules against analysis results."""
        detection_names = {d.name for d in analysis.detections}

        for rule in rules:
            condition = rule.get("condition", "default")
            if condition == "template_match":
                template = rule.get("template", "")
                if template in detection_names:
                    return DeviceState(rule.get("state", "UNKNOWN_SCREEN"))
            elif condition == "ocr_contains":
                text = rule.get("text", "")
                if text.lower() in analysis.ocr_text.lower():
                    return DeviceState(rule.get("state", "UNKNOWN_SCREEN"))
            elif condition == "default":
                return DeviceState(rule.get("state", "UNKNOWN_SCREEN"))

        return DeviceState.UNKNOWN_SCREEN

    def verify_condition(
        self,
        condition: str,
        template: str | None,
        analysis: ScreenAnalysisResult,
    ) -> bool:
        """Verify a workflow verification step."""
        if condition == "template_match" and template:
            return any(d.name == template for d in analysis.detections)
        if condition == "ocr_contains" and template:
            return template.lower() in analysis.ocr_text.lower()
        return False
