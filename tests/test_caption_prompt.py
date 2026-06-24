"""Tests for default AI caption prompt settings."""

from imouse_farm.captions.prompt_store import DEFAULT_AI_PROMPT, get_ai_prompt


def test_default_prompt_reads_filename_and_mentions_labely() -> None:
    prompt = get_ai_prompt()
    assert prompt == DEFAULT_AI_PROMPT
    assert "filename" in prompt.lower()
    assert "labely" in prompt.lower()
    assert "lowercase" in prompt.lower()
    assert "never ask questions" in prompt.lower()
    assert "do not use hyphens" in prompt.lower()
