"""Tests for device settings and debug step gating."""

from imouse_farm.config.models import WorkflowStepConfig
from imouse_farm.settings.device_settings import get_debug_skip_post, set_debug_skip_post


def test_debug_skip_post_toggle() -> None:
    set_debug_skip_post("dev-1", True)
    assert get_debug_skip_post("dev-1") is True
    set_debug_skip_post("dev-1", False)
    assert get_debug_skip_post("dev-1") is False


def test_workflow_step_debug_fields_exist() -> None:
    step = WorkflowStepConfig(
        type="wait",
        name="after_post",
        unless_debug_skip_post=True,
    )
    assert step.unless_debug_skip_post is True
    step2 = WorkflowStepConfig(
        type="execute_action",
        name="debug_kill",
        when_debug_skip_post=True,
    )
    assert step2.when_debug_skip_post is True
