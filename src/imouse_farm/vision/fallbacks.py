"""Template detection fallbacks — secondary templates map to a primary tap target."""

from __future__ import annotations

from typing import Any, Callable

# primary detection -> alternate template names (tried when primary is missing)
DETECTION_FALLBACKS: dict[str, list[str]] = {
    "continuearrow": ["post"],
    # Same physical switch — gray (off) vs blue (on) template.
    "vpntoggle": ["bluetoggle"],
}

# Only one detection per group may survive — highest confidence wins.
EXCLUSIVE_DETECTION_GROUPS: tuple[tuple[str, ...], ...] = (
    ("bluetoggle", "vpntoggle"),
)


def apply_tap_offsets(
    detections: dict[str, dict[str, Any]],
    offset_for: Callable[[str], tuple[int, int]],
) -> dict[str, dict[str, Any]]:
    """Shift tap coordinates using per-template offsets from screen_states.yaml."""
    result: dict[str, dict[str, Any]] = {}
    for name, hit in detections.items():
        ox, oy = offset_for(name)
        if ox or oy:
            adjusted = dict(hit)
            adjusted["x"] = int(hit["x"]) + ox
            adjusted["y"] = int(hit["y"]) + oy
            result[name] = adjusted
        else:
            result[name] = hit
    return result


def expand_template_names(names: list[str] | None) -> list[str]:
    """Include fallback template names for any requested primary detection."""
    if not names:
        return []
    expanded = list(names)
    for name in names:
        for fallback in DETECTION_FALLBACKS.get(name, []):
            if fallback not in expanded:
                expanded.append(fallback)
    return expanded


def apply_detection_fallbacks(detections: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Copy fallback hit coords onto the primary detection key for tapping."""
    result = dict(detections)
    for primary, fallbacks in DETECTION_FALLBACKS.items():
        if primary in result:
            continue
        for fallback in fallbacks:
            if fallback in result:
                hit = dict(result[fallback])
                hit["matched_via"] = fallback
                result[primary] = hit
                break
    return result


def apply_exclusive_detections(detections: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Drop lower-confidence hits when mutually exclusive templates both match."""
    result = dict(detections)
    for group in EXCLUSIVE_DETECTION_GROUPS:
        present = [name for name in group if name in result]
        if len(present) <= 1:
            continue
        best = max(
            present,
            key=lambda name: (
                float(result[name].get("confidence", 0)),
                1 if name == "vpntoggle" else 0,
            ),
        )
        for name in present:
            if name != best:
                del result[name]
    return result


def detection_satisfied(detections: dict[str, dict[str, Any]], name: str) -> bool:
    if name in detections:
        return True
    return any(fb in detections for fb in DETECTION_FALLBACKS.get(name, []))


def resolve_template_state_fallback(
    detections: dict[str, dict[str, Any]],
    fallback_templates: list[dict[str, Any]],
) -> tuple[str | None, float]:
    """Return (template_name, confidence) for the best fallback above min_confidence."""
    best_name: str | None = None
    best_conf = -1.0
    for entry in fallback_templates:
        template = str(entry.get("template") or "").strip()
        if not template or template not in detections:
            continue
        min_conf = float(entry.get("min_confidence", 0.42))
        conf = float(detections[template].get("confidence", 0))
        if conf >= min_conf and conf > best_conf:
            best_name = template
            best_conf = conf
    if best_name is None:
        return None, 0.0
    return best_name, best_conf
