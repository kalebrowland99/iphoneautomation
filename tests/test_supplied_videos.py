"""Tests for supplied-video run mode."""

from __future__ import annotations

from pathlib import Path

import pytest

from imouse_farm.config.models import WorkflowStepConfig
from imouse_farm.post.post_caption_store import (
    clear_all_post_texts,
    set_final_caption,
    set_onscreen_text,
    validate_post_texts,
)
from imouse_farm.settings.run_settings import (
    get_use_supplied_videos,
    set_use_supplied_videos,
)
from imouse_farm.utils.supplied_videos import (
    distribute_supplied_videos,
    list_supplied_videos,
    save_supplied_video,
)


def test_workflow_step_supplied_video_fields_exist() -> None:
    skip = WorkflowStepConfig(
        type="execute_action",
        name="tap_music_gallery",
        unless_use_supplied_videos=True,
    )
    include = WorkflowStepConfig(
        type="wait",
        name="after_media_supplied",
        when_use_supplied_videos=True,
    )
    assert skip.unless_use_supplied_videos is True
    assert include.when_use_supplied_videos is True


def test_validate_post_texts_can_skip_onscreen() -> None:
    key = "slot:99:labely"
    clear_all_post_texts(key, brand="labely")
    set_final_caption(key, 1, "caption one", brand="labely")
    set_final_caption(key, 2, "caption two", brand="labely")
    set_final_caption(key, 3, "caption three", brand="labely")
    assert validate_post_texts(key, brand="labely", require_onscreen=True)
    assert not validate_post_texts(key, brand="labely", require_onscreen=False)


def test_run_settings_toggle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from imouse_farm.settings import run_settings as rs

    monkeypatch.setattr(rs, "RUN_SETTINGS_PATH", tmp_path / "run_settings.json")
    rs._store = {"use_supplied_videos": False}
    set_use_supplied_videos(True)
    assert get_use_supplied_videos() is True
    assert (tmp_path / "run_settings.json").is_file()
    set_use_supplied_videos(False)
    assert get_use_supplied_videos() is False


def test_distribute_copies_to_slots(tmp_path: Path) -> None:
    # Minimal non-blank fake video: validate_slideshow_video needs a real readable MP4.
    # Skip deep validation here by writing via save after patching validate.
    from unittest.mock import patch

    base = tmp_path / "gallery"
    with patch(
        "imouse_farm.utils.supplied_videos.validate_slideshow_video",
        return_value=(True, ""),
    ):
        save_supplied_video(
            b"x" * 2048,
            base_directory=str(base),
            brand="labely",
            filename="a.mp4",
            max_count=3,
        )
        save_supplied_video(
            b"y" * 2048,
            base_directory=str(base),
            brand="labely",
            filename="b.mp4",
            max_count=3,
        )
        save_supplied_video(
            b"z" * 2048,
            base_directory=str(base),
            brand="labely",
            filename="c.mp4",
            max_count=3,
        )
    assert len(list_supplied_videos(str(base), brand="labely")) == 3
    result = distribute_supplied_videos(
        str(base),
        ["7", "8"],
        brand="labely",
        expected_count=3,
    )
    assert len(result["slots"]) == 2
    for slot_info in result["slots"]:
        folder = Path(slot_info["folder"])
        assert folder.is_dir()
        assert len(list(folder.glob("*.mp4"))) == 3
