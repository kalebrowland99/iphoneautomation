"""Load Telegram settings (androidautomationig-compatible telegram.yml)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def _support_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or "") / "iMouseFarm"


def telegram_yml_candidates(project_root: Path | None = None) -> list[Path]:
    """Prefer Application Support copy (Task Scheduler safe), then project config/."""
    paths: list[Path] = [_support_dir() / "telegram.yml"]
    if project_root is not None:
        paths.append(Path(project_root) / "config" / "telegram.yml")
    else:
        # …/src/imouse_farm/notifications/this.py → repo root
        root = Path(__file__).resolve().parents[3]
        paths.append(root / "config" / "telegram.yml")
    return paths


def load_telegram_yml(project_root: Path | None = None) -> dict[str, Any]:
    """Return raw telegram.yml dict, or {} if missing/placeholder."""
    for path in telegram_yml_candidates(project_root):
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        token = str(
            data.get("telegram-api-token")
            or data.get("bot_token")
            or data.get("token")
            or ""
        ).strip()
        chat = str(
            data.get("telegram-chat-id")
            or data.get("chat_id")
            or data.get("chat")
            or ""
        ).strip()
        if not token or token.startswith("your-"):
            continue
        if not chat or "your-chat" in chat.lower():
            continue
        return data
    return {}


def resolve_telegram_credentials(
    project_root: Path | None = None,
) -> tuple[str, str]:
    """Token + chat id from telegram.yml or env (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)."""
    data = load_telegram_yml(project_root)
    token = str(
        data.get("telegram-api-token")
        or data.get("bot_token")
        or os.environ.get("TELEGRAM_BOT_TOKEN")
        or ""
    ).strip()
    chat = str(
        data.get("telegram-chat-id")
        or data.get("chat_id")
        or os.environ.get("TELEGRAM_CHAT_ID")
        or ""
    ).strip()
    if token.startswith("your-"):
        token = ""
    if "your-chat" in chat.lower():
        chat = ""
    return token, chat


def telegram_alerts_enabled(project_root: Path | None = None) -> bool:
    data = load_telegram_yml(project_root)
    if not data:
        token, chat = resolve_telegram_credentials(project_root)
        return bool(token and chat)
    return data.get("telegram-alerts", True) is not False
