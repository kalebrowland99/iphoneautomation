"""Template matching utilities."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from imouse_farm.config.models import DetectionResult
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


def load_image(path: str | Path) -> np.ndarray | None:
    """Load image from disk as BGR numpy array."""
    img = cv2.imread(str(path))
    return img


def match_template(
    screen: np.ndarray,
    template: np.ndarray,
    threshold: float = 0.8,
    name: str = "template",
    *,
    multiscale: bool | None = None,
    match_white_text: bool = False,
) -> DetectionResult | None:
    """Perform OpenCV template matching with confidence scoring."""
    if screen is None or template is None:
        return None

    if match_white_text:
        masked = _match_template_white_text(screen, template, threshold, name, multiscale=multiscale)
        if masked:
            return masked

    use_multiscale = multiscale
    if use_multiscale is None:
        h, w = template.shape[:2]
        use_multiscale = max(h, w) < 120 or min(h, w) < 30

    if use_multiscale:
        return _match_template_multiscale(screen, template, threshold, name)

    if template.shape[0] > screen.shape[0] or template.shape[1] > screen.shape[1]:
        logger.warning("template_larger_than_screen", name=name)
        return None

    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val >= threshold:
        h, w = template.shape[:2]
        return DetectionResult(
            name=name,
            confidence=float(max_val),
            x=max_loc[0] + w // 2,
            y=max_loc[1] + h // 2,
            width=w,
            height=h,
            detection_type="template",
        )
    return None


def _multiscale_factors(template: np.ndarray) -> tuple[float, ...]:
    """Scale factors for template matching; narrow strips need extra range."""
    h, w = template.shape[:2]
    if min(h, w) < 30:
        return (0.35, 0.5, 0.65, 0.8, 1.0, 1.2, 1.4, 1.6, 2.0, 2.5, 3.0)
    return (0.5, 0.65, 0.8, 1.0, 1.2, 1.4, 1.6, 2.0)


def _match_template_multiscale(
    screen: np.ndarray,
    template: np.ndarray,
    threshold: float,
    name: str,
) -> DetectionResult | None:
    """Match small icons across scales (phone mirror size varies)."""
    best_val = -1.0
    best_loc = (0, 0)
    best_size = (template.shape[1], template.shape[0])

    for scale in _multiscale_factors(template):
        tw = int(template.shape[1] * scale)
        th = int(template.shape[0] * scale)
        if tw < 4 or th < 4:
            continue
        if th > screen.shape[0] or tw > screen.shape[1]:
            continue
        scaled = cv2.resize(template, (tw, th))
        result = cv2.matchTemplate(screen, scaled, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val > best_val:
            best_val = float(max_val)
            best_loc = max_loc
            best_size = (tw, th)

    if best_val >= threshold:
        return DetectionResult(
            name=name,
            confidence=best_val,
            x=best_loc[0] + best_size[0] // 2,
            y=best_loc[1] + best_size[1] // 2,
            width=best_size[0],
            height=best_size[1],
            detection_type="template",
        )
    return None


def _match_template_white_text(
    screen: np.ndarray,
    template: np.ndarray,
    threshold: float,
    name: str,
    *,
    multiscale: bool | None = None,
) -> DetectionResult | None:
    """Match icons where only bright foreground (e.g. white Aa) is stable."""
    t_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    mask = cv2.threshold(t_gray, 170, 255, cv2.THRESH_BINARY)[1]
    if cv2.countNonZero(mask) < 8:
        return None

    s_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    use_multiscale = multiscale
    if use_multiscale is None:
        h, w = template.shape[:2]
        use_multiscale = max(h, w) < 120

    best_val = -1.0
    best_loc = (0, 0)
    best_size = (template.shape[1], template.shape[0])

    scales = (0.5, 0.65, 0.8, 1.0, 1.2, 1.4, 1.6, 2.0) if use_multiscale else (1.0,)
    for scale in scales:
        tw = int(template.shape[1] * scale)
        th = int(template.shape[0] * scale)
        if tw < 4 or th < 4:
            continue
        if th > s_gray.shape[0] or tw > s_gray.shape[1]:
            continue
        scaled_gray = cv2.resize(t_gray, (tw, th))
        scaled_mask = cv2.resize(mask, (tw, th), interpolation=cv2.INTER_NEAREST)
        if cv2.countNonZero(scaled_mask) < 8:
            continue
        try:
            result = cv2.matchTemplate(
                s_gray, scaled_gray, cv2.TM_CCOEFF_NORMED, mask=scaled_mask
            )
        except cv2.error:
            continue
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val > best_val:
            best_val = float(max_val)
            best_loc = max_loc
            best_size = (tw, th)

    if best_val >= threshold:
        return DetectionResult(
            name=name,
            confidence=best_val,
            x=best_loc[0] + best_size[0] // 2,
            y=best_loc[1] + best_size[1] // 2,
            width=best_size[0],
            height=best_size[1],
            detection_type="template",
        )
    return None


def match_all_templates(
    screen: np.ndarray,
    templates: dict[str, tuple[np.ndarray, float]],
) -> list[DetectionResult]:
    """Match multiple templates against a screen image."""
    detections: list[DetectionResult] = []
    for name, (template, threshold) in templates.items():
        result = match_template(screen, template, threshold, name)
        if result:
            detections.append(result)
    return detections
