"""Tests for starting tiktok_post from a specific post index."""

from imouse_farm.config.models import WorkflowConfig, WorkflowStepConfig
from imouse_farm.workflows.engine import WorkflowRunner


def _make_runner(start_post_index: int = 1) -> WorkflowRunner:
    workflow = WorkflowConfig(
        name="tiktok_post",
        enabled=True,
        loop=True,
        max_iterations=3,
        steps=[WorkflowStepConfig(type="wait", name="noop", duration_seconds=0)],
    )
    return WorkflowRunner(
        workflow=workflow,
        device_id="dev-1",
        config=None,  # type: ignore[arg-type]
        device_manager=None,  # type: ignore[arg-type]
        screenshot_service=None,  # type: ignore[arg-type]
        vision=None,  # type: ignore[arg-type]
        popup_manager=None,  # type: ignore[arg-type]
        state_machine=None,  # type: ignore[arg-type]
        action_engine=None,  # type: ignore[arg-type]
        db=None,  # type: ignore[arg-type]
        start_post_index=start_post_index,
    )


def test_runner_stores_start_post_index() -> None:
    assert _make_runner(2).start_post_index == 2
    assert _make_runner(1).start_post_index == 1
