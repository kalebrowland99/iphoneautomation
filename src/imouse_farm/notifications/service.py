"""Discord and Telegram notification support."""

from __future__ import annotations

from typing import Any

import httpx

from imouse_farm.config.models import NotificationsConfig
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


class NotificationService:
    """Send notifications via Discord webhooks and Telegram."""

    def __init__(self, config: NotificationsConfig) -> None:
        self._config = config
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

        full_message = f"**[{event.upper()}]** {message}"
        if details:
            detail_str = "\n".join(f"- {k}: {v}" for k, v in details.items())
            full_message += f"\n{detail_str}"

        tasks = []
        if self._config.discord.enabled and self._config.discord.webhook_url:
            tasks.append(self._send_discord(full_message))
        if self._config.telegram.enabled and self._config.telegram.bot_token:
            tasks.append(self._send_telegram(full_message))

        for coro in tasks:
            try:
                await coro
            except Exception as exc:
                logger.error("notification_failed", event=event, error=str(exc))

    async def _send_discord(self, message: str) -> None:
        payload = {"content": message[:2000]}
        resp = await self._client.post(self._config.discord.webhook_url, json=payload)
        resp.raise_for_status()
        logger.debug("discord_notification_sent")

    async def _send_telegram(self, message: str) -> None:
        token = self._config.telegram.bot_token
        chat_id = self._config.telegram.chat_id
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message[:4096], "parse_mode": "Markdown"}
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
