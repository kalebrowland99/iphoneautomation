"""Per-slot TikTok UI overrides (e.g. alternate account switcher layout)."""

from __future__ import annotations

from imouse_farm.config.models import AppConfig, TabCoord, TikTokDeviceUiSlotConfig


def slot_ui_config(
    app_config: AppConfig | None,
    device_user_name: str,
) -> TikTokDeviceUiSlotConfig | None:
    slot = str(device_user_name or "").strip()
    if not app_config or not slot:
        return None
    return app_config.tiktok_device_ui.slots.get(slot)


def uses_alternate_account_switcher_ui(
    app_config: AppConfig | None,
    device_user_name: str,
) -> bool:
    ui = slot_ui_config(app_config, device_user_name)
    return bool(ui and ui.use_alternate_account_switcher)


def alternate_account_switcher_opener(
    app_config: AppConfig | None,
    device_user_name: str,
) -> TabCoord | None:
    ui = slot_ui_config(app_config, device_user_name)
    if not ui or not ui.use_alternate_account_switcher:
        return None
    return ui.account_switcher_opener


def slot_ui_label(
    app_config: AppConfig | None,
    device_user_name: str,
) -> str | None:
    ui = slot_ui_config(app_config, device_user_name)
    if not ui:
        return None
    label = str(ui.ui_label or "").strip()
    return label or None
