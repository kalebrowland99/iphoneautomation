"""Tests for AI caption helpers."""

import random

from imouse_farm.captions.ai_generator import (
    append_hashtags,
    normalize_hashtags,
    resolve_hashtag_template,
    sanitize_caption_statements,
    stem_to_food_name,
    _parse_posts_json,
)


def test_stem_to_food_name() -> None:
    assert stem_to_food_name("1-chicken_tikka_masala") == "Chicken Tikka Masala"
    assert stem_to_food_name("post-beef-burger") == "Beef Burger"
    assert stem_to_food_name("slot-mac_and_cheese") == "Mac And Cheese"
    assert stem_to_food_name("02-cup-noodles-3") == "Cup Noodles"
    assert stem_to_food_name("slideshow-02-cup-noodles-3") == "Cup Noodles"
    assert stem_to_food_name("chicken_tikka_masala") == ""
    assert stem_to_food_name("") == ""


def test_normalize_hashtags() -> None:
    assert normalize_hashtags("#fyp #food") == "#fyp #food"
    assert normalize_hashtags("fyp, food, recipe") == "#fyp #food #recipe"


def test_append_hashtags() -> None:
    result = append_hashtags("Great recipe!", "#fyp #food")
    assert result.endswith("#fyp #food") or result.endswith("#food #fyp")
    assert "Great recipe!" in result


def test_sanitize_caption_statements() -> None:
    assert sanitize_caption_statements("did u know this? wild.") == "did u know this. wild."
    assert sanitize_caption_statements("no questions here") == "no questions here"


def test_hashtag_shuffle_preserves_tags() -> None:
    random.seed(0)
    shuffled = normalize_hashtags("#a #b #c #d", shuffle=True)
    assert sorted(shuffled.split()) == ["#a", "#b", "#c", "#d"]
    assert shuffled != "#a #b #c #d"


def test_resolve_hashtag_template() -> None:
    template = "#______ #toxic_____ #toxinfree #groceryshopping #cleaningredients"
    resolved = resolve_hashtag_template(template, "Chicken Tikka Masala")
    assert resolved == (
        "#chickentikkamasala #toxicchickentikkamasala "
        "#toxinfree #groceryshopping #cleaningredients"
    )
    assert resolve_hashtag_template(template, "") == (
        "#toxinfree #groceryshopping #cleaningredients"
    )
    assert resolve_hashtag_template(template, "unknown") == (
        "#toxinfree #groceryshopping #cleaningredients"
    )
    assert resolve_hashtag_template(template, "Post 2") == (
        "#toxinfree #groceryshopping #cleaningredients"
    )


def test_sanitize_food_name() -> None:
    from imouse_farm.captions.ai_generator import sanitize_food_name

    assert sanitize_food_name("Slideshow 02 3", "02-chips-1") == "Chips"
    assert sanitize_food_name("Cup Noodles", "02-cup-noodles-3") == "Cup Noodles"
    assert sanitize_food_name("", "02-cup-noodles-3") == "Cup Noodles"
    assert sanitize_food_name("Slideshow 02 3", "slideshow-02-3") == ""
    assert sanitize_food_name("unknown", "02-chips-1") == "Chips"
    assert sanitize_food_name("Unknown", "") == ""


def test_food_for_post_prefers_filename_over_unknown() -> None:
    from imouse_farm.captions.ai_generator import food_for_post

    assert food_for_post(extracted="unknown", response_food="", stem="02-chips-1") == "Chips"
    assert food_for_post(extracted="", response_food="unknown", stem="02-cup-noodles-3") == "Cup Noodles"


def test_stems_in_post_order() -> None:
    from imouse_farm.post.post_caption_store import stems_in_post_order

    file_stems = ["post3-food", "post2-food", "post1-food"]
    assert stems_in_post_order(file_stems) == ["post1-food", "post2-food", "post3-food"]


def test_foods_post_order_to_file_order() -> None:
    from imouse_farm.post.post_caption_store import foods_post_order_to_file_order

    by_post = ["P1", "P2", "P3"]
    by_file = foods_post_order_to_file_order(by_post)
    assert by_file[2] == "P1"
    assert by_file[1] == "P2"
    assert by_file[0] == "P3"


def test_parse_posts_json_array() -> None:
    posts = _parse_posts_json('[{"onscreen": "Hi", "final": "Long"}]')
    assert posts[0]["onscreen"] == "Hi"


def test_parse_foods_json() -> None:
    from imouse_farm.captions.ai_generator import _parse_foods_json

    foods = _parse_foods_json('{"foods": ["Chicken Tikka Masala", "Mac And Cheese", ""]}')
    assert foods == ["Chicken Tikka Masala", "Mac And Cheese", ""]


def test_food_label_from_response() -> None:
    from imouse_farm.captions.ai_generator import _food_label_from_response

    assert _food_label_from_response({"food": "Beef Burger"}, "1-beef", 1) == "Beef Burger"
    assert _food_label_from_response({}, "1-chicken_tikka_masala", 2) == "Chicken Tikka Masala"


def test_parse_onscreen_json() -> None:
    from imouse_farm.captions.ai_generator import _parse_onscreen_json

    lines = _parse_onscreen_json('{"onscreen": ["Line one", "Line two", "Line three"]}')
    assert lines == ["Line one", "Line two", "Line three"]


def test_parse_posts_json_object() -> None:
    posts = _parse_posts_json('{"posts": [{"onscreen": "A", "final": "B"}]}')
    assert len(posts) == 1
