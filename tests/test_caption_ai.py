"""Tests for AI caption helpers."""

from imouse_farm.captions.ai_generator import (
    append_hashtags,
    normalize_hashtags,
    stem_to_food_name,
    _parse_posts_json,
)


def test_stem_to_food_name() -> None:
    assert stem_to_food_name("chicken_tikka_masala") == "Chicken Tikka Masala"
    assert stem_to_food_name("beef-burger") == "Beef Burger"
    assert stem_to_food_name("") == ""


def test_normalize_hashtags() -> None:
    assert normalize_hashtags("#fyp #food") == "#fyp #food"
    assert normalize_hashtags("fyp, food, recipe") == "#fyp #food #recipe"


def test_append_hashtags() -> None:
    result = append_hashtags("Great recipe!", "#fyp #food")
    assert result.endswith("#fyp #food")
    assert "Great recipe!" in result


def test_parse_posts_json_array() -> None:
    posts = _parse_posts_json('[{"onscreen": "Hi", "final": "Long"}]')
    assert posts[0]["onscreen"] == "Hi"


def test_parse_posts_json_object() -> None:
    posts = _parse_posts_json('{"posts": [{"onscreen": "A", "final": "B"}]}')
    assert len(posts) == 1
