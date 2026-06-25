"""Screenshot-driven workflow execution engine."""

from __future__ import annotations

import asyncio
import random
import re
import time
from pathlib import Path
from typing import Any, Callable, Awaitable

from imouse_farm.actions.engine import ActionEngine
from imouse_farm.config.models import (
    ActionType,
    AppConfig,
    DetectionResult,
    DeviceState,
    WorkflowConfig,
    WorkflowStepConfig,
)
from imouse_farm.database.repository import DatabaseRepository
from imouse_farm.devices.manager import DeviceManager
from imouse_farm.permissions.watcher import PermissionWatcherManager
from imouse_farm.popups.manager import PopupManager
from imouse_farm.screenshots.service import ScreenshotService
from imouse_farm.state.machine import StateMachine
from imouse_farm.captions.ai_generator import stem_to_food_name
from imouse_farm.post.post_caption_store import (
    POST_COUNT,
    device_storage_key,
    get_final_caption,
    get_gallery_coords,
    get_onscreen_text,
    post_media_stem,
)
from imouse_farm.settings.device_settings import get_debug_skip_post
from imouse_farm.utils.gallery import list_media_stems_for_posts, phone_gallery_folder
from imouse_farm.utils.logging import get_logger
from imouse_farm.vision.fallbacks import (
    apply_detection_fallbacks,
    apply_exclusive_detections,
    apply_tap_offsets,
    detection_satisfied,
    DETECTION_FALLBACKS,
    expand_template_names,
    resolve_template_state_fallback,
)

logger = get_logger(__name__)

EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class WorkflowRunner:
    """State-based workflow runner for a single device.

    Core loop: Screenshot → Analyze → Determine state → Action → Verify
    Never blindly executes coordinate-based actions without prior analysis.
    """

    def __init__(
        self,
        workflow: WorkflowConfig,
        device_id: str,
        config: AppConfig,
        device_manager: DeviceManager,
        screenshot_service: ScreenshotService,
        vision: VisionProvider,
        popup_manager: PopupManager,
        state_machine: StateMachine,
        action_engine: ActionEngine,
        db: DatabaseRepository,
        on_event: EventCallback | None = None,
        on_finished: Callable[[str], Awaitable[None]] | None = None,
        start_post_index: int = 1,
    ) -> None:
        self._workflow = workflow
        self._device_id = device_id
        self._config = config
        self._device_manager = device_manager
        self._screenshots = screenshot_service
        self._vision = vision
        self._popups = popup_manager
        self._state_machine = state_machine
        self._actions = action_engine
        self._db = db
        self._on_event = on_event
        self._on_finished = on_finished
        self._running = False
        self._step_failed = False
        self._failure_message = ""
        self._task: asyncio.Task[None] | None = None
        self._variables: dict[str, Any] = dict(workflow.variables)
        self._last_analysis: VisionAnalysis | None = None
        self._last_screenshot: dict[str, Any] | None = None
        self._run_id: int | None = None
        self._has_recent_screenshot = False
        self._has_recent_analysis = False
        self._start_post_index = max(1, int(start_post_index))

    @property
    def start_post_index(self) -> int:
        return self._start_post_index

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def workflow_name(self) -> str:
        return self._workflow.name

    async def start(self) -> None:
        if self._running:
            return
        self._init_device_variables()
        self._running = True
        self._step_failed = False
        self._failure_message = ""
        self._run_id = await self._db.start_workflow_run(self._workflow.name, self._device_id)
        await self._device_manager.set_workflow(self._device_id, self._workflow.name)
        await self._device_manager.resume_workflow(self._device_id)
        self._task = asyncio.create_task(self._run_loop())
        start_msg = f"Started {self._workflow.name}"
        if self._start_post_index > 1:
            start_msg += f" (from post {self._start_post_index})"
        await self._log_activity(
            "info",
            "workflow",
            start_msg,
        )
        logger.info(
            "workflow_started",
            workflow=self._workflow.name,
            device_id=self._device_id,
            start_post_index=self._start_post_index,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._run_id:
            await self._db.complete_workflow_run(self._run_id, "stopped")
        await self._device_manager.set_workflow(self._device_id, "")
        await self._log_activity("warn", "workflow", f"Stopped {self._workflow.name}")
        logger.info("workflow_stopped", workflow=self._workflow.name, device_id=self._device_id)

    async def _run_loop(self) -> None:
        max_iter = self._workflow.max_iterations
        start_at = self._start_post_index
        if max_iter > 0:
            start_at = min(start_at, max_iter)
        iteration = start_at - 1
        try:
            while self._running:
                if await self._device_manager.is_workflow_paused(self._device_id):
                    await asyncio.sleep(2)
                    continue

                iteration += 1
                if max_iter > 0 and iteration > max_iter:
                    break

                self._refresh_post_variables(iteration)
                await self._log_activity(
                    "info",
                    "workflow",
                    f"{self._workflow.name} post {iteration}/{self._workflow.max_iterations or iteration}",
                )

                for step in self._workflow.steps:
                    if not self._running:
                        break
                    if await self._device_manager.is_workflow_paused(self._device_id):
                        break
                    await self._execute_step(step)

                if not self._workflow.loop:
                    break
                await asyncio.sleep(self._config.timing.workflow_step_delay_seconds)

            if self._step_failed:
                if self._run_id:
                    await self._db.complete_workflow_run(
                        self._run_id, "failed", self._failure_message
                    )
                if self._on_event:
                    await self._on_event("workflow_failed", {
                        "device_id": self._device_id,
                        "workflow": self._workflow.name,
                        "message": self._failure_message,
                    })
            else:
                if self._run_id:
                    await self._db.complete_workflow_run(self._run_id, "completed")
                if self._on_event:
                    await self._on_event("workflow_completed", {
                        "device_id": self._device_id,
                        "workflow": self._workflow.name,
                    })
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("workflow_error", workflow=self._workflow.name, device_id=self._device_id, error=str(exc))
            if self._run_id:
                await self._db.complete_workflow_run(self._run_id, "failed", str(exc))
            await self._db.log_error("workflow_error", str(exc), self._device_id)
            await self._device_manager.record_failure(self._device_id)
        finally:
            self._running = False
            await self._device_manager.set_workflow(self._device_id, "")
            if self._on_finished:
                await self._on_finished(self._device_id)

    def _init_device_variables(self) -> None:
        device = self._device_manager.get_device(self._device_id)
        if not device:
            return
        folder = phone_gallery_folder(
            self._config.gallery.base_directory,
            device.user_name,
            device.phone_name,
        )
        self._variables["phone_name"] = device.phone_name
        self._variables["device_slot"] = device.user_name
        self._variables["gallery_folder"] = str(folder)
        logger.info(
            "workflow_variables",
            device_id=self._device_id,
            slot=device.user_name,
            phone=device.phone_name,
            gallery_folder=str(folder),
        )

    def _post_text_key(self) -> str:
        device = self._device_manager.get_device(self._device_id)
        if device:
            return device_storage_key(device.device_id, device.user_name)
        return self._device_id

    def _refresh_post_variables(self, post_index: int) -> None:
        self._variables["post_index"] = post_index
        text_key = self._post_text_key()
        device = self._device_manager.get_device(self._device_id)
        media_stems: list[str] = []
        if device:
            folder = phone_gallery_folder(
                self._config.gallery.base_directory,
                device.user_name,
                device.phone_name,
            )
            media_stems = list_media_stems_for_posts(
                folder,
                self._config.gallery.media_extensions,
                POST_COUNT,
            )
        stem = post_media_stem(media_stems, post_index)
        food_name = stem_to_food_name(stem) if stem else ""
        onscreen = get_onscreen_text(text_key, post_index)
        final_caption = get_final_caption(text_key, post_index)
        gx, gy = get_gallery_coords(post_index)
        self._variables["post_caption"] = onscreen
        self._variables["final_post_caption"] = final_caption
        self._variables["media_stem"] = stem
        self._variables["food_name"] = food_name
        self._variables["gallery_x"] = gx
        self._variables["gallery_y"] = gy
        logger.info(
            "workflow_post_variables",
            device_id=self._device_id,
            post_index=post_index,
            media_stem=stem,
            food_name=food_name,
            gallery_x=gx,
            gallery_y=gy,
            onscreen_len=len(onscreen),
            final_len=len(final_caption),
        )

    def _filter_min_confidence(self, detections: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        if not hasattr(self._vision, "min_confidence_for"):
            return detections
        result = dict(detections)
        for name in list(result):
            min_conf = self._vision.min_confidence_for(name)
            if min_conf is not None and float(result[name].get("confidence", 0)) < min_conf:
                del result[name]
        return result

    def _current_detections(self) -> dict[str, dict[str, Any]]:
        detections: dict[str, dict[str, Any]] = {}
        if self._last_analysis:
            detections = {
                d.name: {"x": d.x, "y": d.y, "confidence": d.confidence}
                for d in self._last_analysis.detections
            }
        stored = self._actions._last_detections.get(self._device_id, {})
        for name, hit in stored.items():
            if name not in detections:
                detections[name] = dict(hit)
        return detections

    def _has_detection(self, name: str) -> bool:
        if not name:
            return False
        detections = apply_detection_fallbacks(self._current_detections())
        return detection_satisfied(detections, name)

    def _set_detection(self, name: str, hit: dict[str, Any]) -> None:
        entry = {
            "x": int(hit["x"]),
            "y": int(hit["y"]),
            "confidence": float(hit.get("confidence", 1.0)),
        }
        if hit.get("matched_via"):
            entry["matched_via"] = hit["matched_via"]
        detections = self._current_detections()
        detections[name] = entry
        self._actions.set_detections(self._device_id, detections)
        if self._last_analysis:
            remaining = [d for d in self._last_analysis.detections if d.name != name]
            remaining.append(
                DetectionResult(
                    name=name,
                    confidence=entry["confidence"],
                    x=entry["x"],
                    y=entry["y"],
                    detection_type=str(hit.get("detection_type", "ocr")),
                )
            )
            self._last_analysis.detections = remaining

    async def _device_ocr_best_hit(
        self,
        texts: list[str],
        *,
        threshold: float = 0.75,
        prefer_bottom: bool = False,
    ) -> dict[str, Any] | None:
        ctrl = self._device_manager.controller
        for text in texts:
            query = str(text).strip()
            if not query:
                continue
            matches = await ctrl.find_text_on_device(
                self._device_id,
                [query],
                threshold=threshold,
                contain=True,
            )
            if not matches:
                continue
            if prefer_bottom:
                best = max(
                    matches,
                    key=lambda m: (int(m["y"]), float(m.get("confidence", 0))),
                )
            else:
                best = max(matches, key=lambda m: float(m.get("confidence", 0)))
            return {**best, "text": best.get("text") or query}
        return None

    async def _log_activity(
        self,
        level: str,
        category: str,
        message: str,
        **details: Any,
    ) -> None:
        await self._db.log_activity(
            level,
            category,
            message,
            self._device_id,
            {"workflow": self._workflow.name, **details},
        )

    def _step_skip_reason(self, step: WorkflowStepConfig) -> str | None:
        if step.when_state:
            device = self._device_manager.get_device(self._device_id)
            if device and device.current_state != step.when_state:
                return f"state is {device.current_state.value}, need {step.when_state.value}"
        if (
            step.when_detection
            and step.type != "wait_for_detection"
            and not self._has_detection(step.when_detection)
        ):
            return f"'{step.when_detection}' not detected"
        if step.unless_detection and self._has_detection(step.unless_detection):
            return f"'{step.unless_detection}' is present"
        if step.when_post_index is not None:
            current = int(self._variables.get("post_index", 0))
            if current != step.when_post_index:
                return f"post {current}, need post {step.when_post_index}"
        debug_skip = get_debug_skip_post(self._device_id)
        if step.when_debug_skip_post is True and not debug_skip:
            return "debug skip post is off"
        if step.unless_debug_skip_post is True and debug_skip:
            return "debug skip post is on"
        return None

    async def _execute_step(self, step: WorkflowStepConfig) -> None:
        skip = self._step_skip_reason(step)
        if skip:
            if not step.name.startswith("_"):
                await self._log_activity(
                    "debug",
                    "workflow",
                    f"Skip {step.name} ({step.type})",
                    reason=skip,
                )
            return

        if not step.name.startswith("_"):
            await self._log_activity(
                "info",
                "workflow",
                f"→ {step.name}",
                step_type=step.type,
            )

        if step.requires_screenshot and not self._has_recent_screenshot:
            await self._step_capture(WorkflowStepConfig(type="capture_screen", name="_auto_capture"))
        if step.requires_analysis and not self._has_recent_analysis:
            await self._step_analyze(WorkflowStepConfig(type="analyze_screen", name="_auto_analyze"))

        try:
            match step.type:
                case "screenshot" | "capture_screen":
                    await self._step_capture(step)
                case "analyze" | "analyze_screen":
                    await self._step_analyze(step)
                case "determine_state":
                    await self._step_determine_state(step)
                case "check_ocr_state":
                    await self._step_check_ocr_state(step)
                case "check_popups" | "handle_popups":
                    await self._step_check_popups(step)
                case "execute_action":
                    await self._step_action(step)
                case "verify":
                    await self._step_verify(step)
                case "wait" | "wait_random":
                    await self._step_wait(step)
                case "wait_for_detection":
                    await self._step_wait_for_detection(step)
                case _:
                    logger.warning("unknown_step_type", step_type=step.type, name=step.name)
        except Exception as exc:
            logger.error("step_failed", step=step.name, device_id=self._device_id, error=str(exc))
            await self._log_activity(
                "error",
                "workflow",
                f"Step failed: {step.name} — {exc}",
                step_type=step.type,
            )
            await self._handle_failure(step, exc)

    async def _step_capture(self, step: WorkflowStepConfig) -> None:
        self._last_screenshot = await self._screenshots.capture(
            self._device_id, workflow_id=self._workflow.name
        )
        if not self._last_screenshot:
            raise RuntimeError("Screenshot capture failed")
        self._has_recent_screenshot = True
        self._has_recent_analysis = False

    async def _device_ocr_has_text(
        self,
        texts: list[str],
        *,
        threshold: float = 0.65,
    ) -> tuple[bool, str]:
        """Return whether any label is visible via on-device OCR."""
        ctrl = self._device_manager.controller
        for text in texts:
            query = str(text).strip()
            if not query:
                continue
            queries = [query]
            if query != query.upper():
                queries.append(query.upper())
            if query != query.lower():
                queries.append(query.lower())
            for candidate in queries:
                matches = await ctrl.find_text_on_device(
                    self._device_id,
                    [candidate],
                    threshold=threshold,
                    contain=True,
                )
                if matches:
                    hit = max(matches, key=lambda m: float(m.get("confidence", 0)))
                    return True, str(hit.get("text") or candidate)
        return False, ""

    async def _step_check_ocr_state(self, step: WorkflowStepConfig) -> None:
        """Set device state from on-device OCR, with optional template fallback."""
        action = self._resolve_variables(step.action)
        texts = [str(t) for t in (action.get("texts") or ["Not Connected"]) if str(t).strip()]
        threshold = float(action.get("threshold", 0.65))
        retry_delay = float(action.get("retry_delay", 1.5))
        timeout = float(action.get("duration_seconds", 12))
        state_if_found = DeviceState(action.get("state_if_found", "WAITING"))
        state_if_missing = DeviceState(action.get("state_if_missing", "ACTIVE"))
        fallback_template = str(action.get("fallback_template") or "").strip() or None
        state_if_fallback = DeviceState(action.get("state_if_fallback", "WAITING"))
        fallback_min_confidence = float(action.get("fallback_min_confidence", 0.42))
        raw_fallback_templates = action.get("fallback_templates")
        require_state = action.get("require_state")
        required = DeviceState(require_state) if require_state else None

        deadline = time.monotonic() + timeout
        matched_text = ""
        found = False
        while self._running:
            found, matched_text = await self._device_ocr_has_text(
                texts, threshold=threshold
            )
            if found or time.monotonic() >= deadline:
                break
            await asyncio.sleep(retry_delay)

        if found:
            state = state_if_found
            reason = f"found '{matched_text}'"
        else:
            state = state_if_missing
            reason = f"'{texts[0]}' not found"
            fallback_entries: list[dict[str, Any]] = []
            if isinstance(raw_fallback_templates, list) and raw_fallback_templates:
                fallback_entries = [
                    entry for entry in raw_fallback_templates if isinstance(entry, dict)
                ]
            elif fallback_template:
                fallback_entries = [{
                    "template": fallback_template,
                    "state": state_if_fallback.value,
                    "min_confidence": fallback_min_confidence,
                }]
            if fallback_entries and state == state_if_missing:
                template_names = [
                    str(entry.get("template") or "").strip()
                    for entry in fallback_entries
                ]
                template_names = [name for name in template_names if name]
                if template_names:
                    capture = WorkflowStepConfig(
                        type="screenshot",
                        name=f"{step.name}_fallback_capture",
                        templates=template_names,
                    )
                    analyze = WorkflowStepConfig(
                        type="analyze_screen",
                        name=f"{step.name}_fallback_analyze",
                        templates=template_names,
                    )
                    await self._step_capture(capture)
                    await self._step_analyze(analyze)
                    detections = self._actions._last_detections.get(self._device_id, {})
                    winner, conf = resolve_template_state_fallback(
                        detections, fallback_entries
                    )
                    if winner:
                        for entry in fallback_entries:
                            if str(entry.get("template") or "").strip() == winner:
                                state = DeviceState(entry.get("state", state_if_fallback.value))
                                break
                        reason = f"OCR missed but {winner} visible (conf={conf:.2f})"

        await self._state_machine.transition(
            self._device_id, state, reason=f"workflow:{step.name}", force=True
        )
        await self._log_activity(
            "info",
            "workflow",
            f"VPN status → {state.value} ({reason})",
            step=step.name,
            matched_text=matched_text or None,
            texts=texts,
        )
        if required and state != required:
            raise RuntimeError(
                f"VPN check expected state {required.value}, got {state.value} ({reason})"
            )

    async def _merge_device_ocr_keywords(self, keywords: list[str]) -> None:
        """Supplement local OCR with on-device text search (better for Shadowrocket)."""
        if not self._last_analysis:
            return
        ctrl = self._device_manager.controller
        extras: list[str] = []
        for keyword in keywords:
            kw = str(keyword).strip()
            if not kw:
                continue
            queries = [kw]
            if kw != kw.upper():
                queries.append(kw.upper())
            if kw != kw.lower():
                queries.append(kw.lower())
            for query in queries:
                matches = await ctrl.find_text_on_device(
                    self._device_id,
                    [query],
                    threshold=0.72,
                    contain=True,
                )
                if matches:
                    extras.append(kw)
                    for match in matches:
                        text = str(match.get("text", "")).strip()
                        if text:
                            extras.append(text)
                    break
        if extras:
            merged = f"{self._last_analysis.ocr_text} {' '.join(extras)}".strip()
            self._last_analysis.ocr_text = merged
            logger.info(
                "device_ocr_keywords_merged",
                device_id=self._device_id,
                keywords=keywords,
                matched=extras,
            )

    async def _step_analyze(self, step: WorkflowStepConfig) -> None:
        if not self._last_screenshot:
            path = await self._screenshots.get_latest_path(self._device_id)
            if not path:
                raise RuntimeError("No screenshot available — capture first")
            screenshot_path = path
        else:
            screenshot_path = self._last_screenshot["file_path"]

        template_names = expand_template_names(step.templates or None)
        self._last_analysis = self._vision.analyze(
            self._device_id,
            screenshot_path,
            template_names=template_names or None,
            ocr_regions=step.ocr_regions or None,
            ocr_keywords=step.ocr_keywords or None,
        )
        if step.ocr_keywords:
            await self._merge_device_ocr_keywords(step.ocr_keywords)
        self._has_recent_analysis = True

        detections = {
            d.name: {"x": d.x, "y": d.y, "confidence": d.confidence}
            for d in self._last_analysis.detections
        }
        detections = await self._merge_device_template_detections(
            template_names, detections
        )
        detections = apply_detection_fallbacks(detections)
        detections = apply_exclusive_detections(detections)
        detections = self._filter_min_confidence(detections)
        if hasattr(self._vision, "tap_offset_for"):
            detections = apply_tap_offsets(detections, self._vision.tap_offset_for)
        self._actions.set_detections(self._device_id, detections)
        self._last_analysis.detections = [
            DetectionResult(
                name=name,
                confidence=float(hit["confidence"]),
                x=int(hit["x"]),
                y=int(hit["y"]),
                detection_type="template",
            )
            for name, hit in detections.items()
        ]

        logger.info(
            "screen_analyzed",
            device_id=self._device_id,
            state=self._last_analysis.detected_state.value if self._last_analysis.detected_state else None,
            detections=list(detections.keys()),
            provider=self._last_analysis.provider,
        )
        if step.name and not step.name.startswith("_"):
            det_list = (
                ", ".join(
                    f"{k} ({detections[k]['confidence']:.2f})"
                    for k in sorted(detections)
                )
                if detections
                else "none"
            )
            await self._log_activity(
                "info",
                "vision",
                f"Analyze: found [{det_list}]",
                step=step.name,
                detections=list(detections.keys()),
            )

    async def _merge_device_template_detections(
        self,
        template_names: list[str],
        detections: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Supplement local OpenCV matches with iMouse on-device find (better for small icons)."""
        if not self._config.analysis.use_device_template_match or not template_names:
            return detections
        if not hasattr(self._vision, "template_path_for"):
            return detections

        controller = self._device_manager.controller
        device = self._device_manager.get_device(self._device_id)
        sw = int(device.screen_width) if device and device.screen_width else 406
        sh = int(device.screen_height) if device and device.screen_height else 720
        for name in template_names:
            path = self._vision.template_path_for(name)
            if not path:
                continue
            threshold = self._vision.threshold_for(name)
            if hasattr(self._vision, "device_threshold_for"):
                threshold = self._vision.device_threshold_for(name)
            rect = (
                self._vision.search_rect_for(name, width=sw, height=sh)
                if hasattr(self._vision, "search_rect_for")
                else None
            )
            hit = await controller.find_template_on_device(
                self._device_id, path, threshold, rect=rect
            )
            if not hit:
                continue
            existing = detections.get(name)
            if not existing or hit["confidence"] >= existing.get("confidence", 0):
                detections[name] = hit
                logger.info(
                    "device_template_match",
                    device_id=self._device_id,
                    template=name,
                    confidence=hit["confidence"],
                    x=hit["x"],
                    y=hit["y"],
                )
        return detections

    async def _step_determine_state(self, step: WorkflowStepConfig) -> None:
        if not self._last_analysis:
            raise RuntimeError("No analysis — run analyze step first")

        if step.state_rules:
            state = self._vision.evaluate_state_rules(step.state_rules, self._last_analysis)
        elif self._last_analysis.detected_state:
            state = self._last_analysis.detected_state
        else:
            state = DeviceState.UNKNOWN_SCREEN

        await self._state_machine.transition(self._device_id, state, reason=f"workflow:{step.name}")

        device = self._device_manager.get_device(self._device_id)
        if device:
            if state == DeviceState.UNKNOWN_SCREEN:
                device.unknown_screen_count += 1
            else:
                device.unknown_screen_count = 0

    async def _step_check_popups(self, step: WorkflowStepConfig) -> None:
        if not self._last_analysis or not self._last_screenshot:
            raise RuntimeError("Screenshot + analysis required before popup check")

        result = await self._popups.handle(
            self._device_id,
            self._last_analysis,
            self._last_screenshot["file_path"],
            self._workflow.name,
        )

        if result.detected:
            await self._db.log_error(
                "popup_detected",
                result.message,
                self._device_id,
                details={"popup_type": result.popup_type.value if result.popup_type else None},
            )

        if result.should_pause:
            await self._device_manager.pause_workflow(self._device_id)
            await self._state_machine.transition(
                self._device_id, DeviceState.UNKNOWN_SCREEN, "popup_pause", force=True
            )
            self._running = False
            return

        if result.dismiss_action and result.detected and not result.should_pause:
            action_def = self._resolve_variables(result.dismiss_action)
            action_type = ActionType(action_def.get("type", "tap_detection"))
            params = {k: v for k, v in action_def.items() if k != "type"}
            await self._actions.execute_direct(
                self._device_id, action_type, params,
                workflow_id=self._workflow.name, step_name=f"dismiss_{step.name}",
            )
            await self._step_capture(WorkflowStepConfig(type="screenshot", name="_post_dismiss"))
            await self._step_analyze(WorkflowStepConfig(type="analyze", name="_post_dismiss_analyze"))

    async def _step_action(self, step: WorkflowStepConfig) -> None:
        if step.name in ("tap_gallery_item", "type_onscreen_text", "type_final_post_caption"):
            post_index = int(self._variables.get("post_index", 0))
            if post_index >= 1:
                self._refresh_post_variables(post_index)
                await self._log_activity(
                    "info",
                    "workflow",
                    (
                        f"Post {post_index}: {self._variables.get('media_stem') or '(no file)'} "
                        f"→ gallery ({self._variables.get('gallery_x')}, "
                        f"{self._variables.get('gallery_y')})"
                    ),
                    step=step.name,
                )

        if step.requires_analysis and not self._has_recent_analysis:
            raise RuntimeError(
                f"Action '{step.name}' blocked: screenshot-driven automation requires "
                "analyze step before execute_action"
            )

        action_def = self._resolve_variables(step.action)
        action_type = ActionType(action_def.get("type", "tap_detection"))
        params = {k: v for k, v in action_def.items() if k != "type"}

        if (
            action_type == ActionType.TAP_DETECTION
            and params.get("refind_on_device")
            and params.get("detection")
        ):
            detection_name = str(params["detection"])
            refind_templates = expand_template_names([detection_name])
            await self._step_capture(
                WorkflowStepConfig(
                    type="screenshot",
                    name=f"{step.name}_refind_capture",
                    templates=refind_templates,
                )
            )
            await self._step_analyze(
                WorkflowStepConfig(
                    type="analyze_screen",
                    name=f"{step.name}_refind_analyze",
                    templates=refind_templates,
                )
            )
            current = dict(self._actions._last_detections.get(self._device_id, {}))
            refreshed = await self._merge_device_template_detections(
                refind_templates, current
            )
            refreshed = apply_detection_fallbacks(refreshed)
            refreshed = self._filter_min_confidence(refreshed)
            self._actions.set_detections(self._device_id, refreshed)
            hit = refreshed.get(detection_name)
            if hit:
                await self._log_activity(
                    "info",
                    "vision",
                    f"Refind {detection_name} → ({hit['x']}, {hit['y']}) conf={hit.get('confidence')}",
                    step=step.name,
                )
            elif not params.get("optional", False):
                raise RuntimeError(
                    f"Refind failed for '{detection_name}' — confidence below minimum"
                )

        if action_type == ActionType.TAP and "x" in params and "y" in params and "detection" not in params:
            logger.warning(
                "blind_tap_warning",
                device_id=self._device_id,
                step=step.name,
                message="Coordinate tap without detection — prefer tap_detection",
            )

        if action_type == ActionType.TAP_DETECTION and params.get("detection"):
            det_name = str(params["detection"])
            hit = self._actions._last_detections.get(self._device_id, {}).get(det_name)
            if hit and not step.name.startswith("_"):
                via = hit.get("matched_via", "")
                via_note = f" (via {via})" if via else ""
                await self._log_activity(
                    "info",
                    "vision",
                    f"Tap {det_name}{via_note} at ({hit['x']}, {hit['y']}) conf={hit.get('confidence')}",
                    step=step.name,
                )

        success = await self._actions.execute_direct(
            self._device_id, action_type, params,
            workflow_id=self._workflow.name, step_name=step.name,
        )
        if not success:
            raise RuntimeError(f"Action failed: {step.name}")

        if step.skip_post_action:
            return

        self._has_recent_screenshot = False
        self._has_recent_analysis = False

        await asyncio.sleep(0.5)
        await self._step_capture(WorkflowStepConfig(type="capture_screen", name="_post_action_verify"))
        await self._step_analyze(WorkflowStepConfig(type="analyze_screen", name="_post_action_analyze"))

    async def _step_verify(self, step: WorkflowStepConfig) -> None:
        if not self._last_analysis:
            raise RuntimeError("No analysis for verification")
        passed = self._vision.verify_condition(
            step.condition or "", step.template, self._last_analysis
        )
        if not passed:
            if step.on_failure == "continue":
                await self._log_activity(
                    "warn",
                    "workflow",
                    f"Verify failed (continuing): {step.name}",
                    template=step.template,
                )
                logger.warning("verify_failed_continuing", step=step.name, device_id=self._device_id)
                return
            raise RuntimeError(f"Verification failed: {step.name}")

    async def _step_wait(self, step: WorkflowStepConfig) -> None:
        if step.type == "wait_random" or (step.min_seconds and step.max_seconds):
            duration = random.uniform(
                step.min_seconds or 1.0,
                step.max_seconds or step.min_seconds or 3.0,
            )
        else:
            duration = step.duration_seconds or 1.0
        await asyncio.sleep(duration)

    async def _step_wait_for_detection(self, step: WorkflowStepConfig) -> None:
        """Poll screenshot + analyze until a template is detected or timeout."""
        target = step.when_detection or step.template
        if not target and step.templates:
            target = step.templates[0]
        if not target:
            raise RuntimeError(f"wait_for_detection '{step.name}' needs when_detection or templates")

        action_cfg = self._resolve_variables(step.action or {})
        ocr_texts = [
            str(t).strip()
            for t in (action_cfg.get("ocr_fallback_texts") or [])
            if str(t).strip()
        ]
        ocr_as = str(action_cfg.get("ocr_fallback_as") or "post_ocr").strip() or "post_ocr"
        ocr_threshold = float(action_cfg.get("ocr_threshold", 0.75))
        ocr_prefer_bottom = bool(action_cfg.get("ocr_prefer_bottom", False))

        if ocr_texts:
            cleared = self._current_detections()
            cleared.pop(ocr_as, None)
            self._actions.set_detections(self._device_id, cleared)

        templates = expand_template_names(step.templates or [target])
        timeout = float(step.duration_seconds or 90.0)
        poll = float(step.min_seconds or 2.0)
        deadline = time.monotonic() + timeout
        attempt = 0

        await self._log_activity(
            "info",
            "workflow",
            f"Waiting for {target}"
            + (f" or OCR {ocr_texts!r}" if ocr_texts else "")
            + f" (up to {int(timeout)}s)",
            detection=target,
        )

        while self._running:
            if await self._device_manager.is_workflow_paused(self._device_id):
                await asyncio.sleep(2)
                continue

            attempt += 1
            capture_step = WorkflowStepConfig(
                type="screenshot",
                name=f"{step.name}_capture",
                templates=templates,
            )
            analyze_step = WorkflowStepConfig(
                type="analyze_screen",
                name=f"{step.name}_analyze",
                templates=templates,
            )
            await self._step_capture(capture_step)
            await self._step_analyze(analyze_step)

            if self._has_detection(target):
                hit = next(
                    (d for d in self._last_analysis.detections if d.name == target),
                    None,
                ) if self._last_analysis else None
                if not hit:
                    for d in self._last_analysis.detections if self._last_analysis else []:
                        if d.name in (DETECTION_FALLBACKS.get(target) or []):
                            hit = d
                            break
                conf = f"{hit.confidence:.2f}" if hit else "?"
                await self._log_activity(
                    "info",
                    "workflow",
                    f"Found {target} after {attempt} attempt(s) (conf={conf})",
                    detection=target,
                    attempts=attempt,
                    confidence=float(hit.confidence) if hit else None,
                )
                return

            if ocr_texts:
                ocr_hit = await self._device_ocr_best_hit(
                    ocr_texts,
                    threshold=ocr_threshold,
                    prefer_bottom=ocr_prefer_bottom,
                )
                if ocr_hit:
                    self._set_detection(
                        ocr_as,
                        {
                            **ocr_hit,
                            "matched_via": "ocr",
                            "detection_type": "ocr",
                        },
                    )
                    await self._log_activity(
                        "info",
                        "workflow",
                        f"Found {ocr_as} via OCR '{ocr_hit.get('text')}' "
                        f"after {attempt} attempt(s) at ({ocr_hit['x']}, {ocr_hit['y']})",
                        detection=ocr_as,
                        attempts=attempt,
                    )
                    return

            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Timeout waiting for '{target}'"
                    + (f" or OCR {ocr_texts!r}" if ocr_texts else "")
                    + f" after {int(timeout)}s ({attempt} attempts)"
                )

            await asyncio.sleep(poll)

        raise RuntimeError(f"Stopped while waiting for '{target}'")

    async def _handle_failure(self, step: WorkflowStepConfig, exc: Exception) -> None:
        on_failure = step.on_failure
        if on_failure == "retry":
            await asyncio.sleep(self._config.timing.action_retry_delay_seconds)
            await self._execute_step(step)
        elif on_failure in ("escalate", "pause"):
            self._step_failed = True
            self._failure_message = str(exc)
            await self._db.log_error("step_escalated", str(exc), self._device_id, escalated=True)
            await self._device_manager.pause_workflow(self._device_id)
            await self._state_machine.transition(self._device_id, DeviceState.ERROR, str(exc), force=True)
            self._running = False
        elif on_failure == "stop":
            self._running = False

    def _resolve_variables(self, data: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self._substitute(value)
            elif isinstance(value, dict):
                result[key] = self._resolve_variables(value)
            else:
                result[key] = value
        return result

    def _substitute(self, text: str) -> Any:
        def replacer(match: re.Match[str]) -> str:
            key = match.group(1)
            if key in self._variables:
                return str(self._variables[key])
            return match.group(0)
        result = re.sub(r"\$\{(\w+)\}", replacer, text)
        try:
            return int(result)
        except ValueError:
            try:
                return float(result)
            except ValueError:
                return result


class WorkflowEngine:
    """Manage independent workflow runners per device (20-50 device scale)."""

    def __init__(
        self,
        config: AppConfig,
        workflows: dict[str, WorkflowConfig],
        device_manager: DeviceManager,
        screenshot_service: ScreenshotService,
        vision: VisionProvider,
        popup_manager: PopupManager,
        state_machine: StateMachine,
        action_engine: ActionEngine,
        db: DatabaseRepository,
        permission_watchers: PermissionWatcherManager | None = None,
    ) -> None:
        self._config = config
        self._workflows = workflows
        self._device_manager = device_manager
        self._screenshots = screenshot_service
        self._vision = vision
        self._popups = popup_manager
        self._state_machine = state_machine
        self._actions = action_engine
        self._db = db
        self._permission_watchers = permission_watchers
        self._runners: dict[str, WorkflowRunner] = {}
        self._event_callbacks: list[EventCallback] = []

    def on_event(self, callback: EventCallback) -> None:
        self._event_callbacks.append(callback)

    async def _emit(self, event: str, data: dict[str, Any]) -> None:
        for cb in self._event_callbacks:
            try:
                await cb(event, data)
            except Exception as exc:
                logger.error("workflow_event_failed", error=str(exc))

    async def start_workflow(
        self,
        workflow_name: str,
        device_id: str,
        *,
        start_post_index: int | None = None,
    ) -> bool:
        workflow = self._workflows.get(workflow_name)
        if not workflow or not workflow.enabled:
            return False
        key = f"{device_id}:{workflow_name}"
        if key in self._runners and self._runners[key].is_running:
            return False

        post_index = 1
        if start_post_index is not None:
            if workflow_name != "tiktok_post":
                logger.warning(
                    "start_post_index_ignored",
                    workflow=workflow_name,
                    start_post_index=start_post_index,
                )
            elif not (1 <= start_post_index <= POST_COUNT):
                logger.warning(
                    "start_post_index_out_of_range",
                    start_post_index=start_post_index,
                    max_post=POST_COUNT,
                )
                return False
            else:
                post_index = start_post_index

        if self._permission_watchers:
            await self._permission_watchers.acquire(device_id)

        async def _on_runner_finished(dev_id: str) -> None:
            if self._permission_watchers:
                await self._permission_watchers.release(dev_id)

        runner = WorkflowRunner(
            workflow=workflow,
            device_id=device_id,
            config=self._config,
            device_manager=self._device_manager,
            screenshot_service=self._screenshots,
            vision=self._vision,
            popup_manager=self._popups,
            state_machine=self._state_machine,
            action_engine=self._actions,
            db=self._db,
            on_event=self._emit,
            on_finished=_on_runner_finished,
            start_post_index=post_index,
        )
        self._runners[key] = runner
        await runner.start()
        return True

    async def stop_workflow(self, workflow_name: str, device_id: str) -> bool:
        return await self.stop_device(device_id, workflow_name)

    async def stop_device(self, device_id: str, workflow_name: str | None = None) -> bool:
        """Stop a running or paused workflow, including stale state after server restart."""
        stopped = False
        prefix = f"{device_id}:"
        keys_to_remove: list[str] = []
        for key, runner in list(self._runners.items()):
            if not key.startswith(prefix):
                continue
            wf = key[len(prefix):]
            if workflow_name and wf != workflow_name:
                continue
            await runner.stop()
            keys_to_remove.append(key)
            stopped = True
        for key in keys_to_remove:
            self._runners.pop(key, None)

        if stopped and self._permission_watchers:
            await self._permission_watchers.force_stop(device_id)

        device = self._device_manager.get_device(device_id)
        if device:
            should_clear = (
                not workflow_name
                or device.workflow_name in ("", workflow_name)
                or stopped
            )
            if should_clear and (device.workflow_name or device.workflow_paused or stopped):
                await self._device_manager.resume_workflow(device_id)
                await self._device_manager.set_workflow(device_id, "")
                if device.current_state == DeviceState.ERROR:
                    await self._device_manager.set_state(
                        device_id, DeviceState.IDLE, "workflow_stopped"
                    )
                stopped = True
        return stopped

    async def stop_all(self) -> None:
        for runner in list(self._runners.values()):
            await runner.stop()
        self._runners.clear()
        if self._permission_watchers:
            await self._permission_watchers.stop_all()

    async def start_for_group(self, group_name: str) -> int:
        group_config = self._config.device_groups.get(group_name)
        if not group_config:
            return 0
        started = 0
        for device in self._device_manager.devices_in_group(group_name):
            if await self.start_workflow(group_config.workflow, device.device_id):
                started += 1
        return started

    def list_running(self) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for key, runner in self._runners.items():
            if not runner.is_running:
                continue
            sep = key.rfind(":")
            if sep <= 0:
                continue
            result.append({"device_id": key[:sep], "workflow": key[sep + 1:]})
        return result

    def list_workflows(self) -> list[dict[str, Any]]:
        return [
            {"name": w.name, "description": w.description, "enabled": w.enabled,
             "device_groups": w.device_groups, "steps": len(w.steps)}
            for w in self._workflows.values()
        ]
