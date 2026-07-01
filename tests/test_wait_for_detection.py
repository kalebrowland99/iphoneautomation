"""Tests for wait_for_detection workflow step."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from imouse_farm.config.models import AppConfig, DetectionResult, WorkflowConfig, WorkflowStepConfig
from imouse_farm.vision.base import VisionAnalysis
from imouse_farm.workflows.engine import WorkflowRunner


def _make_runner() -> WorkflowRunner:
    workflow = WorkflowConfig(name="test", steps=[])
    return WorkflowRunner(
        workflow=workflow,
        device_id="dev-1",
        config=AppConfig(),
        device_manager=MagicMock(),
        screenshot_service=MagicMock(),
        vision=MagicMock(),
        popup_manager=MagicMock(),
        state_machine=MagicMock(),
        action_engine=MagicMock(),
        db=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_wait_for_detection_succeeds_when_found_on_second_poll() -> None:
    runner = _make_runner()
    runner._running = True
    runner._device_manager.is_workflow_paused = AsyncMock(return_value=False)
    runner._step_capture = AsyncMock()
    runner._log_activity = AsyncMock()

    analysis_without = VisionAnalysis(
        device_id="dev-1",
        screenshot_path="x.png",
        detections=[],
        provider="test",
    )
    analysis_with = VisionAnalysis(
        device_id="dev-1",
        screenshot_path="x.png",
        detections=[
            DetectionResult(name="plus", confidence=0.9, x=10, y=20, detection_type="template")
        ],
        provider="test",
    )
    calls = {"n": 0}

    async def fake_analyze(step: WorkflowStepConfig) -> None:
        calls["n"] += 1
        runner._last_analysis = analysis_with if calls["n"] >= 2 else analysis_without
        runner._has_recent_analysis = True

    runner._step_analyze = fake_analyze

    step = WorkflowStepConfig(
        type="wait_for_detection",
        name="wait_for_plus",
        templates=["plus"],
        when_detection="plus",
        duration_seconds=10,
        min_seconds=0.01,
    )

    with patch("imouse_farm.workflows.engine.asyncio.sleep", new_callable=AsyncMock):
        await runner._step_wait_for_detection(step)

    assert calls["n"] == 2
    assert runner._has_detection("plus")


@pytest.mark.asyncio
async def test_wait_for_detection_not_skipped_when_target_missing() -> None:
    """when_detection is the wait target, not a pre-condition, for wait_for_detection steps."""
    runner = _make_runner()
    step = WorkflowStepConfig(
        type="wait_for_detection",
        name="wait_for_tiktok",
        templates=["tiktok"],
        when_detection="tiktok",
    )
    runner._last_analysis = None
    assert runner._step_skip_reason(step) is None


@pytest.mark.asyncio
async def test_wait_for_detection_times_out() -> None:
    runner = _make_runner()
    runner._running = True
    runner._device_manager.is_workflow_paused = AsyncMock(return_value=False)
    runner._step_capture = AsyncMock()
    runner._log_activity = AsyncMock()
    runner._step_analyze = AsyncMock(
        return_value=VisionAnalysis(
            device_id="dev-1",
            screenshot_path="x.png",
            detections=[],
            provider="test",
        )
    )

    step = WorkflowStepConfig(
        type="wait_for_detection",
        name="wait_for_plus",
        templates=["plus"],
        when_detection="plus",
        duration_seconds=0.05,
        min_seconds=0.02,
    )

    with pytest.raises(RuntimeError, match="Timeout waiting for 'plus'"):
        await runner._step_wait_for_detection(step)


@pytest.mark.asyncio
async def test_wait_for_detection_scans_popups_each_poll() -> None:
    runner = _make_runner()
    runner._workflow = WorkflowConfig(name="tiktok_post", steps=[])
    runner._running = True
    runner._device_manager.is_workflow_paused = AsyncMock(return_value=False)
    runner._step_capture = AsyncMock()
    runner._log_activity = AsyncMock()
    runner._step_analyze = AsyncMock()
    runner._has_detection = MagicMock(return_value=False)
    runner._try_dismiss_popups = AsyncMock(return_value=False)

    step = WorkflowStepConfig(
        type="wait_for_detection",
        name="wait_for_plus",
        templates=["plus"],
        when_detection="plus",
        duration_seconds=0.05,
        min_seconds=0.02,
    )

    with pytest.raises(RuntimeError, match="Timeout waiting for 'plus'"):
        await runner._step_wait_for_detection(step)

    assert runner._try_dismiss_popups.await_count >= 1


@pytest.mark.asyncio
async def test_wait_for_detection_restarts_tiktok_after_failed_polls() -> None:
    runner = _make_runner()
    runner._workflow = WorkflowConfig(name="tiktok_post", steps=[])
    runner._running = True
    runner._device_manager.is_workflow_paused = AsyncMock(return_value=False)
    runner._step_capture = AsyncMock()
    runner._log_activity = AsyncMock()
    runner._try_dismiss_popups = AsyncMock(return_value=False)
    runner._restart_tiktok = AsyncMock()

    calls = {"n": 0}

    async def fake_analyze(step: WorkflowStepConfig) -> None:
        calls["n"] += 1
        runner._last_analysis = VisionAnalysis(
            device_id="dev-1",
            screenshot_path="x.png",
            detections=[],
            provider="test",
        )
        runner._has_recent_analysis = True

    runner._step_analyze = fake_analyze
    runner._has_detection = MagicMock(side_effect=lambda name: calls["n"] > 4)

    step = WorkflowStepConfig(
        type="wait_for_detection",
        name="wait_for_plus",
        templates=["plus"],
        when_detection="plus",
        duration_seconds=60,
        min_seconds=0.01,
        action={"restart_app_after_attempts": 3, "max_app_restarts": 2},
    )

    with patch("imouse_farm.workflows.engine.asyncio.sleep", new_callable=AsyncMock):
        await runner._step_wait_for_detection(step)

    runner._restart_tiktok.assert_awaited_once()
    assert calls["n"] >= 4
