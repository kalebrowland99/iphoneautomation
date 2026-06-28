"""Multi-sample template matching — pick the strongest hit across captures."""

from __future__ import annotations

from typing import Any

from imouse_farm.vision.fallbacks import DETECTION_FALLBACKS, apply_detection_fallbacks


def ocr_rect_from_pct(
    screen_width: int | None,
    screen_height: int | None,
    pct: list[float],
) -> list[int]:
    sw = int(screen_width) if screen_width else 406
    sh = int(screen_height) if screen_height else 720
    if len(pct) != 4:
        return [0, 0, sw, sh]
    return [
        int(sw * float(pct[0])),
        int(sh * float(pct[1])),
        int(sw * float(pct[2])),
        int(sh * float(pct[3])),
    ]


def pick_detection_hit(
    detections: dict[str, dict[str, Any]],
    target: str,
) -> dict[str, Any] | None:
    merged = apply_detection_fallbacks(detections)
    if target in merged:
        return dict(merged[target])
    for fallback in DETECTION_FALLBACKS.get(target, []):
        if fallback in merged:
            hit = dict(merged[fallback])
            hit["matched_via"] = fallback
            return hit
    return None


def stronger_hit(
    current: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not candidate:
        return current
    if not current:
        return candidate
    cur_conf = float(current.get("confidence", 0))
    cand_conf = float(candidate.get("confidence", 0))
    return candidate if cand_conf >= cur_conf else current
