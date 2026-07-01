"""Tests for in-workflow caption auto-generation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from imouse_farm.config.models import AppConfig, OpenAICaptionConfig, SlideshowConfig, WorkflowConfig
from imouse_farm.workflows.engine import WorkflowRunner


def _runner(*, auto_captions: bool = True) -> WorkflowRunner:
    config = AppConfig(
        openai=OpenAICaptionConfig(enabled=True),
        slideshow=SlideshowConfig(auto_generate_captions=auto_captions),
    )
    return WorkflowRunner(
        workflow=WorkflowConfig(name="tiktok_post", steps=[]),
        device_id="dev-1",
        config=config,
        device_manager=MagicMock(),
        screenshot_service=MagicMock(),
        vision=MagicMock(),
        popup_manager=MagicMock(),
        state_machine=MagicMock(),
        action_engine=MagicMock(),
        db=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_ensure_post_captions_always_generates() -> None:
    runner = _runner()
    runner._device_manager.get_device.return_value = MagicMock(user_name="1", phone_name="p")
    runner._log_activity = AsyncMock()
    runner._refresh_post_variables = MagicMock()

    with patch(
        "imouse_farm.workflows.engine.get_onscreen_text",
        return_value="on screen",
    ), patch(
        "imouse_farm.workflows.engine.get_final_caption",
        return_value="final caption",
    ), patch(
        "imouse_farm.captions.service.generate_captions_for_device",
        new_callable=AsyncMock,
    ) as generate:
        await runner._ensure_post_captions(1)
        generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_post_captions_once_per_post_per_iteration() -> None:
    runner = _runner()
    runner._device_manager.get_device.return_value = MagicMock(user_name="1", phone_name="p")
    runner._log_activity = AsyncMock()
    runner._refresh_post_variables = MagicMock()

    with patch(
        "imouse_farm.workflows.engine.get_onscreen_text",
        return_value="on screen",
    ), patch(
        "imouse_farm.workflows.engine.get_final_caption",
        return_value="final caption",
    ), patch(
        "imouse_farm.captions.service.generate_captions_for_device",
        new_callable=AsyncMock,
    ) as generate:
        await runner._ensure_post_captions(2)
        await runner._ensure_post_captions(2)
        generate.assert_awaited_once()
