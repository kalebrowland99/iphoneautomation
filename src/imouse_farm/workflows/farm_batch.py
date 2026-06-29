"""Run production pipelines in batches with AirPlay cast on/off per batch."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from imouse_farm.config.models import AppConfig, BatchConfig
from imouse_farm.database.repository import DatabaseRepository
from imouse_farm.devices.manager import DeviceManager
from imouse_farm.post.post_caption_store import validate_post_texts
from imouse_farm.captions.service import (
    default_onscreen_template_for_brand,
    generate_captions_for_device,
)
from imouse_farm.utils.logging import get_logger
from imouse_farm.workflows.pipeline import WorkflowPipeline

logger = get_logger(__name__)

EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


def _post_text_key(device: Any) -> str:
    from imouse_farm.post.post_caption_store import device_storage_key

    return device_storage_key(device.device_id, device.user_name)


class FarmBatchRunner:
    """Connect one phone at a time, run pipeline, disconnect, then next (lowest slot first)."""

    def __init__(
        self,
        config: BatchConfig,
        app_config: AppConfig,
        device_manager: DeviceManager,
        pipeline: WorkflowPipeline,
        db: DatabaseRepository,
        imouse_connect_delay: float = 4.0,
        *,
        auto_generate_captions: bool = True,
    ) -> None:
        self._config = config
        self._app_config = app_config
        self._auto_captions = bool(auto_generate_captions)
        self._dm = device_manager
        self._pipeline = pipeline
        self._db = db
        self._connect_delay = imouse_connect_delay
        self._event_callbacks: list[EventCallback] = []
        self._pipeline.on_event(self._on_pipeline_event)

        self._status: dict[str, Any] = {
            "status": "idle",
            "batch_index": 0,
            "batch_total": 0,
            "current_batch": [],
            "completed": [],
            "failed": [],
            "message": "",
        }
        self._task: asyncio.Task[None] | None = None
        self._stop_requested = False
        self._batch_done_events: dict[str, asyncio.Event] = {}

    def on_event(self, callback: EventCallback) -> None:
        self._event_callbacks.append(callback)

    async def _emit(self, event: str, data: dict[str, Any]) -> None:
        for cb in self._event_callbacks:
            try:
                await cb(event, data)
            except Exception as exc:
                logger.error("batch_event_failed", error=str(exc))

    def get_status(self) -> dict[str, Any]:
        return dict(self._status)

    def is_running(self) -> bool:
        return self._status.get("status") in ("connecting", "running", "disconnecting")

    async def start(
        self,
        devices: list[Any],
        *,
        from_post: int | None = None,
        brand: str = "labely",
    ) -> bool:
        if self.is_running():
            return False
        if not devices:
            return False

        batches: list[list[Any]] = []
        size = max(1, int(self._config.batch_size))
        for i in range(0, len(devices), size):
            batches.append(devices[i : i + size])

        self._stop_requested = False
        self._status = {
            "status": "connecting",
            "batch_index": 0,
            "batch_total": len(batches),
            "current_batch": [],
            "completed": [],
            "failed": [],
            "message": f"Queued {len(devices)} phone(s) one at a time",
            "from_post": from_post,
        }
        self._task = asyncio.create_task(
            self._run_batches(batches, from_post=from_post, brand=brand)
        )
        await self._emit("batch_started", self.get_status())
        return True

    async def _disconnect_unselected_casts(self, selected_ids: set[str]) -> None:
        """Drop AirPlay for any online phone not in the current batch selection."""
        await self._dm.refresh_devices()
        for device in self._dm.devices.values():
            if device.device_id in selected_ids:
                continue
            if not device.is_online:
                continue
            logger.info(
                "batch_disconnect_unselected",
                device_id=device.device_id,
                slot=device.user_name,
            )
            await self._dm.disconnect_airplay(device.device_id)
            await self._db.log_activity(
                "info",
                "batch",
                f"Phone {device.user_name}: disconnected (not in batch selection)",
                device.device_id,
            )

    async def stop(self) -> None:
        from imouse_farm.actions.cancel import mark_cancelled

        self._stop_requested = True
        for device_id in list(self._batch_done_events.keys()):
            mark_cancelled(device_id)
            await self._pipeline.stop(device_id)
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._status["status"] = "stopped"
        self._status["message"] = "Batch run stopped"
        await self._emit("batch_stopped", self.get_status())

    async def _run_batches(
        self,
        batches: list[list[Any]],
        *,
        from_post: int | None,
        brand: str = "labely",
    ) -> None:
        selected_ids = {d.device_id for batch in batches for d in batch}
        try:
            await self._disconnect_unselected_casts(selected_ids)
            for batch_index, batch in enumerate(batches, start=1):
                if self._stop_requested:
                    break

                await self._disconnect_unselected_casts(selected_ids)

                slot_labels = [str(d.user_name) for d in batch]
                phone_num = batch_index
                phone_total = len(batches)
                self._status.update({
                    "status": "connecting",
                    "batch_index": batch_index,
                    "current_batch": slot_labels,
                    "message": f"Phone {phone_num}/{phone_total}: connecting slot {slot_labels[0]}",
                })
                await self._emit("batch_connecting", self.get_status())

                connected: list[Any] = []
                for device in batch:
                    if self._stop_requested:
                        break
                    ok = await self._ensure_cast(device.device_id)
                    if ok:
                        connected.append(device)
                    else:
                        self._status["failed"].append({
                            "slot": device.user_name,
                            "device_id": device.device_id,
                            "reason": "cast_connect_failed",
                        })
                        await self._db.log_activity(
                            "error",
                            "batch",
                            f"Phone {device.user_name}: cast connect failed",
                            device.device_id,
                            {"batch_index": batch_index},
                        )

                if not connected:
                    continue

                self._status["status"] = "running"
                self._status["message"] = (
                    f"Phone {phone_num}/{phone_total}: running slot {slot_labels[0]}"
                )
                await self._emit("batch_running", self.get_status())

                for device in connected:
                    if self._stop_requested:
                        break
                    text_key = _post_text_key(device)
                    check_from = from_post if from_post is not None else 1
                    missing = validate_post_texts(text_key, from_post=check_from)
                    if missing and self._auto_captions and self._app_config.openai.enabled:
                        try:
                            await generate_captions_for_device(
                                self._app_config,
                                device,
                                onscreen_template=default_onscreen_template_for_brand(brand),
                            )
                            missing = validate_post_texts(text_key, from_post=check_from)
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "batch_auto_caption_failed",
                                device_id=device.device_id,
                                slot=device.user_name,
                                error=str(exc),
                            )
                    if missing:
                        self._status["failed"].append({
                            "slot": device.user_name,
                            "device_id": device.device_id,
                            "reason": "; ".join(missing),
                        })
                        await self._dm.disconnect_airplay(device.device_id)
                        continue

                    self._batch_done_events[device.device_id] = asyncio.Event()
                    chain_valcoin = (
                        brand == "labely"
                        and from_post is None
                        and self._config.chain_valcoin_after_labely
                    )
                    started = await self._pipeline.start(
                        device.device_id,
                        from_post=from_post,
                        brand=brand,
                        chain_valcoin_after_labely=chain_valcoin,
                    )
                    if not started:
                        self._batch_done_events.pop(device.device_id, None)
                        self._status["failed"].append({
                            "slot": device.user_name,
                            "device_id": device.device_id,
                            "reason": "pipeline_start_failed",
                        })
                        await self._dm.disconnect_airplay(device.device_id)

                pending = list(self._batch_done_events.keys())
                for device_id in pending:
                    if self._stop_requested:
                        break
                    event = self._batch_done_events.get(device_id)
                    if not event:
                        continue
                    try:
                        await asyncio.wait_for(
                            event.wait(),
                            timeout=float(self._config.batch_device_timeout_seconds),
                        )
                    except asyncio.TimeoutError:
                        await self._pipeline.stop(device_id)
                        self._status["failed"].append({
                            "device_id": device_id,
                            "reason": "batch_device_timeout",
                        })
                        if self._config.disconnect_on_complete:
                            await self._dm.disconnect_airplay(device_id)
                        self._batch_done_events.pop(device_id, None)

                if not self._stop_requested:
                    self._status["status"] = "disconnecting"
                    self._status["message"] = f"Phone {phone_num}/{phone_total}: disconnecting cast"
                    await self._emit("batch_disconnecting", self.get_status())

                    if self._config.disconnect_on_complete:
                        for device in connected:
                            await self._dm.disconnect_airplay(device.device_id)

                pause = float(self._config.between_phones_pause_seconds)
                if pause > 0 and batch_index < len(batches) and not self._stop_requested:
                    await asyncio.sleep(pause)

            if self._stop_requested:
                self._status["status"] = "stopped"
            else:
                self._status["status"] = "completed"
                self._status["message"] = (
                    f"Batch run finished — "
                    f"{len(self._status['completed'])} ok, {len(self._status['failed'])} failed"
                )
            await self._emit("batch_completed", self.get_status())
        except asyncio.CancelledError:
            self._status["status"] = "stopped"
            raise
        except Exception as exc:
            logger.error("batch_run_failed", error=str(exc))
            self._status["status"] = "failed"
            self._status["message"] = str(exc)
            await self._emit("batch_failed", self.get_status())

    async def _ensure_cast(self, device_id: str) -> bool:
        attempts = max(1, int(self._config.cast_connect_max_attempts))
        interval = float(self._config.cast_connect_retry_seconds)
        for attempt in range(1, attempts + 1):
            await self._dm.refresh_devices()
            device = self._dm.get_device(device_id)
            if device and device.is_online:
                return True
            logger.info(
                "batch_cast_attempt",
                device_id=device_id,
                attempt=attempt,
                max_attempts=attempts,
            )
            await self._dm.reconnect_airplay(device_id)
            await asyncio.sleep(self._connect_delay)
            await self._dm.refresh_devices()
            device = self._dm.get_device(device_id)
            if device and device.is_online:
                return True
            if attempt < attempts:
                await asyncio.sleep(interval)
        return False

    async def _on_pipeline_event(self, event: str, data: dict[str, Any]) -> None:
        device_id = data.get("device_id")
        if not device_id or device_id not in self._batch_done_events:
            return
        if event not in ("pipeline_completed", "pipeline_failed", "pipeline_stopped"):
            return

        slot = None
        device = self._dm.get_device(device_id)
        if device:
            slot = device.user_name

        entry = {"slot": slot, "device_id": device_id, "event": event}
        if event == "pipeline_completed":
            self._status["completed"].append(entry)
        else:
            entry["reason"] = data.get("message", event)
            self._status["failed"].append(entry)

        # Keep AirPlay up when the user kills a run; only decast after a normal finish.
        if event == "pipeline_completed" and self._config.disconnect_on_complete:
            await self._dm.disconnect_airplay(device_id)

        done = self._batch_done_events.pop(device_id, None)
        if done:
            done.set()
