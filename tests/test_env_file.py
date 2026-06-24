"""Tests for .env loading."""

import os

from imouse_farm.utils.env_file import load_env_file


def test_load_env_file_sets_missing_vars(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TEST_IMOUSE_ENV_KEY", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text('TEST_IMOUSE_ENV_KEY="hello"\n', encoding="utf-8")
    load_env_file(env_path)
    assert os.environ.get("TEST_IMOUSE_ENV_KEY") == "hello"


def test_load_env_file_does_not_override_existing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_IMOUSE_ENV_KEY", "existing")
    env_path = tmp_path / ".env"
    env_path.write_text("TEST_IMOUSE_ENV_KEY=from_file\n", encoding="utf-8")
    load_env_file(env_path)
    assert os.environ.get("TEST_IMOUSE_ENV_KEY") == "existing"
