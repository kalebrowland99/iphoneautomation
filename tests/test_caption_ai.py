"""Tests for AI caption helpers."""

from imouse_farm.captions.ai_generator import (
    append_hashtags,
    normalize_hashtags,
    resolve_hashtag_template,
    stem_to_food_name,
    _parse_posts_json,
)


def test_stem_to_food_name() -> None:
    assert stem_to_food_name("1-chicken_tikka_masala") == "Chicken Tikka Masala"
    assert stem_to_food_name("post-beef-burger") == "Beef"
    assert stem_to_food_name("slot-mac_and_cheese") == "Mac And Cheese"
    assert stem_to_food_name("chicken_tikka_masala") == ""
    assert stem_to_food_name("") == ""


def test_normalize_hashtags() -> None:
    assert normalize_hashtags("#fyp #food") == "#fyp #food"
    assert normalize_hashtags("fyp, food, recipe") == "#fyp #food #recipe"


def test_append_hashtags() -> None:
    result = append_hashtags("Great recipe!", "#fyp #food")
    assert result.endswith("#fyp #food")
    assert "Great recipe!" in result


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


def test_parse_posts_json_array() -> None:
    posts = _parse_posts_json('[{"onscreen": "Hi", "final": "Long"}]')
    assert posts[0]["onscreen"] == "Hi"


def test_parse_posts_json_object() -> None:
    posts = _parse_posts_json('{"posts": [{"onscreen": "A", "final": "B"}]}')
    assert len(posts) == 1
