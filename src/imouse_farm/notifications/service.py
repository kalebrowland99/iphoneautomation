"""Discord and Telegram notification support."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from imouse_farm.config.models import NotificationsConfig
from imouse_farm.notifications.telegram_config import (
    resolve_telegram_credentials,
    telegram_alerts_enabled,
)
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


def apply_telegram_yml_to_notifications(
    config: NotificationsConfig,
    *,
    project_root: Path | None = None,
) -> NotificationsConfig:
    """Merge android-style config/telegram.yml into notifications.telegram."""
    token, chat_id = resolve_telegram_credentials(project_root)
    if not token or not chat_id:
        return config
    tg = config.telegram.model_copy(
        update={
            "enabled": True,
            "bot_token": token,
            "chat_id": chat_id,
        }
    )
    return config.model_copy(update={"telegram": tg, "enabled": True})


class NotificationService:
    """Send notifications via Discord webhooks and Telegram."""

    def __init__(
        self,
        config: NotificationsConfig,
        *,
        project_root: Path | None = None,
    ) -> None:
        self._config = apply_telegram_yml_to_notifications(
            config, project_root=project_root
        )
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def notify(self, event: str, message: str, details: dict[str, Any] | None = None) -> None:
        if not self._config.enabled:
            return

        events = self._config.events
        should_send = {
            "device_disconnect": events.device_disconnect,
            "unknown_screen": events.unknown_screen,
            "repeated_failures": events.repeated_failures,
            "workflow_completion": events.workflow_completion,
        }.get(event, True)

        if not should_send:
            return

        full_message = f"[{event.upper()}] {message}"
        if details:
            detail_str = "\n".join(f"- {k}: {v}" for k, v in details.items())
            full_message += f"\n{detail_str}"

        tasks = []
        if self._config.discord.enabled and self._config.discord.webhook_url:
            tasks.append(self._send_discord(full_message))
        if (
            self._config.telegram.enabled
            and self._config.telegram.bot_token
            and telegram_alerts_enabled()
        ):
            tasks.append(self._send_telegram(full_message))

        for coro in tasks:
            try:
                await coro
            except Exception as exc:
                logger.error("notification_failed", event=event, error=str(exc))

    async def send_telegram_text(self, message: str) -> bool:
        """Send a plain Telegram message (morning start / ad-hoc alerts)."""
        if not telegram_alerts_enabled():
            return False
        token = self._config.telegram.bot_token
        chat_id = self._config.telegram.chat_id
        if not token or not chat_id:
            token, chat_id = resolve_telegram_credentials()
        if not token or not chat_id:
            return False
        try:
            await self._send_telegram(message, token=token, chat_id=chat_id)
            return True
        except Exception as exc:
            logger.error("telegram_send_failed", error=str(exc))
            return False

    async def _send_discord(self, message: str) -> None:
        payload = {"content": message[:2000]}
        resp = await self._client.post(self._config.discord.webhook_url, json=payload)
        resp.raise_for_status()
        logger.debug("discord_notification_sent")

    async def _send_telegram(
        self,
        message: str,
        *,
        token: str | None = None,
        chat_id: str | None = None,
    ) -> None:
        tok = token or self._config.telegram.bot_token
        cid = chat_id or self._config.telegram.chat_id
        url = f"https://api.telegram.org/bot{tok}/sendMessage"
        # No parse_mode — same as androidautomationig alerts (avoids Markdown breakages).
        payload = {"chat_id": cid, "text": message[:4096]}
        resp = await self._client.post(url, json=payload)
        resp.raise_for_status()
        logger.debug("telegram_notification_sent")

    async def handle_event(self, event: str, data: dict[str, Any]) -> None:
        """Route system events to notifications."""
        if event == "device_disconnected":
            await self.notify(
                "device_disconnect",
                f"Device disconnected: {data.get('device_id', 'unknown')}",
                data,
            )
        elif event == "unknown_screen":
            await self.notify(
                "unknown_screen",
                f"Unknown screen on device {data.get('device_id')}",
                data,
            )
        elif event == "action_failed":
            threshold = self._config.repeated_failure_threshold
            failures = data.get("consecutive_failures", 0)
            if failures >= threshold:
                await self.notify(
                    "repeated_failures",
                    f"Device {data.get('device_id')} has {failures} consecutive failures",
                    data,
                )
        elif event == "workflow_completed":
            await self.notify(
                "workflow_completion",
                f"Workflow {data.get('workflow')} completed on {data.get('device_id')}",
                data,
            )
        elif event == "popup_detected":
            await self.notify(
                "unknown_screen",
                f"Popup on {data.get('device_id')}: {data.get('popup_type')}",
                data,
            )
