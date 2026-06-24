"""Helpers for typing multi-line text on iOS via iMouse key_sendkey."""

from __future__ import annotations

# iMouseXP fn_key values that insert a line break (try in order).
LINE_BREAK_FN_KEYS = ("enter", "Enter", "return", "Return", "WIN+enter")


def normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def typing_segments(text: str) -> list[str | None]:
    """Split text into chunks to type; ``None`` means press line-break/Enter."""
    normalized = normalize_line_endings(text)
    if "\n" not in normalized:
        return [normalized]

    lines = normalized.split("\n")
    segments: list[str | None] = []
    for index, line in enumerate(lines):
        if line:
            segments.append(line)
        if index < len(lines) - 1:
            segments.append(None)
    return segments
