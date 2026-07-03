"""Tests for per-slot TikTok account profiles and run stickers."""

from __future__ import annotations

from pathlib import Path

import pytest

import imouse_farm.post.account_profile_store as store


@pytest.fixture(autouse=True)
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "account_profiles.json"
    monkeypatch.setattr(store, "ACCOUNT_PROFILES_PATH", path)
    store._store = {}
    yield
    store._store = {}
    if path.exists():
        path.unlink()


def test_normalize_handle_adds_at_prefix() -> None:
    assert store.normalize_handle("user123") == "@user123"
    assert store.normalize_handle("@user123") == "@user123"
    assert store.normalize_handle("") == ""


def test_set_profile_persists_handle_and_brand(tmp_path: Path) -> None:
    profile = store.set_profile("slot:3", tiktok_handle="myacct", brand="valcoin")
    assert profile["tiktok_handle"] == "@myacct"
    assert profile["brand"] == "valcoin"
    assert profile["warmup_enabled"] is False
    store._load_store()
    loaded = store.get_brand_profile("slot:3", "valcoin")
    assert loaded["tiktok_handle"] == "@myacct"
    assert loaded["brand"] == "valcoin"


def test_set_profile_persists_warmup_enabled() -> None:
    store.set_profile("slot:2", tiktok_handle="@acct", brand="labely", warmup_enabled=True)
    profile = store.get_brand_profile("slot:2", "labely")
    assert profile["warmup_enabled"] is True
    store.set_profile("slot:2", brand="labely", warmup_enabled=False)
    profile = store.get_brand_profile("slot:2", "labely")
    assert profile["warmup_enabled"] is False
    assert profile["tiktok_handle"] == "@acct"


def test_same_slot_different_brands() -> None:
    store.set_profile("slot:1", tiktok_handle="@labelyacct", brand="labely")
    store.set_profile("slot:1", tiktok_handle="@valcoinacct", brand="valcoin")
    labely = store.get_brand_profile("slot:1", "labely")
    valcoin = store.get_brand_profile("slot:1", "valcoin")
    assert labely["tiktok_handle"] == "@labelyacct"
    assert valcoin["tiktok_handle"] == "@valcoinacct"


def test_mark_run_lifecycle() -> None:
    key = "slot:1"
    store.set_profile(key, tiktok_handle="@a", brand="labely")
    store.mark_run_started(key, brand="labely")
    p = store.get_brand_profile(key, "labely")
    assert p["last_run_status"] == "running"
    assert p["posts_completed"] == 0

    store.mark_post_completed(key, 2, brand="labely")
    p = store.get_brand_profile(key, "labely")
    assert p["posts_completed"] == 2

    store.mark_run_success(key, posts_completed=3, brand="labely")
    p = store.get_brand_profile(key, "labely")
    assert p["last_run_status"] == "success"
    assert p["posts_completed"] == 3


def test_list_profiles_filters_by_brand() -> None:
    store.set_profile("slot:1", tiktok_handle="@l", brand="labely")
    store.set_profile("slot:2", tiktok_handle="@v", brand="valcoin")
    labely = store.list_profiles(brand="labely")
    valcoin = store.list_profiles(brand="valcoin")
    assert "slot:1" in labely
    assert "slot:2" not in labely
    assert "slot:2" in valcoin
    assert "slot:1" not in valcoin


def test_handle_match_queries_variants() -> None:
    queries = store.handle_match_queries("@TestUser")
    assert "@TestUser" in queries
    assert "TestUser" in queries


def test_reset_last_run_state_clears_sticker_fields() -> None:
    key = "slot:4"
    store.mark_run_success(key, posts_completed=3, brand="labely")
    store.mark_prep_completed(key, brand="labely")

    store.reset_last_run_state(key, brand="labely")
    profile = store.get_brand_profile(key, "labely")

    assert profile["last_run_status"] == "idle"
    assert profile["last_run_at"] is None
    assert profile["last_error"] == ""
    assert profile["posts_completed"] == 0
    assert profile["prep_completed_at"] is not None


def test_reset_all_session_states_clears_prep_and_last_run() -> None:
    store.mark_run_failed("slot:2", message="boom", brand="valcoin")
    store.mark_prep_completed("slot:2", brand="valcoin")

    cleared = store.reset_all_session_states(farm_slots=3)

    assert cleared == ["1", "2", "3"]
    profile = store.get_brand_profile("slot:2", "valcoin")
    assert profile["last_run_status"] == "idle"
    assert profile["last_run_at"] is None
    assert profile["prep_completed_at"] is None
