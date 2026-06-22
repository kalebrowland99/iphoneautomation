"""OpenCV + Tesseract vision provider (v1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from imouse_farm.analysis.ocr import configure_tesseract, extract_text, find_keywords, preprocess_for_ocr
from imouse_farm.analysis.template import load_image, match_all_templates, match_template
from imouse_farm.config.models import AnalysisConfig, DetectionResult, DeviceState
from imouse_farm.utils.logging import get_logger
from imouse_farm.vision.base import VisionAnalysis, VisionProvider

logger = get_logger(__name__)


class OpenCVVisionProvider(VisionProvider):
    """Version 1 vision: OpenCV template matching + Tesseract OCR."""

    def __init__(self, config: AnalysisConfig, workflows_dir: str = "config/workflows") -> None:
        self._config = config
        self._workflows_dir = Path(workflows_dir)
        self._templates_dir = Path(config.templates_directory)
        self._screen_states = self._load_yaml(self._workflows_dir / "screen_states.yaml")
        self._popups = self._load_yaml(self._workflows_dir / "popups.yaml").get("popups", {})
        configure_tesseract(config.tesseract_cmd)

    @property
    def name(self) -> str:
        return "opencv_tesseract"

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

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
        screen = load_image(screenshot_path)
        if screen is None:
            return VisionAnalysis(
                device_id=device_id,
                screenshot_path=screenshot_path,
                detected_state=DeviceState.ERROR,
                provider=self.name,
            )

        detections: list[DetectionResult] = []
        templates = self._resolve_templates(template_names)
        requested = set(template_names or [])
        for name, (template, threshold) in templates.items():
            search_screen = screen
            if name == "vpn":
                roi_h = max(int(screen.shape[0] * 0.12), template.shape[0] + 4)
                search_screen = screen[0:roi_h, :]
            result = match_template(search_screen, template, threshold, name)
            if result:
                detections.append(result)

        if requested:
            for element in self._iter_ui_elements():
                ename = element.get("name", "")
                if ename not in requested:
                    continue
                path = self._templates_dir / element.get("template", "")
                if not path.exists():
                    for ext in (".jpg", ".jpeg", ".png"):
                        alt = self._templates_dir / f"{ename}{ext}"
                        if alt.exists():
                            path = alt
                            break
                if path.exists():
                    tmpl = load_image(path)
                    if tmpl is not None:
                        threshold = element.get("threshold", self._config.template_match_threshold)
                        if ename in {"vpn", "shadowrocket", "vpntoggle", "tiktok", "photos"}:
                            threshold = min(threshold, self._config.small_template_threshold)
                        result = match_template(screen, tmpl, threshold, ename)
                        if result:
                            result.detection_type = "ui_element"
                            detections.append(result)

        processed = preprocess_for_ocr(screen)
        ocr_text = extract_text(processed, self._config.ocr_language, ocr_regions)

        popups = popup_definitions or self._popups
        popup_type = self._detect_popup(popups, detections, ocr_text)

        for state_name, state_def in self._screen_states.get("screen_states", {}).items():
            keywords = state_def.get("ocr_keywords", [])
            if keywords:
                detections.extend(find_keywords(processed, keywords, self._config.ocr_language))

        if ocr_keywords:
            detections.extend(find_keywords(processed, ocr_keywords, self._config.ocr_language))

        detected_state = self._determine_state(detections, ocr_text, popup_type)

        return VisionAnalysis(
            device_id=device_id,
            screenshot_path=screenshot_path,
            detections=detections,
            detected_state=detected_state,
            ocr_text=ocr_text,
            popup_type=popup_type,
            provider=self.name,
        )

    def template_path_for(self, name: str) -> Path | None:
        """Resolve on-disk path for a named template."""
        threshold, path = self._lookup_template(name)
        return path if path.exists() else None

    def threshold_for(self, name: str) -> float:
        threshold, _ = self._lookup_template(name)
        return threshold

    def _lookup_template(self, name: str) -> tuple[float, Path]:
        threshold = self._config.template_match_threshold
        filename = f"{name}.jpg"
        screen_states = self._screen_states.get("screen_states", {})
        for state_def in screen_states.values():
            for tmpl in state_def.get("templates", []):
                if tmpl.get("name") == name:
                    threshold = tmpl.get("threshold", threshold)
                    filename = tmpl.get("path", filename)
        for element in self._iter_ui_elements():
            if element.get("name") == name:
                threshold = element.get("threshold", threshold)
                filename = element.get("template", filename)
        path = self._templates_dir / filename
        if not path.exists():
            for ext in (".jpg", ".jpeg", ".png", ".bmp"):
                alt = self._templates_dir / f"{name}{ext}"
                if alt.exists():
                    path = alt
                    break
        if name in {"vpn", "shadowrocket", "vpntoggle", "tiktok", "photos"}:
            threshold = min(threshold, self._config.small_template_threshold)
        return threshold, path

    def _resolve_templates(self, names: list[str] | None) -> dict:
        import numpy as np

        templates: dict[str, tuple[np.ndarray, float]] = {}
        names_to_load = names or []
        screen_states = self._screen_states.get("screen_states", {})

        if not names_to_load:
            for state_def in screen_states.values():
                for tmpl in state_def.get("templates", []):
                    names_to_load.append(tmpl.get("name", ""))

        for name in names_to_load:
            if not name:
                continue
            threshold, path = self._lookup_template(name)
            if path.exists():
                img = load_image(path)
                if img is not None:
                    templates[name] = (img, threshold)
        return templates

    def _iter_ui_elements(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        ui = self._screen_states.get("ui_elements", {})
        if isinstance(ui, list):
            items.extend(ui)
        elif isinstance(ui, dict):
            for elements in ui.values():
                if isinstance(elements, list):
                    items.extend(elements)
                elif isinstance(elements, dict):
                    items.append(elements)
        automation = self._screen_states.get("automation", {})
        if isinstance(automation, dict):
            for elements in automation.values():
                if isinstance(elements, list):
                    items.extend(elements)
                elif isinstance(elements, dict):
                    items.append(elements)
        return items

    def _detect_popup(
        self,
        popups: dict[str, Any],
        detections: list[DetectionResult],
        ocr_text: str,
    ) -> str | None:
        detection_names = {d.name for d in detections}
        ocr_lower = ocr_text.lower()

        for popup_id, popup_def in popups.items():
            for tmpl in popup_def.get("templates", []):
                if tmpl.get("name") in detection_names:
                    return popup_id
            for keyword in popup_def.get("ocr_keywords", []):
                if keyword.lower() in ocr_lower:
                    return popup_id
        return None

    def _determine_state(
        self, detections: list[DetectionResult], ocr_text: str, popup_type: str | None
    ) -> DeviceState | None:
        if popup_type:
            popup_state_map = {
                "permission_dialog": DeviceState.WAITING,
                "update_prompt": DeviceState.WAITING,
                "login_prompt": DeviceState.WAITING,
                "confirmation_dialog": DeviceState.WAITING,
            }
            return popup_state_map.get(popup_type, DeviceState.UNKNOWN_SCREEN)

        detection_names = {d.name for d in detections}
        screen_states = self._screen_states.get("screen_states", {})

        for state_name, state_def in screen_states.items():
            template_names = {t.get("name") for t in state_def.get("templates", [])}
            if template_names & detection_names:
                state_map = {
                    "home_screen": DeviceState.IDLE,
                    "lock_screen": DeviceState.WAITING,
                    "settings_screen": DeviceState.ACTIVE,
                }
                return state_map.get(state_name, DeviceState.ACTIVE)
            for keyword in state_def.get("ocr_keywords", []):
                if keyword.lower() in ocr_text.lower():
                    return DeviceState.WAITING if state_name == "lock_screen" else DeviceState.IDLE

        return DeviceState.UNKNOWN_SCREEN if not detections else DeviceState.ACTIVE
