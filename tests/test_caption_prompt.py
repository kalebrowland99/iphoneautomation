"""Tests for default AI caption prompt settings."""

from imouse_farm.captions.prompt_store import (
    DEFAULT_AI_PROMPT,
    DEFAULT_VALCOIN_AI_PROMPT,
    get_ai_prompt,
)


def test_default_prompt_reads_filename_and_mentions_labely() -> None:
    prompt = DEFAULT_AI_PROMPT
    assert "filename" in prompt.lower()
    assert "labely" in prompt.lower()
    assert "lowercase" in prompt.lower()
    assert "gen z" in prompt.lower()
    assert "do not use hyphens" in prompt.lower()


def test_valcoin_prompt_ignores_filenames_and_promotes_valcoin() -> None:
    prompt = get_ai_prompt("valcoin")
    assert "ignore" in prompt.lower() and "filename" in prompt.lower()
    assert "valcoin" in prompt.lower()
    assert "rich" not in prompt.lower() or "never use the word rich" in prompt.lower()
