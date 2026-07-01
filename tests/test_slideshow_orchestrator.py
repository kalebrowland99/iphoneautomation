"""Tests for autoslideshow automation URL params."""

from pathlib import Path

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
