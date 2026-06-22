"""Tests for configuration loading."""

from pathlib import Path

import pytest

from imouse_farm.config.loader import load_config, load_workflow, load_workflows
from imouse_farm.config.models import DeviceState


@pytest.fixture
def config_path() -> Path:
    return Path(__file__).parent.parent / "config" / "config.yaml"


def test_load_config(config_path: Path) -> None:
    config = load_config(config_path)
    assert config.imouse.host == "localhost"
    assert config.vision.provider == "opencv_tesseract"
    assert "default" in config.device_groups


def test_load_workflows() -> None:
    workflows_dir = Path(__file__).parent.parent / "config" / "workflows"
    workflows = load_workflows(workflows_dir)
    assert "warmup" in workflows
    assert workflows["warmup"].loop is True


def test_load_warmup_workflow() -> None:
    path = Path(__file__).parent.parent / "config" / "workflows" / "warmup.yaml"
    workflow = load_workflow(path)
    step_types = [s.type for s in workflow.steps]
    assert "screenshot" in step_types
    assert "analyze" in step_types
    assert "wait_random" in step_types


def test_device_states() -> None:
    assert DeviceState.IDLE.value == "IDLE"
    assert DeviceState.UNKNOWN_SCREEN.value == "UNKNOWN_SCREEN"
