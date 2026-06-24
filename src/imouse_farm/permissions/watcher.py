"""Background watcher for random TikTok / iOS permission popups."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from imouse_farm.actions.permission_prompts import (
    NEGATIVE_BUTTON_WORDS,
    button_texts_for_permission,
    is_permission_dialog_text,
    should_allow_permission,
)
from imouse_farm.controller.device_controller import DeviceController
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


class PermissionWatcher:
    """Poll on-device OCR and tap Allow or Don't Allow on iOS permission sheets."""

    def __init__(
        self,
        controller: DeviceController,
        device_id: str,
        *,
        poll_interval_seconds: float = 0.75,
    ) -> None:
        self._controller = controller
        self._device_id = device_id
        self._poll_interval = poll_interval_seconds
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("permission_watcher_started", device_id=self._device_id)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("permission_watcher_stopped", device_id=self._device_id)

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._check_once()
            except Exception as exc:  # noqa: BLE001 — keep watcher alive
                logger.warning(
                    "permission_watcher_error",
                    device_id=self._device_id,
                    error=str(exc),
                )
            await asyncio.sleep(self._poll_interval)

    async def _check_once(self) -> bool:
        """Return True if a permission dialog was handled."""
        screen = await self._controller.ocr_on_device(self._device_id)
        if not screen or not is_permission_dialog_text(screen):
            return False

        allow = should_allow_permission(screen)
        labels = button_texts_for_permission(allow)
        tapped = await self._tap_button(labels)
        if tapped:
            action = "allow" if allow else "deny"
            logger.info(
                "permission_watcher_tap",
                device_id=self._device_id,
                action=action,
                text=tapped.get("text", ""),
                x=tapped.get("x"),
                y=tapped.get("y"),
            )
            await asyncio.sleep(1.2)
            return True
        return False

    async def _tap_button(self, labels: list[str]) -> dict[str, Any] | None:
        deny_mode = labels and labels[0] in ("Ask App Not to Track", "Don't Allow", "Dont Allow")
        negative_words = ("don't", "dont", "cancel", "deny", "not now", "don't allow")

        for text in labels:
            matches = await self._controller.find_text_on_device(self._device_id, [text])
            if deny_mode:
                candidates = [
                    m
                    for m in matches
                    if any(neg in str(m.get("text", "")).lower() for neg in NEGATIVE_BUTTON_WORDS)
                ]
            else:
                candidates = [
                    m
                    for m in matches
                    if not any(neg in str(m.get("text", "")).lower() for neg in negative_words)
                ]
            if not candidates:
                continue
            best = max(candidates, key=lambda m: float(m.get("confidence", 0)))
            await self._controller.tap(self._device_id, int(best["x"]), int(best["y"]))
            return best
        return None


class PermissionWatcherManager:
    """Start/stop per-device permission watchers during automation."""

    def __init__(self, controller: DeviceController) -> None:
        self._controller = controller
        self._watchers: dict[str, PermissionWatcher] = {}
        self._ref_counts: dict[str, int] = {}

    async def acquire(self, device_id: str) -> None:
        self._ref_counts[device_id] = self._ref_counts.get(device_id, 0) + 1
        if device_id not in self._watchers:
            watcher = PermissionWatcher(self._controller, device_id)
            self._watchers[device_id] = watcher
            await watcher.start()

    async def release(self, device_id: str) -> None:
        count = self._ref_counts.get(device_id, 0)
        if count <= 1:
            self._ref_counts.pop(device_id, None)
            watcher = self._watchers.pop(device_id, None)
            if watcher:
                await watcher.stop()
        else:
            self._ref_counts[device_id] = count - 1

    async def stop_all(self) -> None:
        for device_id in list(self._watchers.keys()):
            await self.force_stop(device_id)

    async def force_stop(self, device_id: str) -> None:
        """Stop watcher immediately regardless of reference count."""
        self._ref_counts.pop(device_id, None)
        watcher = self._watchers.pop(device_id, None)
        if watcher:
            await watcher.stop()
