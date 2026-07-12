"""Tests for TikTok + button readiness wait."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.workflows.tiktok_plus_ready import wait_for_tiktok_plus_visible


@pytest.mark.asyncio
async def test_wait_for_plus_returns_when_template_found() -> None:
    controller = MagicMock()
    controller.find_template_on_device = AsyncMock(
        return_value={"x": 200, "y": 680, "confidence": 0.91}
    )
    assert await wait_for_tiktok_plus_visible(
        controller,
        "dev-1",
        templates_directory="config/templates",
        timeout_seconds=5.0,
        poll_seconds=0.1,
    )
    controller.find_template_on_device.assert_awaited()


@pytest.mark.asyncio
async def test_wait_for_plus_returns_immediately_on_first_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = MagicMock()
    controller.find_template_on_device = AsyncMock(
        return_value={"x": 200, "y": 680, "confidence": 0.91}
    )
    sleep_calls: list[float] = []

    async def track_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(
        "imouse_farm.workflows.tiktok_plus_ready.asyncio.sleep",
        track_sleep,
    )
    assert await wait_for_tiktok_plus_visible(
        controller,
        "dev-1",
        templates_directory="config/templates",
        timeout_seconds=90.0,
        poll_seconds=2.0,
    )
    assert sleep_calls == []
    assert controller.find_template_on_device.await_count == 1


@pytest.mark.asyncio
async def test_wait_for_plus_uses_vision_after_two_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = MagicMock()
    controller.find_template_on_device = AsyncMock(return_value=None)
    app_config = MagicMock()

    dismiss = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "imouse_farm.workflows.vision_recovery.try_dismiss_blocking_popup",
        dismiss,
    )
    monkeypatch.setattr(
        "imouse_farm.workflows.tiktok_plus_ready.asyncio.sleep",
        AsyncMock(),
    )

    with pytest.raises(RuntimeError, match="\\+ button not visible"):
        await wait_for_tiktok_plus_visible(
            controller,
            "dev-1",
            app_config=app_config,
            templates_directory="config/templates",
            timeout_seconds=0.5,
            poll_seconds=0.1,
        )

    assert dismiss.await_count >= 1
    first = dismiss.await_args_list[0]
    assert first.args[0] is controller
    assert first.args[1] == "dev-1"
    assert first.kwargs["step_name"] == "wait_for_plus"
    assert first.kwargs["workflow_name"] == "tiktok"


@pytest.mark.asyncio
async def test_wait_for_plus_times_out() -> None:
    controller = MagicMock()
    controller.find_template_on_device = AsyncMock(return_value=None)
    with pytest.raises(RuntimeError, match="\\+ button not visible"):
        await wait_for_tiktok_plus_visible(
            controller,
            "dev-1",
            templates_directory="config/templates",
            timeout_seconds=0.2,
            poll_seconds=0.1,
        )
