"""Background watcher for random TikTok / iOS permission popups."""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

from imouse_farm.actions.permission_prompts import (
    button_texts_for_permission,
    is_deny_permission_label,
    is_not_now_label,
    is_permission_dialog_text,
    is_photo_delete_sheet_text,
    is_tiktok_continue_editing_dialog,
    is_tiktok_email_confirm_dialog,
    is_tiktok_in_app_deny_dialog,
    is_tiktok_post_notify_dialog,
    should_allow_permission,
    tiktok_continue_editing_swipe_coords,
    tiktok_dont_allow_button_texts,
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

POST_DISMISS_SETTLE_SECONDS = 0.5


class PermissionWatcher:
    """Poll on-device OCR and tap Allow or Don't Allow on iOS permission sheets."""

    def __init__(
        self,
        controller: DeviceController,
        device_id: str,
        *,
        device_manager: DeviceManager | None = None,
        poll_interval_seconds: float = 0.25,
    ) -> None:
        self._controller = controller
        self._device_id = device_id
        self._device_manager = device_manager
        self._poll_interval = max(0.15, float(poll_interval_seconds))
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._check_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._loop(),
            name=f"permission_watcher:{self._device_id}",
        )
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
        from imouse_farm.actions.cancel import is_cancelled

        while self._running:
            if is_cancelled(self._device_id):
                break
            try:
                await self._check_once()
            except Exception as exc:  # noqa: BLE001 — keep watcher alive
                logger.warning(
                    "permission_watcher_error",
                    device_id=self._device_id,
                    error=str(exc),
                )
            await asyncio.sleep(self._poll_interval)

    async def _touch_activity(self) -> None:
        if self._device_manager:
            await self._device_manager.record_activity(self._device_id)

    async def _check_once(self) -> bool:
        """Return True if a permission or TikTok dismiss dialog was handled."""
        from imouse_farm.actions.cancel import is_cancelled

        if is_cancelled(self._device_id):
            return False

        async with self._check_lock:
            if is_cancelled(self._device_id):
                return False
            screen = await self._controller.ocr_on_device(self._device_id)
            if not screen:
                return False
            await self._touch_activity()

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
                    await self._touch_activity()
                    await asyncio.sleep(POST_DISMISS_SETTLE_SECONDS)
                    return True

            if is_tiktok_continue_editing_dialog(screen):
                swiped = await self._dismiss_continue_editing()
                if swiped:
                    logger.info(
                        "tiktok_popup_dismiss",
                        device_id=self._device_id,
                        dialog="continue_editing",
                        sx=swiped.get("sx"),
                        sy=swiped.get("sy"),
                        ex=swiped.get("ex"),
                        ey=swiped.get("ey"),
                    )
                    await self._touch_activity()
                    await asyncio.sleep(POST_DISMISS_SETTLE_SECONDS)
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
                    await self._touch_activity()
                    await asyncio.sleep(POST_DISMISS_SETTLE_SECONDS)
                    return True

            if is_tiktok_in_app_deny_dialog(screen):
                tapped = await self._tap_button(tiktok_dont_allow_button_texts())
                if tapped:
                    logger.info(
                        "tiktok_popup_dismiss",
                        device_id=self._device_id,
                        dialog="in_app_deny",
                        text=tapped.get("text", ""),
                        x=tapped.get("x"),
                        y=tapped.get("y"),
                    )
                    await self._touch_activity()
                    await asyncio.sleep(POST_DISMISS_SETTLE_SECONDS)
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
                await self._touch_activity()
                await asyncio.sleep(POST_DISMISS_SETTLE_SECONDS)
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
        deny_mode = labels and (
            labels[0] in ("Ask App Not to Track", "Don't Allow", "Dont Allow")
            or labels[0] in tiktok_dont_allow_button_texts()
        )
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

    async def _dismiss_continue_editing(self) -> dict[str, Any] | None:
        sx, sy, ex, ey = tiktok_continue_editing_swipe_coords()
        await self._pre_touch_if_tiktok()
        if not await self._controller.swipe(
            self._device_id,
            direction="up",
            sx=sx,
            sy=sy,
            ex=ex,
            ey=ey,
        ):
            return None
        return {"text": "continue_editing_swipe", "sx": sx, "sy": sy, "ex": ex, "ey": ey}


class PermissionWatcherManager:
    """Per-device popup watchers — run continuously until force_stop."""

    def __init__(
        self,
        controller: DeviceController,
        device_manager: DeviceManager | None = None,
        *,
        poll_interval_seconds: float = 0.25,
    ) -> None:
        self._controller = controller
        self._device_manager = device_manager
        self._poll_interval = max(0.15, float(poll_interval_seconds))
        self._watchers: dict[str, PermissionWatcher] = {}

    async def ensure_watching(self, device_id: str) -> None:
        """Start background popup scan for a device (idempotent)."""
        if device_id in self._watchers:
            return
        watcher = PermissionWatcher(
            self._controller,
            device_id,
            device_manager=self._device_manager,
            poll_interval_seconds=self._poll_interval,
        )
        self._watchers[device_id] = watcher
        await watcher.start()

    async def acquire(self, device_id: str) -> None:
        await self.ensure_watching(device_id)

    async def release(self, device_id: str) -> None:
        """No-op — watchers stay alive until kill/disconnect (force_stop)."""

    async def try_dismiss(self, device_id: str) -> bool:
        """Run one popup/permission scan (serialized with the background loop)."""
        await self.ensure_watching(device_id)
        watcher = self._watchers[device_id]
        return await watcher._check_once()

    async def stop_all(self) -> None:
        for device_id in list(self._watchers.keys()):
            await self.force_stop(device_id)

    async def force_stop(self, device_id: str) -> None:
        watcher = self._watchers.pop(device_id, None)
        if watcher:
            await watcher.stop()
