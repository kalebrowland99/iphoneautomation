"""Tests for persisted caption AI settings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from imouse_farm.captions import prompt_store


@pytest.fixture
def isolated_prompt_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "caption_ai_settings.json"
    monkeypatch.setattr(prompt_store, "CAPTION_AI_SETTINGS_PATH", path)
    monkeypatch.setattr(prompt_store, "_settings", {
        "prompt": prompt_store.DEFAULT_AI_PROMPT,
        "hashtags": prompt_store.DEFAULT_AI_HASHTAGS,
    })
    yield path


def test_prompt_settings_persist(isolated_prompt_store: Path) -> None:
    prompt_store.set_ai_prompt("custom prompt")
    prompt_store.set_ai_hashtags("#test")

    raw = json.loads(isolated_prompt_store.read_text(encoding="utf-8"))
    assert raw["prompt"] == "custom prompt"
    assert raw["hashtags"] == "#test"

    prompt_store._load_settings()
    assert prompt_store.get_ai_prompt() == "custom prompt"
    assert prompt_store.get_ai_hashtags() == "#test"
