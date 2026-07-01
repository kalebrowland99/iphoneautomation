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
        brand: dict(values)
        for brand, values in prompt_store._BRAND_DEFAULTS.items()
    })
    yield path


def test_prompt_settings_persist_per_brand(isolated_prompt_store: Path) -> None:
    prompt_store.set_ai_prompt("custom labely prompt", brand="labely")
    prompt_store.set_ai_hashtags("#labely", brand="labely")
    prompt_store.set_ai_prompt("custom valcoin prompt", brand="valcoin")
    prompt_store.set_ai_hashtags("#valcoin", brand="valcoin")

    raw = json.loads(isolated_prompt_store.read_text(encoding="utf-8"))
    assert raw["labely"]["prompt"] == "custom labely prompt"
    assert raw["valcoin"]["prompt"] == "custom valcoin prompt"

    prompt_store._load_settings()
    assert prompt_store.get_ai_prompt("labely") == "custom labely prompt"
    assert prompt_store.get_ai_prompt("valcoin") == "custom valcoin prompt"
    assert prompt_store.get_ai_hashtags("valcoin") == "#valcoin"


def test_legacy_flat_settings_migrate_to_labely(isolated_prompt_store: Path) -> None:
    isolated_prompt_store.write_text(
        json.dumps({"prompt": "legacy prompt", "hashtags": "#legacy"}) + "\n",
        encoding="utf-8",
    )
    prompt_store._load_settings()
    assert prompt_store.get_ai_prompt("labely") == "legacy prompt"
    assert prompt_store.get_ai_hashtags("labely") == "#legacy"
    assert prompt_store.get_ai_prompt("valcoin") == prompt_store.DEFAULT_VALCOIN_AI_PROMPT


def test_empty_saved_prompt_falls_back_to_default(isolated_prompt_store: Path) -> None:
    isolated_prompt_store.write_text(
        json.dumps({"labely": {"prompt": "", "hashtags": ""}}) + "\n",
        encoding="utf-8",
    )
    prompt_store._load_settings()
    settings = prompt_store.get_ai_settings("labely")
    assert "labely" in settings["prompt"].lower()
    assert settings["hashtags"] == prompt_store.DEFAULT_AI_HASHTAGS


def test_set_empty_hashtags_keeps_brand_default(isolated_prompt_store: Path) -> None:
    prompt_store.set_ai_hashtags("", brand="labely")
    assert prompt_store.get_ai_hashtags("labely") == prompt_store.DEFAULT_AI_HASHTAGS
    raw = json.loads(isolated_prompt_store.read_text(encoding="utf-8"))
    assert raw["labely"]["hashtags"] == prompt_store.DEFAULT_AI_HASHTAGS
