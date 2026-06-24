"""Per-device action execution via DeviceController with queuing."""

from __future__ import annotations

import asyncio
import time
from asyncio import QueueEmpty
from typing import Any, Callable, Awaitable

from imouse_farm.actions.queue import ActionQueue, QueuedAction
from pathlib import Path

from imouse_farm.config.models import ActionRequest, ActionType, AppConfig, DeviceState
from imouse_farm.controller.device_controller import DeviceController
from imouse_farm.database.repository import DatabaseRepository
from imouse_farm.devices.manager import DeviceManager
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


class ActionEngine:
    """Execute device actions through the SDK with per-device queues.

    One device failure never blocks other device queues.
    """

    def __init__(
        self,
        config: AppConfig,
        controller: DeviceController,
        device_manager: DeviceManager,
        db: DatabaseRepository,
    ) -> None:
        self._config = config
        self._controller = controller
        self._device_manager = device_manager
        self._db = db
        self._queues: dict[str, ActionQueue] = {}
        self._workers: dict[str, asyncio.Task[None]] = {}
        self._running = False
        self._event_callbacks: list[EventCallback] = []
        self._last_detections: dict[str, dict[str, Any]] = {}

    def on_event(self, callback: EventCallback) -> None:
        self._event_callbacks.append(callback)

    def set_detections(self, device_id: str, detections: dict[str, Any]) -> None:
        """Store latest vision detections for tap_detection actions."""
        self._last_detections[device_id] = detections

    async def _emit(self, event: str, data: dict[str, Any]) -> None:
        for cb in self._event_callbacks:
            try:
                await cb(event, data)
            except Exception as exc:
                logger.error("action_event_failed", error=str(exc))

    async def start(self) -> None:
        self._running = True
        logger.info("action_engine_started")

    async def stop(self) -> None:
        self._running = False
        for task in self._workers.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._workers.clear()
        logger.info("action_engine_stopped")

    def _get_queue(self, device_id: str) -> ActionQueue:
        if device_id not in self._queues:
            self._queues[device_id] = ActionQueue(device_id)
            if self._running:
                self._workers[device_id] = asyncio.create_task(self._worker_loop(device_id))
        return self._queues[device_id]

    async def execute(self, request: ActionRequest) -> bool:
        device = self._device_manager.get_device(request.device_id)
        if not device or not device.is_online:
            logger.warning("action_device_unavailable", device_id=request.device_id)
            return False
        return await self._get_queue(request.device_id).enqueue(request)

    async def execute_direct(
        self,
        device_id: str,
        action_type: ActionType,
        params: dict[str, Any] | None = None,
        workflow_id: str | None = None,
        step_name: str | None = None,
    ) -> bool:
        request = ActionRequest(
            device_id=device_id,
            action_type=action_type,
            params=params or {},
            workflow_id=workflow_id,
            step_name=step_name,
        )
        return await self.execute(request)

    async def _worker_loop(self, device_id: str) -> None:
        queue = self._queues[device_id]
        while self._running:
            try:
                queued = await asyncio.wait_for(queue.dequeue(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            queue.is_processing = True
            try:
                result = await self._execute_with_retry(queued)
                if queued.future and not queued.future.done():
                    queued.future.set_result(result)
            except Exception as exc:
                if queued.future and not queued.future.done():
                    queued.future.set_exception(exc)
            finally:
                queue.is_processing = False
                queue.task_done()

    async def _execute_with_retry(self, queued: QueuedAction) -> bool:
        request = queued.request
        params = request.params
        if "retry_count" in params:
            retries = int(params["retry_count"])
        else:
            retries = self._config.timing.action_retry_count
        delay = self._config.timing.action_retry_delay_seconds

        for attempt in range(retries + 1):
            start = time.monotonic()
            action_id = await self._db.log_action_start(
                request.device_id,
                request.action_type.value,
                request.params,
                request.workflow_id,
                request.step_name,
            )
            try:
                success = await self._run_action(request)
                duration_ms = int((time.monotonic() - start) * 1000)
                if success:
                    await self._db.log_action_complete(action_id, "success", duration_ms=duration_ms)
                    await self._device_manager.record_activity(request.device_id)
                    await self._device_manager.set_last_action(
                        request.device_id, request.action_type.value
                    )
                    logger.info(
                        "action_completed",
                        device_id=request.device_id,
                        action=request.action_type.value,
                        duration_ms=duration_ms,
                    )
                    await self._emit("action_completed", {
                        "device_id": request.device_id,
                        "action": request.action_type.value,
                    })
                    return True
                await self._db.log_action_complete(
                    action_id, "failed", error_message="Action returned false", duration_ms=duration_ms
                )
            except Exception as exc:
                duration_ms = int((time.monotonic() - start) * 1000)
                await self._db.log_action_complete(
                    action_id, "failed", error_message=str(exc), duration_ms=duration_ms
                )
                logger.error(
                    "action_failed",
                    device_id=request.device_id,
                    action=request.action_type.value,
                    attempt=attempt + 1,
                    error=str(exc),
                )
            if attempt < retries:
                await asyncio.sleep(delay)

        failures = await self._device_manager.record_failure(request.device_id)
        await self._emit("action_failed", {
            "device_id": request.device_id,
            "action": request.action_type.value,
            "consecutive_failures": failures,
        })
        return False

    async def _run_action(self, request: ActionRequest) -> bool:
        device_id = request.device_id
        params = request.params
        action = request.action_type
        ctrl = self._controller

        match action:
            case ActionType.TAP:
                if "detection" in params:
                    det = self._last_detections.get(device_id, {}).get(params["detection"])
                    if not det:
                        raise RuntimeError(
                            f"Cannot tap: detection '{params['detection']}' not found. "
                            "Run screenshot + analyze first."
                        )
                    return await ctrl.tap(device_id, int(det["x"]), int(det["y"]))
                if params.get("require_detection") and ("x" not in params or "y" not in params):
                    raise RuntimeError("Blind tap blocked: require_detection is set")
                return await ctrl.tap(device_id, int(params["x"]), int(params["y"]))
            case ActionType.TAP_DETECTION:
                name = params.get("detection", "")
                optional = bool(params.get("optional", False))
                det = self._last_detections.get(device_id, {}).get(name)
                if not det:
                    if optional:
                        logger.info("tap_detection_skipped", device_id=device_id, detection=name)
                        return True
                    raise RuntimeError(f"Detection '{name}' not found — analyze screen first")
                x, y = int(det["x"]), int(det["y"])
                tap_count = max(1, int(params.get("tap_count", 1)))
                interval = float(params.get("tap_interval_seconds", 0.4))
                for tap_idx in range(tap_count):
                    if not await ctrl.tap(device_id, x, y):
                        return False
                    if tap_idx < tap_count - 1:
                        await asyncio.sleep(interval)
                return True
            case ActionType.TAP_OCR:
                texts_param = params.get("texts")
                if texts_param:
                    candidates = [str(t).strip() for t in texts_param if str(t).strip()]
                else:
                    single = str(params.get("text", "")).strip()
                    candidates = [single] if single else []
                if not candidates:
                    raise RuntimeError("tap_ocr requires text or texts")
                optional = bool(params.get("optional", True))
                prefer_top = bool(params.get("prefer_top", False))
                threshold = float(params.get("threshold", 0.75))
                contain = bool(params.get("contain", True))
                wait_timeout = float(params.get("wait_timeout_seconds", 0))
                poll_interval = float(params.get("poll_interval_seconds", 2))

                def _pick_best_match(matches: list[dict[str, Any]]) -> dict[str, Any]:
                    if prefer_top:
                        return min(
                            matches,
                            key=lambda m: (int(m["y"]), -float(m.get("confidence", 0))),
                        )
                    return max(
                        matches,
                        key=lambda m: (
                            float(m.get("confidence", 0)),
                            len(str(m.get("text", ""))),
                            -int(m["y"]),
                        ),
                    )

                async def _try_tap_once() -> bool:
                    expect_missing = bool(params.get("expect_missing"))
                    if expect_missing:
                        for text in candidates:
                            matches = await ctrl.find_text_on_device(
                                device_id,
                                [text],
                                threshold=threshold,
                                contain=contain,
                            )
                            if matches:
                                return False
                        logger.info(
                            "ocr_missing_verified",
                            device_id=device_id,
                            texts=candidates,
                        )
                        return True
                    # Try each candidate in order so specific labels (e.g. full song
                    # title) win over shorter partial OCR hits elsewhere on screen.
                    for text in candidates:
                        matches = await ctrl.find_text_on_device(
                            device_id,
                            [text],
                            threshold=threshold,
                            contain=contain,
                        )
                        if not matches:
                            continue
                        annotated = [{**m, "text": m.get("text") or text} for m in matches]
                        best = _pick_best_match(annotated)
                        if params.get("verify_only"):
                            logger.info(
                                "ocr_verified",
                                device_id=device_id,
                                text=best.get("text"),
                                query=text,
                            )
                            return True
                        logger.info(
                            "tap_ocr",
                            device_id=device_id,
                            text=best.get("text"),
                            x=best["x"],
                            y=best["y"],
                            prefer_top=prefer_top,
                            query=text,
                        )
                        await ctrl.tap(device_id, int(best["x"]), int(best["y"]))
                        return True
                    return False

                deadline = time.monotonic() + wait_timeout if wait_timeout > 0 else time.monotonic()
                while True:
                    if await _try_tap_once():
                        return True
                    if wait_timeout <= 0 or time.monotonic() >= deadline:
                        break
                    await asyncio.sleep(poll_interval)
                if optional:
                    logger.info("tap_ocr_skipped", device_id=device_id, texts=candidates)
                    return True
                if params.get("expect_missing"):
                    raise RuntimeError(f"Expected text absent but found {candidates!r} on screen")
                raise RuntimeError(f"None of {candidates!r} found on screen")
            case ActionType.SWIPE:
                return await ctrl.swipe(
                    device_id,
                    direction=str(params.get("direction", "up")),
                    length=float(params.get("length", params.get("len", 0.9))),
                    sx=_coerce_int(params.get("sx", params.get("x1"))),
                    sy=_coerce_int(params.get("sy", params.get("y1"))),
                    ex=_coerce_int(params.get("ex", params.get("x2"))),
                    ey=_coerce_int(params.get("ey", params.get("y2"))),
                )
            case ActionType.LONG_PRESS:
                return await ctrl.long_press(
                    device_id, int(params["x"]), int(params["y"]),
                    int(params.get("duration_ms", 1000)),
                )
            case ActionType.DRAG:
                return await ctrl.drag(
                    device_id,
                    int(params["x1"]),
                    int(params["y1"]),
                    x2=_coerce_int(params.get("x2")),
                    y2=_coerce_int(params.get("y2")),
                    direction=str(params["direction"]).strip() if params.get("direction") else None,
                    distance=_coerce_int(params.get("distance")),
                    duration_ms=int(params.get("duration_ms", 1000)),
                    move_ms=int(params.get("move_ms", 10)),
                    hold_ms=int(params.get("hold_ms", 0)),
                )
            case ActionType.TEXT_INPUT:
                return await ctrl.send_text(device_id, str(params.get("text", "")))
            case ActionType.CLEAR_TEXT:
                return await ctrl.clear_text_field(device_id)
            case ActionType.KEY:
                fn_key = str(params.get("fn_key", "")).strip()
                key = str(params.get("key", "")).strip()
                if fn_key:
                    return await ctrl.send_fn_key(device_id, fn_key)
                if key:
                    return await ctrl.send_key(device_id, key)
                raise RuntimeError("key action requires fn_key or key")
            case ActionType.HOME:
                return await ctrl.press_home(device_id)
            case ActionType.MOUSE_RESET:
                return await ctrl.reset_cursor(device_id)
            case ActionType.LOCK:
                return await ctrl.press_lock(device_id)
            case ActionType.UNLOCK:
                return await ctrl.press_unlock(device_id)
            case ActionType.LAUNCH_APP:
                app = str(
                    params.get("app_name")
                    or params.get("bundle_id")
                    or params.get("url")
                    or ""
                ).strip()
                if not app:
                    raise RuntimeError("launch_app requires app_name or bundle_id")
                return await ctrl.launch_app(device_id, app)
            case ActionType.OPEN_URL:
                return await ctrl.launch_app(device_id, str(params.get("url", "")))
            case ActionType.CLOSE_APP:
                return await ctrl.close_app(device_id)
            case ActionType.KILL_APP:
                return await ctrl.kill_app(device_id)
            case ActionType.ALBUM_CLEAR:
                self._block_album_when_vpn_on(device_id, "Album clear")
                return await ctrl.album_clear(
                    device_id,
                    album_name=params.get("album_name"),
                    timeout_ms=int(params.get("timeout_ms", 120000)),
                )
            case ActionType.ALBUM_UPLOAD:
                self._block_album_when_vpn_on(device_id, "Album upload")
                from imouse_farm.utils.gallery import list_media_files_for_upload

                folder = Path(str(params.get("folder", ""))).resolve()
                if not folder.is_dir():
                    raise RuntimeError(f"Upload folder not found: {folder}")
                extensions = params.get("extensions") or [
                    ".mp4", ".mov", ".m4v", ".jpg", ".jpeg", ".png", ".heic"
                ]
                files = list_media_files_for_upload(folder, extensions)
                if not files:
                    raise RuntimeError(f"No media files in {folder}")
                return await ctrl.album_upload(
                    device_id,
                    files,
                    album_name=params.get("album_name"),
                    timeout_ms=int(params.get("timeout_ms", 300000)),
                    zip_files=bool(params.get("zip", False)),
                    verify=bool(params.get("verify", True)),
                )
            case _:
                raise ValueError(f"Unknown action type: {action}")

    async def cancel_pending(self, device_id: str) -> int:
        """Drop queued actions for a device (e.g. after Stop)."""
        queue = self._queues.get(device_id)
        if not queue:
            return 0
        cancelled = 0
        while True:
            try:
                queued = queue._queue.get_nowait()  # noqa: SLF001
            except QueueEmpty:
                break
            if queued.future and not queued.future.done():
                queued.future.set_result(False)
                cancelled += 1
            queue.task_done()
        return cancelled

    def queue_size(self, device_id: str) -> int:
        queue = self._queues.get(device_id)
        return queue.size if queue else 0

    def _block_album_when_vpn_on(self, device_id: str, action_label: str) -> None:
        device = self._device_manager.get_device(device_id)
        if device and device.current_state == DeviceState.ACTIVE:
            raise RuntimeError(
                f"{action_label} blocked while VPN is active — album sync must run before VPN"
            )
