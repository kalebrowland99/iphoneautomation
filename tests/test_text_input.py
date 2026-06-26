"""Tests for multi-line text typing helpers."""

from imouse_farm.utils.text_input import (
    flatten_line_breaks,
    prepare_single_line_typing_segments,
    prepare_typing_segments,
    typing_segments,
)


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


def test_flatten_line_breaks() -> None:
    assert flatten_line_breaks("hello\n\nworld") == "hello world"


def test_prepare_single_line_no_break_markers() -> None:
    segments = prepare_single_line_typing_segments("caption line\n\n#tag1 #tag2")
    assert None not in segments
    assert "".join(segments) == "caption line #tag1 #tag2"


def test_prepare_single_line_chunks_long_text() -> None:
    text = "word " * 30
    segments = prepare_single_line_typing_segments(text.strip())
    assert None not in segments
    assert all(len(seg) <= 80 for seg in segments)
    assert "".join(segments) == text.strip()


def test_prepare_single_line_preserves_hashtag_spaces() -> None:
    text = (
        "This is why america is sick #chicken #toxicchicken "
        "#toxinfree #groceryshopping #cleaningredients"
    )
    segments = prepare_single_line_typing_segments(text)
    assert "".join(segments) == text


def test_prepare_typing_segments_chunks_long_line() -> None:
    text = "a" * 200
    segments = prepare_typing_segments(text)
    assert segments == [text[i : i + 80] for i in range(0, 200, 80)]
