"""YAML configuration loader."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from imouse_farm.config.models import AppConfig, WorkflowConfig
from imouse_farm.notifications.telegram_config import resolve_telegram_credentials
from imouse_farm.utils.env_file import load_env_file


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(path: str | Path) -> AppConfig:
    """Load main application configuration from a YAML file."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    project_root = config_path.parent.parent
    load_env_file(project_root / ".env")
    data = _load_yaml(config_path)
    nav_path = config_path.parent / "tiktok_navigation.yaml"
    if nav_path.exists() and "tiktok_navigation" not in data:
        data["tiktok_navigation"] = _load_yaml(nav_path)
    slideshow = data.setdefault("slideshow", {})
    env_secret = os.environ.get("FARM_SECRET", "").strip()
    if env_secret and not str(slideshow.get("farm_secret") or "").strip():
        slideshow["farm_secret"] = env_secret
    # androidautomationig-style config/telegram.yml (or %LOCALAPPDATA%\iMouseFarm\telegram.yml)
    token, chat_id = resolve_telegram_credentials(project_root)
    if token and chat_id:
        notifications = data.setdefault("notifications", {})
        telegram = notifications.setdefault("telegram", {})
        telegram["enabled"] = True
        telegram["bot_token"] = token
        telegram["chat_id"] = chat_id
        notifications["enabled"] = True
    return AppConfig.model_validate(data)


def load_workflow(path: str | Path) -> WorkflowConfig:
    """Load a single workflow definition from YAML."""
    workflow_path = Path(path)
    if not workflow_path.exists():
        raise FileNotFoundError(f"Workflow file not found: {workflow_path}")
    data = _load_yaml(workflow_path)
    return WorkflowConfig.model_validate(data)


def load_workflows(directory: str | Path) -> dict[str, WorkflowConfig]:
    """Load all workflow YAML files from a directory."""
    workflows_dir = Path(directory)
    workflows: dict[str, WorkflowConfig] = {}
    if not workflows_dir.exists():
        return workflows

    for path in sorted(workflows_dir.glob("*.yaml")):
        if path.stem in ("screen_states", "popups"):
            continue
        workflow = load_workflow(path)
        workflows[workflow.name] = workflow
    return workflows
