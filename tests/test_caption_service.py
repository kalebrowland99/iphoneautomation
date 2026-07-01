"""Tests for caption service hashtag resolution."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from imouse_farm.captions import prompt_store
from imouse_farm.captions.service import generate_captions_for_device
from imouse_farm.config.models import AppConfig, OpenAICaptionConfig


@pytest.mark.asyncio
async def test_generate_uses_default_hashtags_when_explicit_empty(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "caption_ai_settings.json"
    monkeypatch.setattr(prompt_store, "CAPTION_AI_SETTINGS_PATH", path)
    monkeypatch.setattr(prompt_store, "_settings", {
        brand: dict(values)
        for brand, values in prompt_store._BRAND_DEFAULTS.items()
    })

    config = AppConfig(openai=OpenAICaptionConfig(enabled=True, api_key="test-key"))
    device = MagicMock(device_id="dev-1", user_name="1", phone_name="phone", display_label="Phone 1")

    captured: dict[str, str] = {}

    async def fake_generate_post_captions(
        food_names,
        *,
        media_stems=None,
        user_prompt,
        hashtags,
        config,
    ):
        captured["hashtags"] = hashtags
        return [{"food": "Chips", "final": "caption"}]

    with patch(
        "imouse_farm.captions.service.extract_food_names_from_stems",
        new=AsyncMock(return_value=["Chips", "", ""]),
    ), patch(
        "imouse_farm.captions.service.generate_post_captions",
        side_effect=fake_generate_post_captions,
    ), patch(
        "imouse_farm.captions.service.generate_labely_onscreen_texts",
        new=AsyncMock(return_value=["Line 1", "Line 2", "Line 3"]),
    ), patch(
        "imouse_farm.captions.service._gallery_stems",
        return_value=["02-chips-1", "02-chicken-2", "02-crackers-3"],
    ):
        await generate_captions_for_device(
            config,
            device,
            hashtags="",
            onscreen_template="america_sick",
            brand="labely",
        )

    assert captured["hashtags"] == prompt_store.DEFAULT_AI_HASHTAGS
