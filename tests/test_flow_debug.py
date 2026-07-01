"""Tests for production-order debug pipeline."""

from imouse_farm.dashboard.flow_debug import (
    build_flow_debug_steps,
    flow_step_letter,
    resolve_flow_debug_test_id,
)
from imouse_farm.dashboard.test_actions import get_debug_registry, list_debug_tests


def test_flow_step_count() -> None:
    steps = build_flow_debug_steps()
    assert len(steps) == 159


def test_all_flow_steps_registered() -> None:
    registry = get_debug_registry()
    for _label, test_id in build_flow_debug_steps():
        assert test_id in registry, test_id


def test_flow_list_unique_ids() -> None:
    items = list_debug_tests("flow")
    ids = [item["id"] for item in items]
    assert len(ids) == len(set(ids))
    assert ids[0].startswith("flow:001:")
    assert items[0]["label"].startswith("A. ")


def test_resolve_flow_debug_test_id() -> None:
    assert resolve_flow_debug_test_id("flow:042:tap-plus") == "tap-plus"
    assert resolve_flow_debug_test_id("tap-plus") == "tap-plus"


def test_flow_step_letters() -> None:
    assert flow_step_letter(0) == "A"
    assert flow_step_letter(25) == "Z"
    assert flow_step_letter(26) == "27"
