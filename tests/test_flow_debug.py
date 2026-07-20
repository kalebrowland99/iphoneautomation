"""Tests for production-order debug pipeline."""

from imouse_farm.dashboard.flow_debug import (
    build_flow_debug_steps,
    build_post_draft_debug_steps,
    build_vpn_flow_debug_steps,
    flow_step_letter,
    resolve_flow_debug_test_id,
)
from imouse_farm.dashboard.test_actions import get_debug_registry, list_debug_tests


def test_flow_step_count() -> None:
    steps = build_flow_debug_steps()
    assert len(steps) == 147
    vpn_ids = [test_id for _label, test_id in steps if "vpn" in test_id]
    assert "prep-vpn-vision-ensure-on" in vpn_ids
    assert "prep-vpn-vision-ensure-off" in vpn_ids


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
    assert resolve_flow_debug_test_id("vpn:003:prep-vpn-vision-ensure-on") == (
        "prep-vpn-vision-ensure-on"
    )
    assert resolve_flow_debug_test_id("tap-plus") == "tap-plus"


def test_flow_step_letters() -> None:
    assert flow_step_letter(0) == "A"
    assert flow_step_letter(25) == "Z"
    assert flow_step_letter(26) == "27"


def test_vpn_flow_debug_steps() -> None:
    steps = build_vpn_flow_debug_steps()
    assert [test_id for _label, test_id in steps] == [
        "prep-open-shadowrocket",
        "prep-vpn-vision-analyze",
        "prep-vpn-vision-ensure-on",
        "prep-vpn-vision-ensure-off",
        "prep-vpn-off-before-album",
    ]
    registry = get_debug_registry()
    for _label, test_id in steps:
        assert test_id in registry, test_id


def test_vpn_flow_list() -> None:
    items = list_debug_tests("vpn")
    assert len(items) == 5
    assert items[0]["id"] == "vpn:001:prep-open-shadowrocket"
    assert items[0]["label"].startswith("A. ")
    assert items[-1]["test_id"] == "prep-vpn-off-before-album"
    assert resolve_flow_debug_test_id(items[2]["id"]) == "prep-vpn-vision-ensure-on"


def test_post_draft_debug_steps_omit_post_button() -> None:
    from imouse_farm.dashboard.test_actions import _ensure_draft_gallery_specs

    _ensure_draft_gallery_specs(1)
    steps = build_post_draft_debug_steps(video_count=1)
    ids = [test_id for _label, test_id in steps]
    assert ids[:2] == ["draft-download-videos", "tap-tiktok"]
    assert ids[-1] == "post-type-final-caption-1"
    assert "tap-post" not in ids
    assert "post-go-home" not in ids
    assert "draft-gallery-1-p1" in ids
    registry = get_debug_registry()
    for _label, test_id in steps:
        assert test_id in registry, test_id


def test_post_draft_debug_steps_three_videos_posts_until_last() -> None:
    from imouse_farm.dashboard.test_actions import _ensure_draft_gallery_specs

    _ensure_draft_gallery_specs(3)
    steps = build_post_draft_debug_steps(video_count=3)
    ids = [test_id for _label, test_id in steps]
    assert ids[0] == "draft-download-videos"
    assert ids[1] == "tap-tiktok"
    assert ids.count("tap-post") == 2
    assert ids[-1] == "post-type-final-caption-3"
    assert "draft-gallery-3-p1" in ids
    assert "draft-gallery-3-p3" in ids
    assert "post-go-home" not in ids


def test_post_draft_debug_steps_supplied_skips_onscreen_editor() -> None:
    from imouse_farm.dashboard.test_actions import _ensure_draft_gallery_specs

    _ensure_draft_gallery_specs(1)
    steps = build_post_draft_debug_steps(video_count=1, use_supplied_videos=True)
    ids = [test_id for _label, test_id in steps]
    assert ids[0] == "draft-download-videos"
    assert "post-tap-music" in ids
    assert "post-deselect-recommended-song" in ids
    assert "post-tap-favorites" not in ids
    assert "post-tap-hvitserk" not in ids
    assert "post-dismiss-music" in ids
    assert "post-tap-next-after-music-supplied" in ids
    assert "tap-continuearrow" not in ids
    assert "tap-aa" not in ids
    assert "post-drag-trim" not in ids
    assert "tap-editor" not in ids
    assert "post-tap-done" not in ids
    assert "post-type-final-caption-1" in ids
    assert "post-tap-next-editor-supplied" not in ids


def test_post_draft_list() -> None:
    items = list_debug_tests(
        "post_draft",
        slot="1",
        brand="labely",
        base_directory="gallery",
        media_extensions=[".mp4", ".mov"],
    )
    assert items
    assert items[0]["id"].startswith("draft:001:")
    assert items[0]["group"] == "post_draft"
    assert items[0]["video_count"] in {"1", "2", "3"}
    assert items[0]["label"].startswith("A. ")
    assert resolve_flow_debug_test_id(items[0]["id"]) == items[0]["test_id"]
