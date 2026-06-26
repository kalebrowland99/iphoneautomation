"""Background watcher for random TikTok / iOS permission popups."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from imouse_farm.actions.permission_prompts import (
    button_texts_for_permission,
    is_deny_permission_label,
    is_not_now_label,
    is_permission_dialog_text,
    is_photo_delete_sheet_text,
    is_tiktok_email_confirm_dialog,
    is_tiktok_post_notify_dialog,
    should_allow_permission,
    tiktok_not_now_button_texts,
    tiktok_post_notify_dismiss_coords,
)
from imouse_farm.actions.pre_touch_reset import (
    is_tiktok_workflow,
    pre_touch_mouse_reset,
)
from imouse_farm.controller.device_controller import DeviceController
from imouse_farm.devices.manager import DeviceManager
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


class PermissionWatcher:
    """Poll on-device OCR and tap Allow or Don't Allow on iOS permission sheets."""

    def __init__(
        self,
        controller: DeviceController,
        device_id: str,
        *,
        device_manager: DeviceManager | None = None,
        poll_interval_seconds: float = 0.75,
    ) -> None:
        self._controller = controller
        self._device_id = device_id
        self._device_manager = device_manager
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
        """Return True if a permission or TikTok dismiss dialog was handled."""
        screen = await self._controller.ocr_on_device(self._device_id)
        if not screen:
            return False

        if is_tiktok_email_confirm_dialog(screen):
            tapped = await self._tap_not_now()
            if tapped:
                logger.info(
                    "tiktok_popup_dismiss",
                    device_id=self._device_id,
                    dialog="email_confirm",
                    text=tapped.get("text", ""),
                    x=tapped.get("x"),
                    y=tapped.get("y"),
                )
                await asyncio.sleep(1.2)
                return True

        if is_tiktok_post_notify_dialog(screen):
            tapped = await self._dismiss_post_notify()
            if tapped:
                logger.info(
                    "tiktok_popup_dismiss",
                    device_id=self._device_id,
                    dialog="post_notify",
                    text=tapped.get("text", ""),
                    x=tapped.get("x"),
                    y=tapped.get("y"),
                )
                await asyncio.sleep(1.2)
                return True

        if is_photo_delete_sheet_text(screen):
            return False

        if not is_permission_dialog_text(screen):
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

    async def _pre_touch_if_tiktok(self) -> None:
        if not self._device_manager:
            return
        device = self._device_manager.get_device(self._device_id)
        if device and is_tiktok_workflow(device.workflow_name):
            await pre_touch_mouse_reset(
                self._controller,
                self._device_id,
                step_name="permission_watcher",
            )

    async def _tap_button(self, labels: list[str]) -> dict[str, Any] | None:
        deny_mode = labels and labels[0] in ("Ask App Not to Track", "Don't Allow", "Dont Allow")
        negative_words = ("don't", "dont", "cancel", "deny", "not now", "don't allow", "delet")

        for text in labels:
            matches = await self._controller.find_text_on_device(self._device_id, [text])
            if deny_mode:
                candidates = [
                    m
                    for m in matches
                    if is_deny_permission_label(str(m.get("text", "")))
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
            await self._pre_touch_if_tiktok()
            await self._controller.tap(self._device_id, int(best["x"]), int(best["y"]))
            return best
        return None

    async def _tap_not_now(self) -> dict[str, Any] | None:
        for text in tiktok_not_now_button_texts():
            matches = await self._controller.find_text_on_device(
                self._device_id, [text], threshold=0.65, contain=True
            )
            candidates = [
                m for m in matches if is_not_now_label(str(m.get("text", "")))
            ]
            if not candidates:
                continue
            best = max(candidates, key=lambda m: float(m.get("confidence", 0)))
            await self._pre_touch_if_tiktok()
            await self._controller.tap(self._device_id, int(best["x"]), int(best["y"]))
            return best
        return None

    async def _dismiss_post_notify(self) -> dict[str, Any] | None:
        x, y = tiktok_post_notify_dismiss_coords()
        await self._pre_touch_if_tiktok()
        if not await self._controller.tap(self._device_id, x, y):
            return None
        return {"text": "post_notify_dismiss", "x": x, "y": y}


class PermissionWatcherManager:
    """Start/stop per-device permission watchers during automation."""

    def __init__(
        self,
        controller: DeviceController,
        device_manager: DeviceManager | None = None,
    ) -> None:
        self._controller = controller
        self._device_manager = device_manager
        self._watchers: dict[str, PermissionWatcher] = {}
        self._ref_counts: dict[str, int] = {}

    async def acquire(self, device_id: str) -> None:
        self._ref_counts[device_id] = self._ref_counts.get(device_id, 0) + 1
        if device_id not in self._watchers:
            watcher = PermissionWatcher(
                self._controller,
                device_id,
                device_manager=self._device_manager,
            )
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
