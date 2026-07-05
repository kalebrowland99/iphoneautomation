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
