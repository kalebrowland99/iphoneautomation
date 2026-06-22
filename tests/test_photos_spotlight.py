"""Tests for Photos Spotlight open flow with retry."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from imouse_farm.actions.photos_spotlight import (
    close_photos_app,
    open_photos_via_spotlight,
    photos_is_open,
    run_spotlight_open_sequence,
)
from imouse_farm.config.models import ActionType, AppConfig


@pytest.fixture
def config(tmp_path: Path) -> AppConfig:
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "photos.jpg").write_bytes(b"fake")
    cfg = AppConfig()
    cfg.analysis.templates_directory = str(templates)
    return cfg


@pytest.mark.asyncio
async def test_run_spotlight_open_sequence_stops_on_swipe_failure() -> None:
    calls: list[str] = []

    async def execute(action_type: ActionType, params: dict, step_name: str) -> bool:
        calls.append(action_type.value)
        return action_type != ActionType.SWIPE

    ok = await run_spotlight_open_sequence(execute, step_prefix="test")
    assert not ok
    assert calls == ["swipe"]


@pytest.mark.asyncio
async def test_open_photos_retries_after_verify_failure(config: AppConfig) -> None:
    controller = AsyncMock()
    controller.press_home = AsyncMock(return_value=True)
    controller.find_template_on_device = AsyncMock(return_value=None)

    attempt = 0

    async def execute(action_type: ActionType, params: dict, step_name: str) -> bool:
        nonlocal attempt
        if action_type == ActionType.HOME:
            attempt += 1
        return True

    ok = await open_photos_via_spotlight(
        execute,
        controller,
        config,
        "device-1",
        step_prefix="test",
        max_attempts=2,
        load_wait_seconds=0,
    )
    assert not ok
    assert attempt == 2
    controller.press_home.assert_awaited()


@pytest.mark.asyncio
async def test_open_photos_succeeds_on_second_attempt(config: AppConfig) -> None:
    controller = AsyncMock()
    controller.press_home = AsyncMock(return_value=True)
    verify_calls = 0

    async def find_template(*_args, **_kwargs):
        nonlocal verify_calls
        verify_calls += 1
        return {"x": 1, "y": 1, "confidence": 0.9} if verify_calls >= 2 else None

    controller.find_template_on_device = AsyncMock(side_effect=find_template)

    async def execute(action_type: ActionType, params: dict, step_name: str) -> bool:
        return True

    ok = await open_photos_via_spotlight(
        execute,
        controller,
        config,
        "device-1",
        step_prefix="test",
        max_attempts=2,
        load_wait_seconds=0,
    )
    assert ok
    assert verify_calls >= 2


@pytest.mark.asyncio
async def test_close_photos_double_home_when_still_open(config: AppConfig) -> None:
    controller = AsyncMock()
    controller.press_home = AsyncMock(return_value=True)
    controller.find_template_on_device = AsyncMock(
        side_effect=[{"x": 1, "y": 1, "confidence": 0.9}, None]
    )

    await close_photos_app(controller, config, "device-1")
    assert controller.press_home.await_count == 2


@pytest.mark.asyncio
async def test_photos_is_open(config: AppConfig) -> None:
    controller = AsyncMock()
    controller.find_template_on_device = AsyncMock(return_value={"x": 0, "y": 0})
    assert await photos_is_open(controller, config, "device-1")

    controller.find_template_on_device = AsyncMock(return_value=None)
    assert not await photos_is_open(controller, config, "device-1")
