"""Tests for onscreen text templates."""

from imouse_farm.captions.onscreen_templates import build_onscreen_text


def test_build_onscreen_text_toxic_walmart() -> None:
    text = build_onscreen_text("toxic_walmart", "Chicken Tikka Masala")
    assert "Chicken Tikka Masala" in text
    assert "Walmart Edition" in text


def test_build_onscreen_text_america_sick() -> None:
    text = build_onscreen_text("america_sick", "Mac And Cheese")
    assert text == "This Is Why AMERICA IS SICK\nMac And Cheese Edition"


def test_build_onscreen_text_america_sick_capitalizes_food() -> None:
    text = build_onscreen_text("america_sick", "mac and cheese")
    assert text == "This Is Why AMERICA IS SICK\nMac and cheese Edition"


def test_apply_onscreen_maps_file_order_to_workflow_posts() -> None:
    from imouse_farm.captions.onscreen_templates import apply_onscreen_for_foods

    saved: dict[int, str] = {}

    def _save(_key: str, post: int, text: str) -> None:
        saved[post] = text

    # File order: post 3, post 2, post 1 foods
    foods = ["Left Food", "Middle Food", "Right Food"]
    applied = apply_onscreen_for_foods(
        "toxic_walmart",
        foods,
        "device-a",
        set_onscreen_text=_save,
    )
    assert applied == 3
    assert "Right Food" in saved[1]
    assert "Middle Food" in saved[2]
    assert "Left Food" in saved[3]
