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

# Small UI icons; backgrounds often vary (video frame behind button).
_SMALL_ICON_NAMES = frozenset(
    {
        "shadowrocket",
        "vpntoggle",
        "bluetoggle",
        "tiktok",
        "photos",
        "gallery",
        "aa",
        "border",
        "editor",
        "continuearrow",
        "post",
    }
)


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
            element = self._ui_element_for(name)
            if element.get("detect_method") == "ocr":
                continue
            search_screen, offset_x, offset_y = self._search_region(screen, name)
            match_white = bool(element.get("match_white_text", False))
            result = match_template(
                search_screen, template, threshold, name, match_white_text=match_white
            )
            if result:
                result = DetectionResult(
                    name=result.name,
                    confidence=result.confidence,
                    x=result.x + offset_x,
                    y=result.y + offset_y,
                    width=result.width,
                    height=result.height,
                    detection_type=result.detection_type,
                )
                detections.append(result)

        if requested:
            for element in self._iter_ui_elements():
                ename = element.get("name", "")
                if ename not in requested:
                    continue
                if element.get("detect_method") == "ocr":
                    result = self._ocr_detection(screen, element, ename)
                    if result and not any(d.name == ename for d in detections):
                        detections.append(result)
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
                        if ename in _SMALL_ICON_NAMES:
                            threshold = min(threshold, self._config.small_template_threshold)
                        search_screen, offset_x, offset_y = self._search_region(screen, ename)
                        match_white = bool(element.get("match_white_text", False))
                        result = match_template(
                            search_screen,
                            tmpl,
                            threshold,
                            ename,
                            match_white_text=match_white,
                        )
                        if result and not any(d.name == ename for d in detections):
                            result = DetectionResult(
                                name=result.name,
                                confidence=result.confidence,
                                x=result.x + offset_x,
                                y=result.y + offset_y,
                                width=result.width,
                                height=result.height,
                                detection_type="ui_element",
                            )
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
        element = self._ui_element_for(name)
        if element.get("detect_method") == "ocr":
            return None
        threshold, path = self._lookup_template(name)
        return path if path.exists() else None

    def threshold_for(self, name: str) -> float:
        threshold, _ = self._lookup_template(name)
        return threshold

    def device_threshold_for(self, name: str) -> float:
        element = self._ui_element_for(name)
        if element.get("device_threshold") is not None:
            return float(element["device_threshold"])
        return self.threshold_for(name)

    def min_confidence_for(self, name: str) -> float | None:
        element = self._ui_element_for(name)
        if element.get("min_confidence") is not None:
            return float(element["min_confidence"])
        return None

    def tap_offset_for(self, name: str) -> tuple[int, int]:
        element = self._ui_element_for(name)
        offset = element.get("tap_offset")
        if isinstance(offset, (list, tuple)) and len(offset) == 2:
            return int(offset[0]), int(offset[1])
        return 0, 0

    def search_rect_for(
        self, name: str, *, width: int | None = None, height: int | None = None
    ) -> list[int] | None:
        element = self._ui_element_for(name)
        w = width or 406
        h = height or 720
        pct = element.get("search_rect_pct")
        if isinstance(pct, list) and len(pct) == 4:
            return [
                int(w * float(pct[0])),
                int(h * float(pct[1])),
                int(w * float(pct[2])),
                int(h * float(pct[3])),
            ]
        rect = element.get("search_rect")
        if isinstance(rect, list) and len(rect) == 4:
            return [int(v) for v in rect]
        return None

    def _ui_element_for(self, name: str) -> dict[str, Any]:
        for element in self._iter_ui_elements():
            if element.get("name") == name:
                return element
        return {}

    def _ocr_detection(
        self, screen: Any, element: dict[str, Any], name: str
    ) -> DetectionResult | None:
        """Find OCR keyword in a template search region; detection key is ``name``."""
        keyword = str(element.get("ocr_keyword", "")).strip()
        if not keyword:
            return None
        search_screen, offset_x, offset_y = self._search_region(screen, name)
        processed = preprocess_for_ocr(search_screen)
        min_conf = float(element.get("ocr_min_confidence", 60.0))
        hits = find_keywords(
            processed, [keyword], self._config.ocr_language, min_confidence=min_conf
        )
        if not hits:
            return None
        best = max(hits, key=lambda d: d.confidence)
        return DetectionResult(
            name=name,
            confidence=best.confidence,
            x=best.x + offset_x,
            y=best.y + offset_y,
            width=best.width,
            height=best.height,
            detection_type="ocr",
        )

    def _search_region(
        self, screen: Any, name: str
    ) -> tuple[Any, int, int]:
        h, w = screen.shape[:2]
        rect = self.search_rect_for(name, width=w, height=h)
        if not rect:
            return screen, 0, 0
        x1, y1, x2, y2 = rect
        x1 = max(0, min(x1, w - 1))
        x2 = max(x1 + 1, min(x2, w))
        y1 = max(0, min(y1, h - 1))
        y2 = max(y1 + 1, min(y2, h))
        return screen[y1:y2, x1:x2], x1, y1

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
        if name in _SMALL_ICON_NAMES:
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
            if self._ui_element_for(name).get("detect_method") == "ocr":
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
                "tiktok_email_confirm": DeviceState.WAITING,
                "tiktok_post_notify": DeviceState.WAITING,
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
