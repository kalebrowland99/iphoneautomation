"""Background watcher for random TikTok / iOS permission popups."""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

from imouse_farm.actions.permission_prompts import (
    button_texts_for_permission,
    find_contacts_search_texts,
    is_deny_permission_label,
    is_find_contacts_context_label,
    is_ios_local_network_dialog,
    is_not_now_label,
    is_ok_button_label,
    is_permission_dialog_text,
    is_photo_delete_sheet_text,
    is_tiktok_email_confirm_dialog,
    is_tiktok_save_login_dialog,
    is_tiktok_live_feed_dialog,
    is_ios_passkeys_passcode_dialog,
    is_tiktok_post_notify_dialog,
    is_tiktok_add_phone_dialog,
    is_tiktok_security_checkup_dialog,
    is_tiktok_viewer_history_dialog,
    is_tiktok_avatar_style_dialog,
    is_tiktok_ai_pick_dialog,
    detect_tiktok_ai_pick_on_device,
    is_tiktok_virtual_items_policies_dialog,
    is_got_it_label,
    is_save_button_label,
    local_network_ok_button_texts,
    should_allow_permission,
    tiktok_dont_allow_button_texts,
    tiktok_got_it_button_texts,
    tiktok_not_now_button_texts,
    tiktok_security_checkup_modal_rect_pct,
    tiktok_security_checkup_search_texts,
    tiktok_avatar_style_dismiss_coords,
    tiktok_ai_pick_dismiss_coords,
    tiktok_post_notify_dismiss_coords,
    tiktok_add_phone_dismiss_coords,
    tiktok_add_phone_modal_rect_pct,
    tiktok_add_phone_search_texts,
    tiktok_security_checkup_dismiss_coords,
    tiktok_viewer_history_save_button_texts,
)
from imouse_farm.actions.pre_touch_reset import (
    is_tiktok_workflow,
    pre_touch_mouse_reset,
)
from imouse_farm.controller.device_controller import DeviceController
from imouse_farm.devices.manager import DeviceManager
from imouse_farm.utils.logging import get_logger
from imouse_farm.vision.template_scan import ocr_rect_from_pct

logger = get_logger(__name__)

POST_DISMISS_SETTLE_SECONDS = 0.5


def _device_screen_size(device_manager: DeviceManager | None, device_id: str) -> tuple[int, int]:
    if device_manager:
        device = device_manager.get_device(device_id)
        if device and device.screen_width and device.screen_height:
            return int(device.screen_width), int(device.screen_height)
    return 406, 720


async def _ocr_join(
    controller: Any,
    device_id: str,
    *,
    is_ex: bool = False,
    rect: list[int] | None = None,
) -> str:
    items = await controller.ocr_items_on_device(device_id, is_ex=is_ex, rect=rect)
    return " ".join(str(item.get("text", "")) for item in items if item.get("text"))


async def collect_security_checkup_ocr(
    controller: Any,
    device_id: str,
    *,
    screen: str | None = None,
    device_manager: DeviceManager | None = None,
) -> str:
    """Merge full-screen + center-modal OCR (same sources the watcher uses)."""
    sw, sh = _device_screen_size(device_manager, device_id)
    modal_rect = ocr_rect_from_pct(sw, sh, list(tiktok_security_checkup_modal_rect_pct()))
    full = screen if screen is not None else await _ocr_join(controller, device_id)
    modal_ex = await _ocr_join(controller, device_id, is_ex=True, rect=modal_rect)
    full_ex = await _ocr_join(controller, device_id, is_ex=True)
    return "\n".join(part for part in (full, modal_ex, full_ex) if part)


async def detect_tiktok_security_checkup_on_device(
    controller: Any,
    device_id: str,
    *,
    screen: str | None = None,
    device_manager: DeviceManager | None = None,
) -> tuple[bool, str]:
    """Detect the security checkup sheet using the same OCR stack as other popups, plus modal crop."""
    combined = await collect_security_checkup_ocr(
        controller,
        device_id,
        screen=screen,
        device_manager=device_manager,
    )
    if is_tiktok_security_checkup_dialog(combined):
        return True, combined

    sw, sh = _device_screen_size(device_manager, device_id)
    modal_rect = ocr_rect_from_pct(sw, sh, list(tiktok_security_checkup_modal_rect_pct()))
    for rect in (modal_rect, None):
        matches = await controller.find_text_on_device(
            device_id,
            tiktok_security_checkup_search_texts(),
            threshold=0.45,
            contain=True,
            is_ex=True,
            rect=rect,
        )
        if not matches:
            continue
        joined = " ".join(str(m.get("text", "")) for m in matches if m.get("text"))
        probe = f"{combined}\n{joined}".strip()
        if is_tiktok_security_checkup_dialog(probe):
            return True, probe
        for match in matches:
            line = str(match.get("text", ""))
            if is_tiktok_security_checkup_dialog(line):
                return True, f"{combined}\n{line}".strip()
    return False, combined


async def collect_add_phone_ocr(
    controller: Any,
    device_id: str,
    *,
    screen: str | None = None,
    device_manager: DeviceManager | None = None,
) -> str:
    """Merge full-screen + center-modal OCR for the Add phone sheet."""
    sw, sh = _device_screen_size(device_manager, device_id)
    modal_rect = ocr_rect_from_pct(sw, sh, list(tiktok_add_phone_modal_rect_pct()))
    full = screen if screen is not None else await _ocr_join(controller, device_id)
    modal_ex = await _ocr_join(controller, device_id, is_ex=True, rect=modal_rect)
    full_ex = await _ocr_join(controller, device_id, is_ex=True)
    return "\n".join(part for part in (full, modal_ex, full_ex) if part)


async def detect_tiktok_add_phone_on_device(
    controller: Any,
    device_id: str,
    *,
    screen: str | None = None,
    device_manager: DeviceManager | None = None,
) -> tuple[bool, str]:
    """Detect the Add phone sheet using OCR + modal crop + find_text fallback."""
    combined = await collect_add_phone_ocr(
        controller,
        device_id,
        screen=screen,
        device_manager=device_manager,
    )
    if is_tiktok_add_phone_dialog(combined):
        return True, combined

    sw, sh = _device_screen_size(device_manager, device_id)
    modal_rect = ocr_rect_from_pct(sw, sh, list(tiktok_add_phone_modal_rect_pct()))
    for rect in (modal_rect, None):
        matches = await controller.find_text_on_device(
            device_id,
            tiktok_add_phone_search_texts(),
            threshold=0.45,
            contain=True,
            is_ex=True,
            rect=rect,
        )
        if not matches:
            continue
        joined = " ".join(str(m.get("text", "")) for m in matches if m.get("text"))
        probe = f"{combined}\n{joined}".strip()
        if is_tiktok_add_phone_dialog(probe):
            return True, probe
        for match in matches:
            line = str(match.get("text", ""))
            if is_tiktok_add_phone_dialog(line):
                return True, f"{combined}\n{line}".strip()
    return False, combined


class PermissionWatcher:
    """Poll on-device OCR and tap Allow or Don't Allow on iOS permission sheets."""

    def __init__(
        self,
        controller: DeviceController,
        device_id: str,
        *,
        device_manager: DeviceManager | None = None,
        poll_interval_seconds: float = 0.25,
        contacts_poll_interval_seconds: float = 0.2,
    ) -> None:
        self._controller = controller
        self._device_id = device_id
        self._device_manager = device_manager
        self._poll_interval = max(0.15, float(poll_interval_seconds))
        self._contacts_poll_interval = max(0.1, float(contacts_poll_interval_seconds))
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._contacts_task: asyncio.Task[None] | None = None
        self._check_lock = asyncio.Lock()
        self._contacts_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._loop(),
            name=f"permission_watcher:{self._device_id}",
        )
        self._contacts_task = asyncio.create_task(
            self._contacts_loop(),
            name=f"find_contacts_watcher:{self._device_id}",
        )
        logger.info("permission_watcher_started", device_id=self._device_id)

    async def stop(self) -> None:
        self._running = False
        for task in (self._task, self._contacts_task):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._task = None
        self._contacts_task = None
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

    async def _contacts_loop(self) -> None:
        """Dedicated fast loop: tap Don't allow the instant the find-contacts sheet shows.

        Runs concurrently with the main OCR loop so it never waits behind the full
        popup scan, and it only ever taps a deny button when find-contacts body copy
        is on screen — so it can't deny camera/photos prompts or hit the + button.
        """
        from imouse_farm.actions.cancel import is_cancelled

        while self._running:
            if is_cancelled(self._device_id):
                break
            try:
                await self._check_contacts_once()
            except Exception as exc:  # noqa: BLE001 — keep watcher alive
                logger.warning(
                    "find_contacts_watcher_error",
                    device_id=self._device_id,
                    error=str(exc),
                )
            await asyncio.sleep(self._contacts_poll_interval)

    async def _touch_activity(self) -> None:
        if self._device_manager:
            await self._device_manager.record_activity(self._device_id)

    async def _check_once(self) -> bool:
        """Return True if a permission or TikTok dismiss dialog was handled."""
        from imouse_farm.actions.cancel import is_cancelled

        if is_cancelled(self._device_id):
            return False

        if self._device_manager:
            tap_lock = self._device_manager.get_tap_lock(self._device_id)
            if tap_lock.locked():
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

            if is_tiktok_save_login_dialog(screen):
                tapped = await self._tap_not_now()
                if tapped:
                    logger.info(
                        "tiktok_popup_dismiss",
                        device_id=self._device_id,
                        dialog="save_login",
                        text=tapped.get("text", ""),
                        x=tapped.get("x"),
                        y=tapped.get("y"),
                    )
                    await self._touch_activity()
                    await asyncio.sleep(POST_DISMISS_SETTLE_SECONDS)
                    return True

            ai_pick_visible, _ = await detect_tiktok_ai_pick_on_device(
                self._controller,
                self._device_id,
                screen=screen,
                device_manager=self._device_manager,
            )
            if ai_pick_visible:
                tapped = await self._dismiss_ai_pick()
                if tapped:
                    logger.info(
                        "tiktok_popup_dismiss",
                        device_id=self._device_id,
                        dialog="ai_pick",
                        text=tapped.get("text", ""),
                        x=tapped.get("x"),
                        y=tapped.get("y"),
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

            checkup_visible, _ = await detect_tiktok_security_checkup_on_device(
                self._controller,
                self._device_id,
                screen=screen,
                device_manager=self._device_manager,
            )
            if checkup_visible:
                tapped = await self._dismiss_security_checkup()
                if tapped:
                    logger.info(
                        "tiktok_popup_dismiss",
                        device_id=self._device_id,
                        dialog="security_checkup",
                        text=tapped.get("text", ""),
                        x=tapped.get("x"),
                        y=tapped.get("y"),
                    )
                    await self._touch_activity()
                    await asyncio.sleep(POST_DISMISS_SETTLE_SECONDS)
                    return True

            add_phone_visible, _ = await detect_tiktok_add_phone_on_device(
                self._controller,
                self._device_id,
                screen=screen,
                device_manager=self._device_manager,
            )
            if add_phone_visible:
                tapped = await self._dismiss_add_phone()
                if tapped:
                    logger.info(
                        "tiktok_popup_dismiss",
                        device_id=self._device_id,
                        dialog="add_phone",
                        text=tapped.get("text", ""),
                        x=tapped.get("x"),
                        y=tapped.get("y"),
                    )
                    await self._touch_activity()
                    await asyncio.sleep(POST_DISMISS_SETTLE_SECONDS)
                    return True

            if is_ios_passkeys_passcode_dialog(screen):
                dismissed = await self._dismiss_passkeys_passcode()
                if dismissed:
                    logger.info(
                        "tiktok_popup_dismiss",
                        device_id=self._device_id,
                        dialog="passkeys_passcode",
                        action=dismissed.get("action", ""),
                    )
                    await self._touch_activity()
                    await asyncio.sleep(POST_DISMISS_SETTLE_SECONDS)
                    return True

            if is_tiktok_viewer_history_dialog(screen):
                tapped = await self._tap_viewer_history_save()
                if tapped:
                    logger.info(
                        "tiktok_popup_dismiss",
                        device_id=self._device_id,
                        dialog="viewer_history",
                        text=tapped.get("text", ""),
                        x=tapped.get("x"),
                        y=tapped.get("y"),
                    )
                    await self._touch_activity()
                    await asyncio.sleep(POST_DISMISS_SETTLE_SECONDS)
                    return True

            if is_tiktok_avatar_style_dialog(screen):
                tapped = await self._dismiss_avatar_style()
                if tapped:
                    logger.info(
                        "tiktok_popup_dismiss",
                        device_id=self._device_id,
                        dialog="avatar_style",
                        text=tapped.get("text", ""),
                        x=tapped.get("x"),
                        y=tapped.get("y"),
                    )
                    await self._touch_activity()
                    await asyncio.sleep(POST_DISMISS_SETTLE_SECONDS)
                    return True

            if is_tiktok_virtual_items_policies_dialog(screen):
                tapped = await self._tap_got_it()
                if tapped:
                    logger.info(
                        "tiktok_popup_dismiss",
                        device_id=self._device_id,
                        dialog="virtual_items_policies",
                        text=tapped.get("text", ""),
                        x=tapped.get("x"),
                        y=tapped.get("y"),
                    )
                    await self._touch_activity()
                    await asyncio.sleep(POST_DISMISS_SETTLE_SECONDS)
                    return True

            if is_ios_local_network_dialog(screen):
                tapped = await self._tap_ok()
                if tapped:
                    logger.info(
                        "permission_watcher_tap",
                        device_id=self._device_id,
                        action="local_network_ok",
                        text=tapped.get("text", ""),
                        x=tapped.get("x"),
                        y=tapped.get("y"),
                    )
                    await self._touch_activity()
                    await asyncio.sleep(POST_DISMISS_SETTLE_SECONDS)
                    return True

            if is_photo_delete_sheet_text(screen):
                return False

            if is_tiktok_live_feed_dialog(screen):
                swiped = await self._dismiss_live_feed()
                if swiped:
                    logger.info(
                        "tiktok_popup_dismiss",
                        device_id=self._device_id,
                        dialog="live_feed",
                        sx=swiped.get("sx"),
                        sy=swiped.get("sy"),
                        ex=swiped.get("ex"),
                        ey=swiped.get("ey"),
                    )
                    await self._touch_activity()
                    await asyncio.sleep(POST_DISMISS_SETTLE_SECONDS)
                    return True

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

    async def run_full_cycle(self) -> bool:
        """One production-equivalent poll: main popup scan then find-contacts loop."""
        if await self._check_once():
            return True
        return await self._check_contacts_once()

    async def _check_contacts_once(self) -> bool:
        """Tap Don't allow when the TikTok find-contacts sheet is visible.

        Targeted ``find_text`` (not full OCR) so it's cheap and instant, and gated on
        find-contacts body copy so an iOS camera/photos prompt is never denied.
        """
        from imouse_farm.actions.cancel import is_cancelled

        if is_cancelled(self._device_id):
            return False

        if self._device_manager:
            tap_lock = self._device_manager.get_tap_lock(self._device_id)
            if tap_lock.locked():
                return False

        async with self._contacts_lock:
            if is_cancelled(self._device_id):
                return False
            matches = await self._controller.find_text_on_device(
                self._device_id,
                find_contacts_search_texts(),
                threshold=0.6,
                contain=True,
            )
            if not matches:
                return False

            has_context = any(
                is_find_contacts_context_label(str(m.get("text", ""))) for m in matches
            )
            if not has_context:
                return False

            deny_candidates = [
                m for m in matches if is_deny_permission_label(str(m.get("text", "")))
            ]
            if not deny_candidates:
                return False

            best = max(deny_candidates, key=lambda m: float(m.get("confidence", 0)))
            await self._pre_touch_if_tiktok()
            if not await self._controller.tap(
                self._device_id, int(best["x"]), int(best["y"])
            ):
                return False
            logger.info(
                "tiktok_popup_dismiss",
                device_id=self._device_id,
                dialog="find_contacts_fast",
                text=best.get("text", ""),
                x=best.get("x"),
                y=best.get("y"),
            )
            await self._touch_activity()
            await asyncio.sleep(POST_DISMISS_SETTLE_SECONDS)
            return True

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

    async def _tap_got_it(self) -> dict[str, Any] | None:
        for text in tiktok_got_it_button_texts():
            matches = await self._controller.find_text_on_device(
                self._device_id, [text], threshold=0.65, contain=True
            )
            candidates = [
                m for m in matches if is_got_it_label(str(m.get("text", "")))
            ]
            if not candidates:
                continue
            best = max(candidates, key=lambda m: float(m.get("confidence", 0)))
            await self._pre_touch_if_tiktok()
            await self._controller.tap(self._device_id, int(best["x"]), int(best["y"]))
            return best
        return None

    async def _tap_ok(self) -> dict[str, Any] | None:
        for text in local_network_ok_button_texts():
            matches = await self._controller.find_text_on_device(
                self._device_id, [text], threshold=0.65, contain=True
            )
            candidates = [
                m for m in matches if is_ok_button_label(str(m.get("text", "")))
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

    async def _dismiss_security_checkup(self) -> dict[str, Any] | None:
        x, y = tiktok_security_checkup_dismiss_coords()
        await self._pre_touch_if_tiktok()
        if not await self._controller.tap(self._device_id, x, y):
            return None
        return {"text": "security_checkup_dismiss", "x": x, "y": y}

    async def _dismiss_add_phone(self) -> dict[str, Any] | None:
        x, y = tiktok_add_phone_dismiss_coords()
        await self._pre_touch_if_tiktok()
        if not await self._controller.tap(self._device_id, x, y):
            return None
        return {"text": "add_phone_dismiss", "x": x, "y": y}

    async def _dismiss_passkeys_passcode(self) -> dict[str, Any] | None:
        if not await self._controller.press_home(self._device_id):
            return None
        return {"text": "passkeys_passcode_dismiss", "action": "press_home"}

    async def _dismiss_avatar_style(self) -> dict[str, Any] | None:
        x, y = tiktok_avatar_style_dismiss_coords()
        await self._pre_touch_if_tiktok()
        if not await self._controller.tap(self._device_id, x, y):
            return None
        return {"text": "avatar_style_dismiss", "x": x, "y": y}

    async def _dismiss_ai_pick(self) -> dict[str, Any] | None:
        x, y = tiktok_ai_pick_dismiss_coords()
        await self._pre_touch_if_tiktok()
        if not await self._controller.tap(self._device_id, x, y):
            return None
        return {"text": "ai_pick_dismiss", "x": x, "y": y}

    async def _tap_viewer_history_save(self) -> dict[str, Any] | None:
        from imouse_farm.vision.text_color import decode_screenshot, is_text_light_enough

        matches = await self._controller.find_text_on_device(
            self._device_id,
            tiktok_viewer_history_save_button_texts(),
            threshold=0.65,
            contain=True,
        )
        candidates = [
            m for m in matches if is_save_button_label(str(m.get("text", "")))
        ]
        if not candidates:
            return None

        shot = await self._controller.capture_screenshot(self._device_id)
        image = decode_screenshot(shot) if shot else None
        if image is not None:
            light_candidates = []
            for match in candidates:
                rect = match.get("rect")
                ocr_rect = rect if isinstance(rect, list) else None
                if is_text_light_enough(
                    image,
                    int(match["x"]),
                    int(match["y"]),
                    rect=ocr_rect,
                ):
                    light_candidates.append(match)
            if light_candidates:
                candidates = light_candidates

        best = max(candidates, key=lambda m: float(m.get("confidence", 0)))
        await self._pre_touch_if_tiktok()
        if not await self._controller.tap(self._device_id, int(best["x"]), int(best["y"])):
            return None
        return best

    async def _dismiss_live_feed(self) -> dict[str, Any] | None:
        from imouse_farm.workflows.feed_scroll import screen_dimensions, swipe_feed_up

        sw, sh = screen_dimensions(
            self._device_manager.get_device(self._device_id)
            if self._device_manager
            else None
        )
        await self._pre_touch_if_tiktok()
        return await swipe_feed_up(self._controller, self._device_id, sw, sh)


class PermissionWatcherManager:
    """Per-device popup watchers — run continuously until force_stop."""

    def __init__(
        self,
        controller: DeviceController,
        device_manager: DeviceManager | None = None,
        *,
        poll_interval_seconds: float = 0.25,
        contacts_poll_interval_seconds: float = 0.2,
    ) -> None:
        self._controller = controller
        self._device_manager = device_manager
        self._poll_interval = max(0.15, float(poll_interval_seconds))
        self._contacts_poll_interval = max(0.1, float(contacts_poll_interval_seconds))
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
            contacts_poll_interval_seconds=self._contacts_poll_interval,
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

    async def run_watcher_cycle(self, device_id: str) -> bool:
        """Run one full watcher poll (main scan + find-contacts loop)."""
        await self.ensure_watching(device_id)
        watcher = self._watchers[device_id]
        return await watcher.run_full_cycle()

    async def stop_all(self) -> None:
        for device_id in list(self._watchers.keys()):
            await self.force_stop(device_id)

    async def force_stop(self, device_id: str) -> None:
        watcher = self._watchers.pop(device_id, None)
        if watcher:
            await watcher.stop()
