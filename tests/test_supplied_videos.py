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
    get_batch_size,
    get_use_supplied_videos,
    set_batch_size,
    set_use_supplied_videos,
)
from imouse_farm.utils.supplied_videos import (
    distribute_supplied_videos,
    list_supplied_videos,
    save_supplied_video,
    supplied_videos_status,
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
    rs._store = {
        "use_supplied_videos": False,
        "use_supplied_videos_by_brand": {"labely": False, "valcoin": False},
        "batch_size": 2,
    }
    set_use_supplied_videos(True, brand="labely")
    assert get_use_supplied_videos("labely") is True
    assert get_use_supplied_videos("valcoin") is False
    assert (tmp_path / "run_settings.json").is_file()
    set_use_supplied_videos(True, brand="valcoin")
    assert get_use_supplied_videos("valcoin") is True
    set_use_supplied_videos(False, brand="valcoin")
    assert get_use_supplied_videos("valcoin") is False
    assert get_use_supplied_videos("labely") is True


def test_run_settings_batch_size(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from imouse_farm.settings import run_settings as rs

    monkeypatch.setattr(rs, "RUN_SETTINGS_PATH", tmp_path / "run_settings.json")
    rs._store = {
        "use_supplied_videos": False,
        "use_supplied_videos_by_brand": {"labely": False, "valcoin": False},
        "batch_size": 2,
    }
    set_batch_size(4)
    assert get_batch_size() == 4
    set_batch_size(0)
    assert get_batch_size() == 1
    set_batch_size(99)
    assert get_batch_size() == 20
    saved = (tmp_path / "run_settings.json").read_text(encoding="utf-8")
    assert '"batch_size": 20' in saved


def test_run_settings_brands_are_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from imouse_farm.settings import run_settings as rs

    monkeypatch.setattr(rs, "RUN_SETTINGS_PATH", tmp_path / "run_settings.json")
    rs._store = {
        "use_supplied_videos": True,
        "use_supplied_videos_by_brand": {"labely": True, "valcoin": True},
        "batch_size": 2,
    }
    set_use_supplied_videos(False, brand="valcoin")
    assert get_use_supplied_videos("labely") is True
    assert get_use_supplied_videos("valcoin") is False
    settings = rs.get_run_settings()
    assert settings["use_supplied_videos_by_brand"]["labely"] is True
    assert settings["use_supplied_videos_by_brand"]["valcoin"] is False


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


def _save_three_labely(base: Path) -> None:
    from unittest.mock import patch

    with patch(
        "imouse_farm.utils.supplied_videos.validate_slideshow_video",
        return_value=(True, ""),
    ):
        for name in ("a.mp4", "b.mp4", "c.mp4"):
            save_supplied_video(
                b"x" * 2048,
                base_directory=str(base),
                brand="labely",
                filename=name,
                max_count=3,
            )


def test_distribute_removes_stale_video_in_branded_folder(tmp_path: Path) -> None:
    """An old unprefixed video must not ride along after the fresh 01_..03_ set."""
    base = tmp_path / "gallery"
    _save_three_labely(base)
    # Pre-seed a leftover from a previous day; its name sorts AFTER 01_..03_.
    stale_dir = base / "7" / "labely"
    stale_dir.mkdir(parents=True, exist_ok=True)
    (stale_dir / "slideshow.mp4").write_bytes(b"old" * 1024)

    distribute_supplied_videos(str(base), ["7"], brand="labely", expected_count=3)

    names = sorted(p.name for p in stale_dir.glob("*.mp4"))
    assert names == ["01_a.mp4", "02_b.mp4", "03_c.mp4"]
    assert not (stale_dir / "slideshow.mp4").exists()


def test_distribute_removes_legacy_root_video_and_keeps_other_brand(tmp_path: Path) -> None:
    base = tmp_path / "gallery"
    _save_three_labely(base)
    slot_root = base / "8"
    slot_root.mkdir(parents=True, exist_ok=True)
    # Legacy labely location (slot root) + a valcoin sibling that must survive.
    (slot_root / "yesterday.mp4").write_bytes(b"old" * 1024)
    valcoin_dir = slot_root / "valcoin"
    valcoin_dir.mkdir(parents=True, exist_ok=True)
    (valcoin_dir / "keep.mp4").write_bytes(b"coin" * 1024)

    distribute_supplied_videos(str(base), ["8"], brand="labely", expected_count=3)

    # Legacy root video purged; canonical destination is the branded subfolder.
    assert not (slot_root / "yesterday.mp4").exists()
    assert sorted(p.name for p in (slot_root / "labely").glob("*.mp4")) == [
        "01_a.mp4",
        "02_b.mp4",
        "03_c.mp4",
    ]
    # Other brand is untouched.
    assert (valcoin_dir / "keep.mp4").exists()


def test_distribute_accepts_one_video(tmp_path: Path) -> None:
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
            filename="solo.mp4",
            max_count=3,
        )
    status = supplied_videos_status(str(base), brand="labely", expected_count=3)
    assert status["count"] == 1
    assert status["ready"] is True
    result = distribute_supplied_videos(
        str(base),
        ["9"],
        brand="labely",
        expected_count=3,
    )
    assert result["video_count"] == 1
    assert len(list(Path(result["slots"][0]["folder"]).glob("*.mp4"))) == 1
