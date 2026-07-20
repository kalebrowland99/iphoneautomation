"""Tests for ValCoin warmup retry behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from imouse_farm.config.loader import load_config
from imouse_farm.workflows import warmup as warmup_mod


@pytest.mark.asyncio
async def test_valcoin_warmup_retries_after_account_switch_failure(monkeypatch) -> None:
    cfg = load_config("config/config.yaml")
    cfg.batch.warmup.max_retry_attempts = 2
    device = SimpleNamespace(device_id="dev-1", user_name="13", screen_width=375, screen_height=667)
    controller = AsyncMock()
    controller.kill_app = AsyncMock(return_value=True)
    controller.press_home = AsyncMock(return_value=True)
    controller.tap = AsyncMock(return_value=True)
    controller.ocr_on_device = AsyncMock(return_value=[])

    calls = {"ensure": 0}

    async def fake_ensure(*_args, **_kwargs) -> None:
        calls["ensure"] += 1
        if calls["ensure"] < 2:
            raise RuntimeError("Could not find @fred in account dropdown via OCR")

    monkeypatch.setattr(warmup_mod, "ensure_tiktok_account", fake_ensure)
    monkeypatch.setattr(warmup_mod, "_reopen_tiktok_for_warmup_retry", AsyncMock())
    monkeypatch.setattr(warmup_mod, "_run_warmup_scroll", AsyncMock())
    monkeypatch.setattr(warmup_mod, "_teardown_after_warmup", AsyncMock())

    await warmup_mod.run_tiktok_warmup(
        controller,
        device,
        brand="valcoin",
        app_config=cfg,
        after_labely=True,
    )

    assert calls["ensure"] == 2
    warmup_mod._reopen_tiktok_for_warmup_retry.assert_awaited_once()
    warmup_mod._run_warmup_scroll.assert_awaited_once()


@pytest.mark.asyncio
async def test_warmup_scroll_taps_home_every_few_swipes(monkeypatch) -> None:
    from imouse_farm.workflows import feed_scroll

    cfg = load_config("config/config.yaml")
    cfg.batch.warmup.duration_seconds = 30
    cfg.batch.warmup.swipe_delay_min_seconds = 0
    cfg.batch.warmup.swipe_delay_max_seconds = 0.01
    cfg.batch.warmup.swipe_delay_mean_seconds = 0.01
    cfg.batch.warmup.swipe_delay_long_watch_probability = 0
    device = SimpleNamespace(
        device_id="dev-1", user_name="5", screen_width=406, screen_height=720
    )
    controller = AsyncMock()
    controller.tap = AsyncMock(return_value=True)
    controller.ocr_on_device = AsyncMock(return_value="")

    swipe_n = {"n": 0}

    async def fake_swipe(*_args, **_kwargs):
        swipe_n["n"] += 1
        return {"sx": 200, "sy": 500, "ex": 200, "ey": 200}

    monkeypatch.setattr(feed_scroll, "swipe_feed_up", fake_swipe)
    monkeypatch.setattr(warmup_mod, "increment_warmup_days", lambda *_a, **_k: 1)
    monkeypatch.setattr(feed_scroll.random, "randint", lambda a, b: 3)
    monkeypatch.setattr(feed_scroll.random, "uniform", lambda a, b: 9999)
    monkeypatch.setattr(feed_scroll.random, "random", lambda: 1.0)
    monkeypatch.setattr(feed_scroll.random, "expovariate", lambda _x: 0.01)
    monkeypatch.setattr(feed_scroll.asyncio, "sleep", AsyncMock())

    await warmup_mod._run_warmup_scroll(
        controller,
        device,
        brand="valcoin",
        app_config=cfg,
        log_activity=None,
        duration_override=0.25,
        stop_check=lambda: False,
    )

    home_x = cfg.tiktok_navigation.home_tab_x
    home_y = cfg.tiktok_navigation.home_tab_y
    home_taps = [
        c for c in controller.tap.await_args_list if c.args[1:] == (home_x, home_y)
    ]
    assert swipe_n["n"] >= 3
    assert len(home_taps) >= 1


@pytest.mark.asyncio
async def test_warmup_vpn_on_does_not_reset_phone_on_failure(monkeypatch) -> None:
    cfg = load_config("config/config.yaml")
    controller = AsyncMock()
    device_manager = AsyncMock()
    device_manager.reset_phone_and_recast = AsyncMock()

    async def fail_ensure(*_a, **_k):
        raise RuntimeError(
            "VPN vision confirmed OFF, expected ON"
        )

    monkeypatch.setattr(warmup_mod, "ensure_vpn_on", fail_ensure)

    with pytest.raises(RuntimeError, match="expected ON"):
        await warmup_mod._ensure_vpn_on(
            controller,
            "dev-1",
            cfg,
            None,
            device_manager=device_manager,
        )

    device_manager.reset_phone_and_recast.assert_not_awaited()


@pytest.mark.asyncio
async def test_warmup_teardown_vpn_off_failure_does_not_raise(monkeypatch) -> None:
    cfg = load_config("config/config.yaml")
    controller = AsyncMock()

    async def fail_off(*_a, **_k):
        raise RuntimeError(
            "VPN vision confirmed ON, expected OFF"
        )

    monkeypatch.setattr(warmup_mod, "ensure_vpn_off", fail_off)
    await warmup_mod._teardown_after_warmup(controller, "dev-1", cfg, None)


@pytest.mark.asyncio
async def test_open_tiktok_for_warmup_always_taps_icon_after_vpn(monkeypatch) -> None:
    cfg = load_config("config/config.yaml")
    controller = AsyncMock()
    controller.press_home = AsyncMock(return_value=True)
    controller.tap = AsyncMock(return_value=True)
    # Real DeviceController has press_home, not home — guard against regressions.
    del controller.home
    device_manager = AsyncMock()

    monkeypatch.setattr(warmup_mod, "_ensure_vpn_on", AsyncMock())
    wait_plus = AsyncMock(return_value=0.9)
    monkeypatch.setattr(warmup_mod, "wait_for_tiktok_plus_visible", wait_plus)

    await warmup_mod._open_tiktok_for_warmup(
        controller,
        "dev-1",
        app_config=cfg,
        log_activity=None,
        device_manager=device_manager,
    )

    warmup_mod._ensure_vpn_on.assert_awaited_once()
    controller.press_home.assert_awaited_once_with("dev-1")
    controller.tap.assert_awaited_once_with("dev-1", 507, 1011)
    wait_plus.assert_awaited_once()


@pytest.mark.asyncio
async def test_valcoin_warmup_raises_after_max_retries(monkeypatch) -> None:
    cfg = load_config("config/config.yaml")
    cfg.batch.warmup.max_retry_attempts = 2
    device = SimpleNamespace(device_id="dev-1", user_name="13", screen_width=375, screen_height=667)
    controller = AsyncMock()

    async def always_fail(*_args, **_kwargs) -> None:
        raise RuntimeError("account switch failed")

    monkeypatch.setattr(warmup_mod, "ensure_tiktok_account", always_fail)
    monkeypatch.setattr(warmup_mod, "_reopen_tiktok_for_warmup_retry", AsyncMock())
    monkeypatch.setattr(warmup_mod, "_run_warmup_scroll", AsyncMock())

    with pytest.raises(RuntimeError, match="account switch failed"):
        await warmup_mod.run_tiktok_warmup(
            controller,
            device,
            brand="valcoin",
            app_config=cfg,
            after_labely=True,
        )

    assert warmup_mod._reopen_tiktok_for_warmup_retry.await_count == 1
    warmup_mod._run_warmup_scroll.assert_not_awaited()
