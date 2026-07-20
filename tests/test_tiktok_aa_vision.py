"""Tests for TikTok Aa + editor toolbar vision locate helpers."""

from __future__ import annotations

import pytest

from imouse_farm.config.models import AppConfig, OpenAICaptionConfig
from imouse_farm.workflows.tiktok_aa_vision import (
    AA_VISION_MODEL_DEFAULT,
    EDITOR_FALLBACK_XY,
    _validate_aa_coords,
    _validate_editor_coords,
    aa_vision_model,
    clear_saved_editor_coords,
    editor_tap_coords,
    editor_template_path,
    load_editor_template_b64,
    parse_aa_editor_coords,
    save_editor_coords,
)


def test_aa_vision_model_default_and_override() -> None:
    assert aa_vision_model(AppConfig()) == AA_VISION_MODEL_DEFAULT
    cfg = AppConfig(openai=OpenAICaptionConfig(aa_vision_model="gpt-4o"))
    assert aa_vision_model(cfg) == "gpt-4o"


def test_validate_aa_coords_accepts_right_toolbar() -> None:
    _validate_aa_coords(560, 400, 608, 1080)


def test_validate_aa_coords_rejects_left_and_extreme_y() -> None:
    with pytest.raises(RuntimeError, match="too far left"):
        _validate_aa_coords(100, 400, 608, 1080)
    with pytest.raises(RuntimeError, match="outside typical"):
        _validate_aa_coords(560, 50, 608, 1080)
    with pytest.raises(RuntimeError, match="outside typical"):
        _validate_aa_coords(560, 900, 608, 1080)


def test_parse_aa_editor_coords() -> None:
    aa_x, aa_y, ed_x, ed_y = parse_aa_editor_coords(
        "AA_X: 566\nAA_Y: 422\nEDITOR_X: 568\nEDITOR_Y: 247\n"
    )
    assert (aa_x, aa_y, ed_x, ed_y) == (566, 422, 568, 247)


def test_parse_aa_editor_coords_rejects_xy_only() -> None:
    with pytest.raises(RuntimeError, match="AA_X/AA_Y"):
        parse_aa_editor_coords("X: 566\nY: 422\n")


def test_validate_editor_coords_must_be_above_aa() -> None:
    _validate_editor_coords(566, 247, aa_x=566, aa_y=422, width=608, height=1080)
    with pytest.raises(RuntimeError, match="not clearly above"):
        _validate_editor_coords(566, 430, aa_x=566, aa_y=422, width=608, height=1080)
    with pytest.raises(RuntimeError, match="Settings-gear|outside typical"):
        _validate_editor_coords(566, 68, aa_x=566, aa_y=422, width=608, height=1080)


def test_editor_coords_store_and_fallback() -> None:
    clear_saved_editor_coords()
    x, y, source = editor_tap_coords("dev-1")
    assert (x, y) == EDITOR_FALLBACK_XY
    assert source == "fallback"
    save_editor_coords("dev-1", 570, 250)
    x, y, source = editor_tap_coords("dev-1")
    assert (x, y, source) == (570, 250, "vision_saved")
    clear_saved_editor_coords("dev-1")
    assert editor_tap_coords("dev-1")[2] == "fallback"


def test_editor_template_loads_from_config_templates() -> None:
    cfg = AppConfig()
    path = editor_template_path(cfg)
    assert path.name == "editor.jpg"
    assert path.is_file(), f"missing editor template at {path}"
    b64 = load_editor_template_b64(cfg)
    assert b64 and len(b64) > 100
