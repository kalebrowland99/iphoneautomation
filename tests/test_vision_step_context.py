"""Tests for vision step goals, error context, and dismiss budgets."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.workflows.vision_step_context import (
    MAX_VISION_DISMISS_PER_WAIT,
    build_vision_error_msg,
    vision_step_goal,
)


def test_vision_step_goal_profile_tab() -> None:
    goal = vision_step_goal("tiktok_account_switch", "ensure_tiktok_account")
    assert "profile tab" in goal.lower()
    assert "@" in goal


def test_build_vision_error_msg_includes_recent_errors() -> None:
    prompt = build_vision_error_msg(
        workflow_name="tiktok_post",
        step_name="wait_for_plus",
        error_msg="Timeout waiting for plus",
        recent_errors=["tap_gallery: tap failed", "wait_for_plus: timeout"],
    )
    assert "Goal:" in prompt
    assert "wait_for_plus" in prompt
    assert "tap_gallery: tap failed" in prompt
    assert "Recent errors" in prompt


@pytest.mark.asyncio
async def test_plus_ready_stops_vision_after_max_dismisses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from imouse_farm.workflows import tiktok_plus_ready as plus_mod

    controller = MagicMock()
    controller.find_template_on_device = AsyncMock(return_value=None)
    app_config = MagicMock()

    dismiss = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "imouse_farm.workflows.vision_recovery.try_dismiss_blocking_popup",
        dismiss,
    )
    monkeypatch.setattr(plus_mod.asyncio, "sleep", AsyncMock())

    with pytest.raises(RuntimeError, match="\\+ button not visible"):
        await plus_mod.wait_for_tiktok_plus_visible(
            controller,
            "dev-1",
            app_config=app_config,
            templates_directory="config/templates",
            timeout_seconds=30.0,
            poll_seconds=0.05,
        )

    assert dismiss.await_count == MAX_VISION_DISMISS_PER_WAIT
