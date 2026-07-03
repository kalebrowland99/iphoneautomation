"""Tests for autoslideshow automation URL params."""

from pathlib import Path

import pytest

from imouse_farm.config.loader import load_config
from imouse_farm.integrations.slideshow_jobs import SlideshowJobStore
from imouse_farm.integrations.slideshow_orchestrator import SlideshowOrchestrator
from imouse_farm.utils.env_file import load_env_file


def _orchestrator() -> SlideshowOrchestrator:
    load_env_file(Path(".env"))
    cfg = load_config("config/config.yaml")
    return SlideshowOrchestrator(
        cfg.slideshow,
        cfg,
        SlideshowJobStore(),
        None,
        None,
        "localhost",
        8080,
    )


def test_labely_url_uses_scan_count_not_slideshows_per_slot() -> None:
    url = _orchestrator().automation_url("t", "labely", ["2"], videos_per_slot=3)
    assert "slideshowsPerSlot=3" in url
    assert "labelyScanSlotCount=3" in url


def test_valcoin_url_uses_slides_per_slideshow_not_slideshows_per_slot() -> None:
    url = _orchestrator().automation_url("t", "valcoin", ["2"], videos_per_slot=3)
    assert "slideshowsPerSlot=1" in url
    assert "slidesPerSlideshow=3" in url


def test_debug_override_single_video() -> None:
    url = _orchestrator().automation_url("t", "valcoin", ["2"], videos_per_slot=1)
    assert "slidesPerSlideshow=1" in url


@pytest.mark.asyncio
async def test_generate_captions_for_slot_runs_after_gallery_exists(monkeypatch) -> None:
    from unittest.mock import AsyncMock, MagicMock

    orch = _orchestrator()
    orch._config.auto_generate_captions = True
    device = MagicMock(user_name="2", device_id="dev-2")

    generate = AsyncMock(return_value={"generated": 1, "errors": []})
    monkeypatch.setattr(
        "imouse_farm.integrations.slideshow_orchestrator.generate_captions_for_devices",
        generate,
    )
    orch._jobs.update = AsyncMock()

    ok = await orch._generate_captions_for_slot(
        "job-1",
        device,
        brand="labely",
        slot_index=1,
        slot_total=3,
    )

    assert ok is True
    generate.assert_awaited_once()
    assert generate.await_args.kwargs["brand"] == "labely"
    assert generate.await_args.args[1] == [device]
