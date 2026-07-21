"""Tests for android-style telegram.yml loading."""

from __future__ import annotations

from pathlib import Path

from imouse_farm.notifications.telegram_config import (
    load_telegram_yml,
    resolve_telegram_credentials,
    telegram_alerts_enabled,
)
from imouse_farm.notifications.service import apply_telegram_yml_to_notifications
from imouse_farm.config.models import NotificationsConfig, TelegramConfig


def test_load_telegram_yml_android_keys(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    cfg = root / "config"
    cfg.mkdir(parents=True)
    (cfg / "telegram.yml").write_text(
        "telegram-api-token: '123:ABC'\ntelegram-chat-id: '999'\ntelegram-alerts: true\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "empty-appdata"))

    data = load_telegram_yml(root)
    assert data["telegram-api-token"] == "123:ABC"
    token, chat = resolve_telegram_credentials(root)
    assert token == "123:ABC"
    assert chat == "999"
    assert telegram_alerts_enabled(root) is True

    merged = apply_telegram_yml_to_notifications(
        NotificationsConfig(telegram=TelegramConfig(enabled=False)),
        project_root=root,
    )
    assert merged.telegram.enabled is True
    assert merged.telegram.bot_token == "123:ABC"
    assert merged.telegram.chat_id == "999"


def test_skip_placeholder_telegram_yml(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    cfg = root / "config"
    cfg.mkdir(parents=True)
    (cfg / "telegram.yml").write_text(
        "telegram-api-token: 'your-telegram-bot-token'\ntelegram-chat-id: 'your-chat-id'\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "empty-appdata"))

    assert load_telegram_yml(root) == {}
    assert resolve_telegram_credentials(root) == ("", "")
