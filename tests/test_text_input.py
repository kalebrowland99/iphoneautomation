"""Tests for multi-line text typing helpers."""

from imouse_farm.utils.text_input import typing_segments


def test_single_line_unchanged() -> None:
    assert typing_segments("hello world") == ["hello world"]


def test_two_lines_inserts_break_marker() -> None:
    assert typing_segments("line one\nline two") == ["line one", None, "line two"]


def test_blank_line_types_double_break() -> None:
    assert typing_segments("a\n\nb") == ["a", None, None, "b"]


def test_trailing_newline() -> None:
    assert typing_segments("hello\n") == ["hello", None]


def test_normalizes_crlf() -> None:
    assert typing_segments("a\r\nb") == ["a", None, "b"]
