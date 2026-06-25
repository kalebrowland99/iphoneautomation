"""Helpers for typing multi-line text on iOS via iMouse key_sendkey."""

from __future__ import annotations

import re

# iMouseXP fn_key values that insert a line break (try in order).
LINE_BREAK_FN_KEYS = ("enter", "Enter", "return", "Return", "WIN+enter")

# Long single key_sendkey payloads can fail on-device; keep chunks conservative.
MAX_KEY_CHUNK_LEN = 80


def normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def flatten_line_breaks(text: str) -> str:
    """Collapse newlines into spaces for single-line captions (no Enter keys)."""
    return re.sub(r"\s+", " ", normalize_line_endings(text)).strip()


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


def _split_text_chunks(text: str, max_len: int) -> list[str]:
    """Split a long line into <=max_len chunks, preferring spaces."""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= max_len:
            chunks.append(rest)
            break
        cut = rest.rfind(" ", 0, max_len + 1)
        if cut <= 0:
            cut = max_len
        chunk = rest[:cut].rstrip()
        if not chunk:
            chunk = rest[:max_len]
            cut = max_len
        chunks.append(chunk)
        rest = rest[cut:].lstrip()
    return chunks


def expand_typing_chunks(
    segments: list[str | None],
    max_len: int = MAX_KEY_CHUNK_LEN,
) -> list[str | None]:
    """Further split long text segments for reliable key_sendkey calls."""
    expanded: list[str | None] = []
    for segment in segments:
        if segment is None:
            expanded.append(None)
        elif len(segment) <= max_len:
            expanded.append(segment)
        else:
            expanded.extend(_split_text_chunks(segment, max_len))
    return expanded


def prepare_typing_segments(text: str, max_len: int = MAX_KEY_CHUNK_LEN) -> list[str | None]:
    """Line breaks + chunking for device text input."""
    return expand_typing_chunks(typing_segments(text), max_len=max_len)


def prepare_single_line_typing_segments(
    text: str, max_len: int = MAX_KEY_CHUNK_LEN
) -> list[str]:
    """Chunked typing with no line-break keys — for TikTok final captions."""
    flat = flatten_line_breaks(text)
    if not flat:
        return []
    return [seg for seg in expand_typing_chunks([flat], max_len=max_len) if seg is not None]
