"""Run production pipelines in batches with AirPlay cast on/off per batch."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from imouse_farm.config.models import AppConfig, BatchConfig
from imouse_farm.database.repository import DatabaseRepository
from imouse_farm.devices.manager import DeviceManager
from imouse_farm.permissions.watcher import PermissionWatcherManager
from imouse_farm.post.post_caption_store import validate_post_texts, text_key_for_device
from imouse_farm.post.account_profile_store import (
    get_profile_for_device,
    is_cant_cast_imouse,
    is_phone_dead,
    set_cant_cast_imouse,
    clear_cant_cast_imouse,
)
from imouse_farm.post.brand_keys import device_storage_key
from imouse_farm.captions.service import (
    default_onscreen_template_for_brand,
    generate_captions_for_device,
)
from imouse_farm.utils.logging import get_logger
from imouse_farm.recordings.session_recorder import (
    SessionRecordingManager,
    session_recording_path,
)
from imouse_farm.workflows.pipeline import WorkflowPipeline
from imouse_farm.workflows.warmup import run_tiktok_warmup
from imouse_farm.workflows.imouse_recovery import is_imouse_failure

logger = get_logger(__name__)

EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


def _post_text_key(device: Any, brand: str) -> str:
    return text_key_for_device(device.device_id, device.user_name, brand=brand)


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
        permission_watchers: PermissionWatcherManager | None = None,
    ) -> None:
        self._config = config
        self._app_config = app_config
        self._auto_captions = bool(auto_generate_captions)
        self._permission_watchers = permission_watchers
        self._dm = device_manager
        self._pipeline = pipeline
        self._db = db
        self._connect_delay = imouse_connect_delay
        self._session_recordings = SessionRecordingManager()
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
        self._current_brand: str = "labely"
        self._labely_pipeline_ok: set[str] = set()
        self._valcoin_post_slots: frozenset[str] = frozenset()
        self._active_batch_index = 0
        self._imouse_failure_count = 0
        self._first_imouse_failure_batch_index: int | None = None
        self._kernel_recovery_count = 0
        self._pending_kernel_recovery_batch_index: int | None = None

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

    def _batch_wait_timeout_seconds(self) -> float:
        """Max seconds to wait for one phone's batch (post + chained ValCoin warmup)."""
        return max(1800.0, float(self._config.batch_device_timeout_seconds))

    async def wait_done(self, timeout: float | None = None) -> bool:
        """Wait until the current batch task finishes (no-op if nothing is running).

        Returns True when the task completed, False if *timeout* elapsed first.
        When False, the batch may still be running — call ``wait_until_idle()``
        before starting the next phone.
        """
        limit = float(timeout) if timeout is not None else self._batch_wait_timeout_seconds()
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=limit)
            except asyncio.TimeoutError:
                logger.warning("farm_batch_wait_done_timeout", timeout=limit)
                return False
            except Exception:
                logger.exception("farm_batch_wait_done_error")
                return False
        return self._task is None or self._task.done()

    async def wait_until_idle(self) -> None:
        """Block until the batch asyncio task finishes (no timeout)."""
        if self._task and not self._task.done():
            await asyncio.shield(self._task)

    async def start(
        self,
        devices: list[Any],
        *,
        from_post: int | None = None,
        brand: str = "labely",
        valcoin_slots: frozenset[str] | None = None,
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
        self._labely_pipeline_ok.clear()
        self._valcoin_post_slots = valcoin_slots or frozenset()
        if self._permission_watchers:
            for device in devices:
                await self._permission_watchers.ensure_watching(device.device_id)
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
        self._status["status"] = "idle"
        self._status["message"] = "Batch run stopped"
        self._batch_done_events.clear()
        self._labely_pipeline_ok.clear()
        await self._session_recordings.stop_all()
        await self._emit("batch_stopped", self.get_status())

    async def _run_batches(
        self,
        batches: list[list[Any]],
        *,
        from_post: int | None,
        brand: str = "labely",
    ) -> None:
        self._current_brand = brand
        self._labely_pipeline_ok.clear()
        self._active_batch_index = 0
        self._imouse_failure_count = 0
        self._first_imouse_failure_batch_index = None
        self._kernel_recovery_count = 0
        self._pending_kernel_recovery_batch_index = None
        selected_ids = {d.device_id for batch in batches for d in batch}
        try:
            await self._disconnect_unselected_casts(selected_ids)
            batch_index = 1
            while batch_index <= len(batches):
                if self._stop_requested:
                    break
                batch = batches[batch_index - 1]
                self._active_batch_index = batch_index

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
                    base_key = device_storage_key(device.device_id, device.user_name)
                    if is_phone_dead(base_key):
                        logger.info(
                            "batch_cast_skipped_phone_dead",
                            device_id=device.device_id,
                            slot=device.user_name,
                        )
                        await self._db.log_activity(
                            "info",
                            "batch",
                            f"Phone {device.user_name}: skipped — phone dead",
                            device.device_id,
                            {"batch_index": batch_index},
                        )
                        self._status["failed"].append({
                            "slot": device.user_name,
                            "device_id": device.device_id,
                            "reason": "phone_dead",
                        })
                        continue
                    if is_cant_cast_imouse(base_key):
                        logger.info(
                            "batch_cast_skipped_tagged",
                            device_id=device.device_id,
                            slot=device.user_name,
                        )
                        await self._db.log_activity(
                            "error",
                            "batch",
                            f"Phone {device.user_name}: skipped — tagged as cant cast iMouse",
                            device.device_id,
                            {"batch_index": batch_index},
                        )
                        self._status["failed"].append({
                            "slot": device.user_name,
                            "device_id": device.device_id,
                            "reason": "cant_cast_imouse",
                        })
                        continue
                    ok = await self._ensure_cast(device.device_id)
                    if ok:
                        connected.append(device)
                    else:
                        self._note_imouse_failure(batch_index, "cast_connect_failed")
                        logger.info(
                            "batch_cast_tagged_cant_cast",
                            device_id=device.device_id,
                            slot=device.user_name,
                        )
                        self._status["failed"].append({
                            "slot": device.user_name,
                            "device_id": device.device_id,
                            "reason": "cast_connect_failed",
                        })
                        if self._should_tag_cant_cast_after_failure():
                            set_cant_cast_imouse(base_key)
                        await self._db.log_activity(
                            "error",
                            "batch",
                            f"Phone {device.user_name}: cast connect failed"
                            + (
                                " — tagged as cant cast iMouse"
                                if self._should_tag_cant_cast_after_failure()
                                else " — kernel recovery may retry"
                            ),
                            device.device_id,
                            {"batch_index": batch_index},
                        )

                resume = await self._check_kernel_recovery(batches, selected_ids)
                if resume is not None:
                    batch_index = resume
                    continue

                if not connected:
                    batch_index += 1
                    continue

                self._status["status"] = "running"
                self._status["message"] = (
                    f"Phone {phone_num}/{phone_total}: running slot {slot_labels[0]}"
                )
                await self._emit("batch_running", self.get_status())

                for device in connected:
                    if self._stop_requested:
                        break
                    valcoin_profile = get_profile_for_device(
                        device.device_id, device.user_name, brand="valcoin"
                    )
                    profile = get_profile_for_device(
                        device.device_id, device.user_name, brand=brand
                    )

                    effective_from_post = from_post
                    base_key = device_storage_key(device.device_id, device.user_name)
                    chain_valcoin = (
                        brand == "labely"
                        and effective_from_post is None
                        and self._config.chain_valcoin_after_labely
                        and str(device.user_name) in self._valcoin_post_slots
                        and not valcoin_profile.get("warmup_enabled")
                    )
                    if profile.get("warmup_enabled"):
                        self._status["message"] = (
                            f"Phone {phone_num}/{phone_total}: warmup slot {device.user_name}"
                        )
                        await self._emit("batch_running", self.get_status())
                        await self._start_session_recording(device)
                        try:
                            await run_tiktok_warmup(
                                self._dm.controller,
                                device,
                                brand=brand,
                                app_config=self._app_config,
                                device_manager=self._dm,
                                stop_check=lambda: self._stop_requested,
                                log_activity=self._db.log_activity,
                                permission_watchers=self._permission_watchers,
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "batch_warmup_failed",
                                device_id=device.device_id,
                                slot=device.user_name,
                                error=str(exc),
                            )
                            self._status["failed"].append({
                                "slot": device.user_name,
                                "device_id": device.device_id,
                                "reason": f"warmup_failed: {exc}",
                            })
                            self._note_imouse_failure(batch_index, f"warmup_failed: {exc}")
                            await self._finish_device_session(device.device_id)
                            resume = await self._check_kernel_recovery(batches, selected_ids)
                            if resume is not None:
                                batch_index = resume
                                break
                            continue
                        if self._stop_requested:
                            break
                        self._status["completed"].append({
                            "slot": device.user_name,
                            "device_id": device.device_id,
                            "event": "warmup_only",
                        })
                        await self._finish_device_session(device.device_id)
                        continue

                    # Caption validation only needed when actually posting.
                    text_key = _post_text_key(device, brand)
                    check_from = effective_from_post if effective_from_post is not None else 1
                    if self._auto_captions and self._app_config.openai.enabled:
                        try:
                            await generate_captions_for_device(
                                self._app_config,
                                device,
                                onscreen_template=default_onscreen_template_for_brand(brand),
                                brand=brand,
                            )
                            if chain_valcoin:
                                await generate_captions_for_device(
                                    self._app_config,
                                    device,
                                    onscreen_template=default_onscreen_template_for_brand(
                                        "valcoin"
                                    ),
                                    brand="valcoin",
                                )
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "batch_auto_caption_failed",
                                device_id=device.device_id,
                                slot=device.user_name,
                                error=str(exc),
                            )
                    missing = validate_post_texts(text_key, from_post=check_from, brand=brand)
                    if chain_valcoin:
                        valcoin_key = _post_text_key(device, "valcoin")
                        missing.extend(
                            validate_post_texts(valcoin_key, from_post=1, brand="valcoin")
                        )
                    if missing:
                        self._status["failed"].append({
                            "slot": device.user_name,
                            "device_id": device.device_id,
                            "reason": "; ".join(missing),
                        })
                        await self._finish_device_session(device.device_id)
                        continue

                    valcoin_warmup_after_labely = (
                        brand == "labely"
                        and bool(valcoin_profile.get("warmup_enabled"))
                    )
                    self._batch_done_events[device.device_id] = asyncio.Event()
                    await self._start_session_recording(device)
                    started = await self._pipeline.start(
                        device.device_id,
                        from_post=effective_from_post,
                        brand=brand,
                        chain_valcoin_after_labely=chain_valcoin,
                        skip_prep_when_valid=self._config.skip_prep_when_valid,
                        skip_labely_end_for_valcoin_warmup=valcoin_warmup_after_labely,
                    )
                    if not started:
                        self._batch_done_events.pop(device.device_id, None)
                        self._status["failed"].append({
                            "slot": device.user_name,
                            "device_id": device.device_id,
                            "reason": "pipeline_start_failed",
                        })
                        await self._finish_device_session(device.device_id)

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
                        self._note_imouse_failure(batch_index, "batch_device_timeout")
                        if self._config.disconnect_on_complete:
                            await self._finish_device_session(device_id)
                        self._batch_done_events.pop(device_id, None)

                resume = await self._check_kernel_recovery(batches, selected_ids)
                if resume is not None:
                    batch_index = resume
                    continue

                if not self._stop_requested and brand == "labely":
                    for device in connected:
                        if self._stop_requested:
                            break
                        vc_profile = get_profile_for_device(
                            device.device_id, device.user_name, brand="valcoin"
                        )
                        if not vc_profile.get("warmup_enabled"):
                            continue
                        if device.device_id not in self._labely_pipeline_ok:
                            logger.info(
                                "batch_valcoin_warmup_skipped_no_labely",
                                device_id=device.device_id,
                                slot=device.user_name,
                            )
                            await self._db.log_activity(
                                "info",
                                "batch",
                                f"ValCoin warmup skipped for slot {device.user_name} — Labely run did not finish",
                                device.device_id,
                            )
                            continue
                        self._status["message"] = (
                            f"Phone {phone_num}/{phone_total}: ValCoin warmup slot {device.user_name}"
                        )
                        await self._emit("batch_running", self.get_status())

                        # Ensure AirPlay is still live before ValCoin warmup scroll.
                        cast_ok = await self._ensure_cast(device.device_id)
                        if not cast_ok:
                            logger.warning(
                                "batch_valcoin_warmup_no_cast",
                                device_id=device.device_id,
                                slot=device.user_name,
                            )
                            await self._db.log_activity(
                                "warn",
                                "batch",
                                f"ValCoin warmup skipped — could not reconnect AirPlay for slot {device.user_name}",
                                device.device_id,
                            )
                            continue

                        try:
                            await run_tiktok_warmup(
                                self._dm.controller,
                                device,
                                brand="valcoin",
                                app_config=self._app_config,
                                device_manager=self._dm,
                                stop_check=lambda: self._stop_requested,
                                log_activity=self._db.log_activity,
                                after_labely=True,
                                permission_watchers=self._permission_watchers,
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "batch_valcoin_warmup_failed",
                                device_id=device.device_id,
                                slot=device.user_name,
                                error=str(exc),
                            )
                            await self._db.log_activity(
                                "warn",
                                "batch",
                                f"ValCoin warmup failed for slot {device.user_name}: {exc}",
                                device.device_id,
                            )

                if not self._stop_requested:
                    self._status["status"] = "disconnecting"
                    self._status["message"] = f"Phone {phone_num}/{phone_total}: disconnecting cast"
                    await self._emit("batch_disconnecting", self.get_status())

                    if self._config.disconnect_on_complete:
                        for device in connected:
                            await self._finish_device_session(device.device_id)

                pause = float(self._config.between_phones_pause_seconds)
                if pause > 0 and batch_index < len(batches) and not self._stop_requested:
                    await asyncio.sleep(pause)

                resume = await self._check_kernel_recovery(batches, selected_ids)
                if resume is not None:
                    batch_index = resume
                    continue

                batch_index += 1

            if self._stop_requested:
                self._status["status"] = "idle"
                self._status["message"] = "Batch run stopped"
            else:
                self._status["status"] = "completed"
                self._status["message"] = (
                    f"Batch run finished — "
                    f"{len(self._status['completed'])} ok, {len(self._status['failed'])} failed"
                )
            await self._emit("batch_completed", self.get_status())
        except asyncio.CancelledError:
            self._status["status"] = "idle"
            self._status["message"] = "Batch run stopped"
            await self._session_recordings.stop_all()
            raise
        except Exception as exc:
            logger.error("batch_run_failed", error=str(exc))
            self._status["status"] = "failed"
            self._status["message"] = str(exc)
            await self._emit("batch_failed", self.get_status())

    def _should_tag_cant_cast_after_failure(self) -> bool:
        cfg = self._config.kernel_recovery
        if not cfg.enabled:
            return True
        if self._kernel_recovery_count >= cfg.max_recovery_attempts:
            return True
        if self._pending_kernel_recovery_batch_index is not None:
            return False
        if self._imouse_failure_count < cfg.failure_threshold:
            return False
        return False

    def _note_imouse_failure(self, batch_index: int, reason: str) -> None:
        if not is_imouse_failure(reason):
            return
        if self._first_imouse_failure_batch_index is None:
            self._first_imouse_failure_batch_index = batch_index
        self._imouse_failure_count += 1
        cfg = self._config.kernel_recovery
        if (
            cfg.enabled
            and self._imouse_failure_count >= cfg.failure_threshold
            and self._kernel_recovery_count < cfg.max_recovery_attempts
        ):
            self._pending_kernel_recovery_batch_index = self._first_imouse_failure_batch_index

    def _prune_failed_for_retry(self, retry_slots: set[str]) -> None:
        if not retry_slots:
            return
        self._status["failed"] = [
            entry
            for entry in self._status["failed"]
            if str(entry.get("slot") or "") not in retry_slots
        ]

    async def _check_kernel_recovery(
        self,
        batches: list[list[Any]],
        selected_ids: set[str],
    ) -> int | None:
        resume = self._pending_kernel_recovery_batch_index
        if resume is None:
            return None
        if await self._execute_kernel_recovery(batches, resume, selected_ids):
            return resume
        self._pending_kernel_recovery_batch_index = None
        return None

    async def _execute_kernel_recovery(
        self,
        batches: list[list[Any]],
        resume_index: int,
        selected_ids: set[str],
    ) -> bool:
        cfg = self._config.kernel_recovery
        self._kernel_recovery_count += 1
        self._pending_kernel_recovery_batch_index = None
        self._imouse_failure_count = 0
        self._first_imouse_failure_batch_index = None

        retry_batches = batches[resume_index - 1 :]
        retry_slots = {str(d.user_name) for batch in retry_batches for d in batch}
        self._prune_failed_for_retry(retry_slots)

        for batch in retry_batches:
            for device in batch:
                clear_cant_cast_imouse(
                    device_storage_key(device.device_id, device.user_name)
                )

        phone_total = len(batches)
        await self._db.log_activity(
            "warn",
            "batch",
            (
                f"iMouseXP failed on {cfg.failure_threshold}+ phone(s) — restarting kernel, "
                f"recasting, and resuming from phone {resume_index}/{phone_total}"
            ),
        )
        self._status["status"] = "connecting"
        self._status["message"] = (
            f"Kernel recovery {self._kernel_recovery_count}/{cfg.max_recovery_attempts}: "
            f"restarting iMouseXP and resuming at phone {resume_index}"
        )
        await self._emit("batch_connecting", self.get_status())

        for batch in batches:
            for device in batch:
                await self._finish_device_session(device.device_id, disconnect=True)

        if not await self._dm.controller.restart_imouse_kernel():
            await self._db.log_activity("error", "batch", "iMouseXP kernel restart failed")
            return False

        await asyncio.sleep(float(cfg.kernel_restart_wait_seconds))
        await self._dm.controller.reconnect()
        await self._dm.refresh_devices()

        for batch in retry_batches:
            for device in batch:
                await self._dm.reconnect_airplay(device.device_id)
                await asyncio.sleep(self._connect_delay)

        self._labely_pipeline_ok.intersection_update(
            {d.device_id for batch in batches[: resume_index - 1] for d in batch}
        )
        self._batch_done_events.clear()

        self._status["message"] = (
            f"Kernel restarted — resuming from phone {resume_index}/{phone_total}"
        )
        await self._emit("batch_running", self.get_status())
        logger.info(
            "batch_kernel_recovery_complete",
            resume_index=resume_index,
            recovery_count=self._kernel_recovery_count,
        )
        return True

    async def _start_session_recording(self, device: Any) -> None:
        cfg = self._config.session_recording
        if not cfg.enabled:
            return
        slot = str(device.user_name).strip()
        if not slot:
            return
        path = session_recording_path(self._app_config.gallery.base_directory, slot)
        await self._session_recordings.start(
            self._dm.controller,
            device.device_id,
            slot,
            path,
            fps=float(cfg.fps),
            log_activity=self._db.log_activity,
        )

    async def _finish_device_session(self, device_id: str, *, disconnect: bool = True) -> None:
        await self._session_recordings.stop(device_id, log_activity=self._db.log_activity)
        if disconnect:
            await self._dm.disconnect_airplay(device_id)

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
        if event not in (
            "pipeline_completed",
            "pipeline_failed",
            "pipeline_stopped",
            "pipeline_paused",
        ):
            return

        slot = None
        device = self._dm.get_device(device_id)
        if device:
            slot = device.user_name

        entry = {"slot": slot, "device_id": device_id, "event": event}
        if event == "pipeline_completed":
            self._status["completed"].append(entry)
            if self._current_brand == "labely":
                self._labely_pipeline_ok.add(str(device_id))
        else:
            entry["reason"] = data.get("message") or (
                "paused" if event == "pipeline_paused" else event
            )
            self._status["failed"].append(entry)
            if self._active_batch_index:
                self._note_imouse_failure(
                    self._active_batch_index,
                    str(entry["reason"]),
                )
            if event == "pipeline_paused":
                await self._db.log_activity(
                    "warn",
                    "batch",
                    f"Pipeline paused for slot {slot or device_id} — skipping to next phone",
                    device_id,
                )

        # Keep AirPlay up when the user kills a run; only decast after a normal finish.
        # Also skip auto-disconnect if ValCoin warmup is pending — the batch loop
        # disconnects after warmup completes.
        valcoin_warmup_pending = False
        if device and event == "pipeline_completed" and self._current_brand == "labely":
            vc_profile = get_profile_for_device(
                device.device_id, device.user_name, brand="valcoin"
            )
            valcoin_warmup_pending = bool(vc_profile.get("warmup_enabled"))

        disconnect = (
            event == "pipeline_completed"
            and self._config.disconnect_on_complete
            and not valcoin_warmup_pending
        )
        if not (event == "pipeline_completed" and valcoin_warmup_pending):
            await self._finish_device_session(device_id, disconnect=disconnect)

        done = self._batch_done_events.pop(device_id, None)
        if done:
            done.set()

        if event == "pipeline_paused":
            await self._pipeline.stop(device_id)
