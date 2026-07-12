"""Tests for onscreen text templates."""

import random

from imouse_farm.captions.onscreen_templates import (
    _edition_has_negative_wording,
    build_onscreen_text,
    build_varied_onscreen_text,
    build_varied_onscreen_texts,
    pick_hook_line1,
)


def test_build_onscreen_text_toxic_walmart() -> None:
    text = build_onscreen_text("toxic_walmart", "Chicken Tikka Masala")
    assert "Chicken Tikka Masala" in text
    assert "Walmart Edition" in text


def test_build_onscreen_text_america_sick() -> None:
    text = build_onscreen_text("america_sick", "Mac And Cheese")
    assert text == "This Is Why AMERICA IS SICK\nToxic Mac And Cheese Edition"


def test_build_onscreen_text_america_sick_capitalizes_food() -> None:
    text = build_onscreen_text("america_sick", "mac and cheese")
    assert text == "This Is Why AMERICA IS SICK\nToxic Mac and cheese Edition"


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


def test_varied_america_sick_shares_hook_across_posts() -> None:
    rng = random.Random(0)
    hook = pick_hook_line1("america_sick", rng=rng)
    texts = build_varied_onscreen_texts(
        "america_sick",
        ["chips", "noodles", "crackers"],
        rng=rng,
    )
    assert len(texts) == 3
    for text, food in zip(texts, ["Chips", "Noodles", "Crackers"], strict=True):
        assert text.startswith(hook)
        assert food in text.split("\n", 1)[1]
        assert "Edition" in text
        assert _edition_has_negative_wording(text.split("\n", 1)[1])
        assert " the " not in f" {text.lower()} "
        assert not text.lower().startswith("the ")


def test_varied_hooks_rotate_between_batches() -> None:
    hooks = {pick_hook_line1("america_sick") for _ in range(30)}
    assert len(hooks) > 1
    assert "This Is Why AMERICA IS SICK" in hooks


def test_varied_toxic_walmart_keeps_walmart_edition() -> None:
    text = build_varied_onscreen_text("toxic_walmart", "Frozen Pizza")
    assert "Frozen Pizza" in text.split("\n", 1)[0]
    assert text.endswith("Walmart Edition")


def test_varied_america_sick_edition_line_varies() -> None:
    rng = random.Random(7)
    editions = {
        build_varied_onscreen_text("america_sick", "Sugary Drinks", hook_line1="Hook", rng=rng).split("\n", 1)[1]
        for _ in range(12)
    }
    assert any("Sugary Drinks" in line for line in editions)
    assert len(editions) > 1
    assert all(_edition_has_negative_wording(line) for line in editions)
