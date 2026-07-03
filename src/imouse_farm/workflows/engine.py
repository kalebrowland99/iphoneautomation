"""Screenshot-driven workflow execution engine."""

from __future__ import annotations

import asyncio
import random
import re
import time
from pathlib import Path
from typing import Any, Callable, Awaitable

from imouse_farm.actions.engine import ActionEngine
from imouse_farm.actions.pre_touch_reset import is_tiktok_workflow
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
from imouse_farm.workflows.account_switch import ensure_tiktok_account
from imouse_farm.workflows.tiktok_plus_ready import wait_for_tiktok_plus_visible
from imouse_farm.permissions.watcher import PermissionWatcherManager
from imouse_farm.popups.manager import PopupManager
from imouse_farm.screenshots.service import ScreenshotService
from imouse_farm.state.machine import StateMachine
from imouse_farm.captions.ai_generator import stem_to_food_name
from imouse_farm.post.account_profile_store import get_profile_for_device
from imouse_farm.post.post_caption_store import (
    POST_COUNT,
    get_final_caption,
    get_gallery_coords,
    get_onscreen_text,
    post_media_stem,
    text_key_for_device,
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
from imouse_farm.vision.template_scan import pick_detection_hit
from imouse_farm.workflows.vision_recovery import (
    ask_vision_for_recovery,
    execute_recovery_action,
    kill_and_reopen_tiktok,
)

logger = get_logger(__name__)

TIKTOK_TAP_LOCK_ACTIONS = frozenset({
    ActionType.TAP,
    ActionType.TAP_DETECTION,
    ActionType.TAP_OCR,
    ActionType.SWIPE,
    ActionType.DRAG,
})
POPUP_DISMISS_SETTLE_SECONDS = 1.0

EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]

# Sync full-screen OCR dismiss only where dialogs commonly block navigation.
SYNC_POPUP_CLEAR_STEP_NAMES = frozenset({
    "wait_for_plus",  # TikTok home feed before each post
})


def step_needs_sync_popup_clear(
    workflow_name: str | None,
    step: WorkflowStepConfig,
) -> bool:
    """Whether to run a sync permission OCR pass before this workflow step."""
    if not is_tiktok_workflow(workflow_name):
        return False
    return step.name in SYNC_POPUP_CLEAR_STEP_NAMES


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
        permission_watchers: PermissionWatcherManager | None = None,
        brand: str = "labely",
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
        self._permission_watchers = permission_watchers
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
        self._current_step_index = -1
        self._start_post_index = max(1, int(start_post_index))
        self._brand = str(brand or "labely").strip().lower()
        self._tiktok_post_failure_recoveries = 0
        self._tiktok_account_switch_recoveries = 0
        self._iteration_completed_by_recovery = False
        self._captions_auto_generated_posts: set[int] = set()
        self._pending_white_background_after_restart = False

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
                self._tiktok_post_failure_recoveries = 0
                self._tiktok_account_switch_recoveries = 0
                self._iteration_completed_by_recovery = False
                self._captions_auto_generated_posts = set()
                await self._log_activity(
                    "info",
                    "workflow",
                    f"{self._workflow.name} post {iteration}/{self._workflow.max_iterations or iteration}",
                )

                for step_index, step in enumerate(self._workflow.steps):
                    if not self._running:
                        break
                    if await self._device_manager.is_workflow_paused(self._device_id):
                        break
                    if self._iteration_completed_by_recovery:
                        break
                    self._current_step_index = step_index
                    await self._execute_step(step)
                    if self._iteration_completed_by_recovery:
                        break

                if self._workflow.name == "tiktok_post" and not self._step_failed:
                    from imouse_farm.post.account_profile_store import mark_post_completed

                    mark_post_completed(self._post_text_key(), iteration, brand=self._brand)

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
            brand=self._brand,
        )
        self._variables["phone_name"] = device.phone_name
        self._variables["device_slot"] = device.user_name
        self._variables["gallery_folder"] = str(folder)
        profile = get_profile_for_device(device.device_id, device.user_name, brand=self._brand)
        self._variables["tiktok_account"] = profile.get("tiktok_handle", "")
        self._variables["brand"] = self._brand
        logger.info(
            "workflow_variables",
            device_id=self._device_id,
            slot=device.user_name,
            phone=device.phone_name,
            gallery_folder=str(folder),
            tiktok_account=self._variables.get("tiktok_account"),
        )

    def _post_text_key(self) -> str:
        device = self._device_manager.get_device(self._device_id)
        if device:
            return text_key_for_device(
                device.device_id,
                device.user_name,
                brand=self._brand,
            )
        return text_key_for_device(self._device_id, brand=self._brand)

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
                brand=self._brand,
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

    async def _ensure_post_captions(self, post_index: int) -> None:
        """Regenerate onscreen + final captions from gallery before typing."""
        if self._workflow.name != "tiktok_post":
            return
        if not self._config.openai.enabled or not self._config.slideshow.auto_generate_captions:
            return
        if post_index in self._captions_auto_generated_posts:
            return

        text_key = self._post_text_key()
        device = self._device_manager.get_device(self._device_id)
        if not device:
            raise RuntimeError("Device not found for caption auto-generation")

        from imouse_farm.captions.service import (
            default_onscreen_template_for_brand,
            generate_captions_for_device,
        )

        template = default_onscreen_template_for_brand(
            self._brand,
            self._config.slideshow.default_onscreen_template,
        )
        await self._log_activity(
            "info",
            "workflow",
            f"Post {post_index}: generating captions from gallery before typing",
            brand=self._brand,
        )
        await generate_captions_for_device(
            self._config,
            device,
            onscreen_template=template,
            brand=self._brand,
        )
        self._captions_auto_generated_posts.add(post_index)
        self._refresh_post_variables(post_index)

        onscreen = get_onscreen_text(text_key, post_index, brand=self._brand).strip()
        final = get_final_caption(text_key, post_index, brand=self._brand).strip()
        if not onscreen:
            raise RuntimeError(
                f"Post {post_index}: onscreen text empty after auto-generation "
                f"(check gallery files and OpenAI settings)"
            )
        if not final:
            raise RuntimeError(
                f"Post {post_index}: final caption empty after auto-generation "
                f"(check gallery files and OpenAI settings)"
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
        rect: list[int] | None = None,
        is_ex: bool = False,
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
                rect=rect,
                is_ex=is_ex,
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

    async def _sample_best_detection(
        self,
        step: WorkflowStepConfig,
        target: str,
        templates: list[str],
        action_cfg: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Capture several frames per poll and keep the strongest template/OCR hit."""
        from imouse_farm.vision.template_scan import (
            ocr_rect_from_pct,
            pick_detection_hit,
            stronger_hit,
        )

        samples = max(1, int(action_cfg.get("samples_per_poll", 1)))
        sample_interval = float(action_cfg.get("sample_interval_seconds", 0.4))
        ocr_texts = [
            str(t).strip()
            for t in (action_cfg.get("ocr_fallback_texts") or [])
            if str(t).strip()
        ]
        ocr_threshold = float(action_cfg.get("ocr_threshold", 0.5))
        ocr_prefer_top = bool(action_cfg.get("prefer_top", True))
        ocr_ex = bool(action_cfg.get("ocr_ex", False))
        raw_rect = action_cfg.get("ocr_search_rect_pct")
        device = self._device_manager.get_device(self._device_id)
        ocr_rect: list[int] | None = None
        if isinstance(raw_rect, list) and len(raw_rect) == 4 and device:
            ocr_rect = ocr_rect_from_pct(
                device.screen_width, device.screen_height, raw_rect
            )

        best_hit: dict[str, Any] | None = None
        for sample_idx in range(samples):
            capture_step = WorkflowStepConfig(
                type="screenshot",
                name=f"{step.name}_capture_{sample_idx}",
                templates=templates,
            )
            analyze_step = WorkflowStepConfig(
                type="analyze_screen",
                name=f"{step.name}_analyze_{sample_idx}",
                templates=templates,
            )
            await self._step_capture(capture_step)
            await self._step_analyze(analyze_step)

            template_hit = pick_detection_hit(self._current_detections(), target)
            if template_hit:
                template_hit = dict(template_hit)
                template_hit.setdefault("detection_type", "template")
                best_hit = stronger_hit(best_hit, template_hit)

            if ocr_texts:
                ocr_hit = await self._device_ocr_best_hit(
                    ocr_texts,
                    threshold=ocr_threshold,
                    prefer_bottom=not ocr_prefer_top,
                    rect=ocr_rect,
                    is_ex=ocr_ex,
                )
                if ocr_hit:
                    ocr_entry = {
                        "x": int(ocr_hit["x"]),
                        "y": int(ocr_hit["y"]),
                        "confidence": float(ocr_hit.get("confidence", 0.85)),
                        "matched_via": "ocr",
                        "detection_type": "ocr",
                        "text": ocr_hit.get("text"),
                    }
                    best_hit = stronger_hit(best_hit, ocr_entry)

            if sample_idx < samples - 1:
                await asyncio.sleep(sample_interval)

        if best_hit:
            self._set_detection(target, best_hit)
        return best_hit

    async def _log_activity(
        self,
        level: str,
        category: str,
        message: str,
        *args: Any,
        **details: Any,
    ) -> None:
        # Shared helpers (account_switch, tiktok_plus_ready, vision_recovery, warmup)
        # sometimes pass device_id as a 4th positional when wired to db.log_activity.
        if args:
            extra = args[0]
            if isinstance(extra, str) and extra.strip() and "device_id" not in details:
                details = {**details, "passed_device_id": extra.strip()}
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
            if step.name in ("tap_white_background", "after_white_background"):
                if current == step.when_post_index or self._pending_white_background_after_restart:
                    pass
                else:
                    return (
                        f"post {current}, white background only for post "
                        f"{step.when_post_index} or after TikTok restart"
                    )
            elif current != step.when_post_index:
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

        if step_needs_sync_popup_clear(self._workflow.name, step):
            await self._ensure_popups_cleared(step.name)

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
            await self._execute_step_body(step)
            if (
                step.name == "tap_white_background"
                and self._pending_white_background_after_restart
            ):
                self._pending_white_background_after_restart = False
                await self._log_activity(
                    "info",
                    "workflow",
                    "White background tap done after TikTok restart",
                    step=step.name,
                )
            # Post-step screen validation: if screen_check is set, verify the
            # expected element is present before proceeding to the next step.
            if step.screen_check:
                await self._verify_screen_check(step)
        except Exception as exc:
            logger.error("step_failed", step=step.name, device_id=self._device_id, error=str(exc))
            await self._log_activity(
                "error",
                "workflow",
                f"Step failed: {step.name} — {exc}",
                step_type=step.type,
            )
            if await self._try_recover_tiktok_post(step, exc):
                return
            account_recovery = await self._try_recover_tiktok_account_switch(step, exc)
            if account_recovery is True:
                return
            if account_recovery is None:
                failure_exc = getattr(self, "_pending_failure_exc", None) or exc
                await self._handle_failure(step, failure_exc)
                return
            # Ask OpenAI Vision what to do to recover, then apply normal failure policy.
            await self._vision_recover(step, exc)
            await self._handle_failure(step, exc)

    async def _execute_step_body(self, step: WorkflowStepConfig) -> None:
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
            case "ensure_tiktok_account":
                await self._step_ensure_tiktok_account(step)
            case _:
                logger.warning("unknown_step_type", step_type=step.type, name=step.name)

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

    async def _device_template_confidence(self, template_name: str) -> float:
        detections = await self._merge_device_template_detections(
            [template_name], {}
        )
        hit = detections.get(template_name)
        if not hit:
            return 0.0
        return float(hit.get("confidence", 0))

    async def _template_fallback_state(
        self,
        fallback_entries: list[dict[str, Any]],
        *,
        prefer_state: str,
    ) -> tuple[str | None, float]:
        """On-device template match for VPN toggle state during OCR polling."""
        entries = [
            entry
            for entry in fallback_entries
            if str(entry.get("state") or "").strip() == prefer_state
        ]
        if not entries:
            return None, 0.0
        template_names = [
            str(entry.get("template") or "").strip()
            for entry in entries
            if str(entry.get("template") or "").strip()
        ]
        if not template_names:
            return None, 0.0
        detections = await self._merge_device_template_detections(template_names, {})
        return resolve_template_state_fallback(detections, entries)

    async def _tap_detection_inline(self, detection: str) -> None:
        await self._step_action(
            WorkflowStepConfig(
                type="execute_action",
                name=f"_inline_tap_{detection}",
                action={
                    "type": "tap_detection",
                    "detection": detection,
                    "refind_on_device": True,
                },
                skip_post_action=True,
            )
        )

    def _step_index_by_name(self, name: str) -> int:
        for index, step in enumerate(self._workflow.steps):
            if step.name == name:
                return index
        raise RuntimeError(f"Step {name!r} not found in workflow {self._workflow.name}")

    def _max_tiktok_post_failure_recoveries(self) -> int:
        for step in self._workflow.steps:
            if step.name == "wait_for_plus":
                action = step.action or {}
                return int(
                    action.get("max_failure_recoveries")
                    or action.get("max_app_restarts")
                    or 5
                )
        return 5

    async def _try_recover_tiktok_post(
        self,
        step: WorkflowStepConfig,
        exc: Exception,
    ) -> bool:
        """Restart TikTok and resume from wait_for_plus after a failed post step."""
        if self._workflow.name != "tiktok_post":
            return False
        if step.on_failure not in ("pause", "escalate"):
            return False

        max_recoveries = self._max_tiktok_post_failure_recoveries()
        if self._tiktok_post_failure_recoveries >= max_recoveries:
            await self._log_activity(
                "error",
                "workflow",
                f"TikTok recovery exhausted ({max_recoveries}) after {step.name}: {exc}",
                step=step.name,
            )
            return False

        self._tiktok_post_failure_recoveries += 1
        await self._log_activity(
            "warn",
            "workflow",
            (
                f"Step failed ({step.name}) — closing and reopening TikTok, "
                f"then resuming from + button "
                f"({self._tiktok_post_failure_recoveries}/{max_recoveries})"
            ),
            step=step.name,
            error=str(exc),
        )

        try:
            await self._restart_tiktok(parent_step=step.name)
        except Exception as restart_exc:
            await self._log_activity(
                "error",
                "workflow",
                f"TikTok restart failed during recovery: {restart_exc}",
                step=step.name,
            )
            try:
                await self._reset_phone_recast_and_open_tiktok(parent_step=step.name)
            except Exception as reset_exc:
                await self._log_activity(
                    "error",
                    "workflow",
                    f"Phone reset/recast failed during recovery: {reset_exc}",
                    step=step.name,
                )
                return False
            return await self._resume_tiktok_post_from_plus()

        if await self._resume_tiktok_post_from_plus():
            return True

        await self._log_activity(
            "warn",
            "workflow",
            "TikTok restart did not recover — resetting phone and recasting",
            step=step.name,
        )
        try:
            await self._reset_phone_recast_and_open_tiktok(parent_step=step.name)
        except Exception as reset_exc:
            await self._log_activity(
                "error",
                "workflow",
                f"Phone reset/recast failed after TikTok restart: {reset_exc}",
                step=step.name,
            )
            return False
        return await self._resume_tiktok_post_from_plus()

    async def _try_recover_tiktok_account_switch(
        self,
        step: WorkflowStepConfig,
        exc: Exception,
    ) -> bool | None:
        """Reopen TikTok via vision recovery and retry ensure_tiktok_account up to 3 times.

        Returns True if a retry succeeded, None if all recoveries failed,
        False if this path does not apply.
        """
        if step.type != "ensure_tiktok_account":
            return False
        if step.on_failure not in ("pause", "escalate"):
            return False

        max_recoveries = 3
        if self._tiktok_account_switch_recoveries >= max_recoveries:
            return False

        last_exc: Exception = exc
        while self._tiktok_account_switch_recoveries < max_recoveries:
            self._tiktok_account_switch_recoveries += 1
            await self._log_activity(
                "warn",
                "workflow",
                (
                    f"Account switch failed ({last_exc}) — reopening TikTok and retrying "
                    f"({self._tiktok_account_switch_recoveries}/{max_recoveries})"
                ),
                step=step.name,
            )

            await self._vision_recover(step, last_exc)
            await asyncio.sleep(self._config.timing.action_retry_delay_seconds)

            self._step_failed = False
            self._failure_message = ""
            try:
                await self._execute_step_body(step)
                if step.screen_check:
                    await self._verify_screen_check(step)
                await self._log_activity(
                    "info",
                    "workflow",
                    "Account switch succeeded after TikTok reopen",
                    step=step.name,
                )
                return True
            except Exception as retry_exc:
                last_exc = retry_exc
                logger.error(
                    "account_switch_retry_failed",
                    step=step.name,
                    device_id=self._device_id,
                    attempt=self._tiktok_account_switch_recoveries,
                    max_recoveries=max_recoveries,
                    error=str(retry_exc),
                )
                if self._tiktok_account_switch_recoveries >= max_recoveries:
                    await self._log_activity(
                        "error",
                        "workflow",
                        f"Account switch retry failed: {retry_exc}",
                        step=step.name,
                    )
                    self._pending_failure_exc = retry_exc
                    return None
                await self._log_activity(
                    "warn",
                    "workflow",
                    f"Account switch retry failed: {retry_exc} — reopening TikTok again",
                    step=step.name,
                )

        return None

    async def _resume_tiktok_post_from_plus(self) -> bool:
        """Re-run from wait_for_plus through end of current post iteration."""
        self._step_failed = False
        self._failure_message = ""
        plus_idx = self._step_index_by_name("wait_for_plus")
        for index in range(plus_idx, len(self._workflow.steps)):
            if not self._running:
                return False
            if await self._device_manager.is_workflow_paused(self._device_id):
                return False
            recovery_step = self._workflow.steps[index]
            self._current_step_index = index
            await self._execute_step(recovery_step)
            if self._iteration_completed_by_recovery:
                return True
            if self._step_failed:
                return False

        self._iteration_completed_by_recovery = True
        return True

    async def _open_tiktok_from_home(self, *, parent_step: str) -> None:
        """Open TikTok from the home screen via configured icon coordinates."""
        nav = self._config.tiktok_navigation
        x = nav.tiktok_home_icon_x
        y = nav.tiktok_home_icon_y
        await self._log_activity(
            "info",
            "workflow",
            f"Opening TikTok from home at ({x}, {y})",
            step=parent_step,
        )
        ok = await self._device_manager.controller.tap(self._device_id, x, y)
        if not ok:
            raise RuntimeError(f"TikTok icon tap failed at ({x}, {y})")
        await wait_for_tiktok_plus_visible(
            self._device_manager.controller,
            self._device_id,
            device_manager=self._device_manager,
            vision=self._vision,
            templates_directory=self._config.analysis.templates_directory,
            log_activity=lambda level, category, message, *args, **details: self._log_activity(
                level, category, message, *args, step=parent_step, **details
            ),
        )

    async def _reset_phone_recast_and_open_tiktok(self, *, parent_step: str) -> None:
        """Reboot phone, reconnect AirPlay, reopen TikTok, resume from +."""
        await self._log_activity(
            "warn",
            "workflow",
            "Resetting phone, reconnecting cast, and reopening TikTok",
            step=parent_step,
        )
        await self._device_manager.reset_phone_and_recast(self._device_id)
        await self._open_tiktok_from_home(parent_step=f"{parent_step}_phone_reset")
        self._pending_white_background_after_restart = True
        await self._log_activity(
            "info",
            "workflow",
            "Phone reset complete — resuming from + button",
            step=parent_step,
        )

    async def _restart_tiktok(self, *, parent_step: str) -> None:
        """Force-quit TikTok (app switcher + swipe up ×5) and reopen from home."""
        wf = self._workflow.name
        step_name = f"{parent_step}_restart_tiktok"
        await self._log_activity(
            "warn",
            "workflow",
            "Closing and reopening TikTok (home → app switcher → swipe up ×5)",
            step=parent_step,
        )

        for action_type, wait_s in (
            (ActionType.HOME, 3.0),
            (ActionType.KILL_APP, 3.0),
            (ActionType.HOME, 3.0),
        ):
            ok = await self._execute_direct(
                action_type,
                {},
                step_name=step_name,
            )
            if not ok:
                raise RuntimeError(f"TikTok restart failed at {action_type.value}")
            await asyncio.sleep(wait_s)

        await self._open_tiktok_from_home(parent_step=parent_step)
        self._pending_white_background_after_restart = True
        await self._log_activity(
            "info",
            "workflow",
            "Next post will run white-background tap (TikTok was restarted)",
            step=parent_step,
        )

    async def _step_check_ocr_state(self, step: WorkflowStepConfig) -> None:
        """Set device state from on-device OCR, with optional template fallback."""
        action = self._resolve_variables(step.action)
        mode = str(action.get("mode") or "").strip()
        if mode == "template_connected":
            await self._step_check_template_connected(step, action)
            return

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
        reconnect_cast = bool(action.get("reconnect_cast_during_poll"))
        focus_app_after_reconnect = str(
            action.get("focus_app_after_reconnect") or ""
        ).strip()

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

        deadline = time.monotonic() + timeout
        matched_text = ""
        found = False
        template_override: str | None = None
        while self._running:
            if reconnect_cast:
                await self._device_manager.refresh_devices()
                device = self._device_manager.get_device(self._device_id)
                if device is not None and not device.is_online:
                    logger.info(
                        "ocr_state_reconnect_cast",
                        device_id=self._device_id,
                        step=step.name,
                    )
                    await self._device_manager.reconnect_airplay(self._device_id)
                    await asyncio.sleep(2.0)
                    await self._device_manager.refresh_devices()
                    if focus_app_after_reconnect:
                        await self._log_activity(
                            "info",
                            "workflow",
                            f"Re-open app after cast reconnect ({focus_app_after_reconnect})",
                            step=step.name,
                        )
                        await self._tap_detection_inline(focus_app_after_reconnect)
                        await asyncio.sleep(2.0)
            if fallback_entries:
                winner, conf = await self._template_fallback_state(
                    fallback_entries,
                    prefer_state=state_if_missing.value,
                )
                if winner:
                    found = False
                    matched_text = ""
                    template_override = f"{winner} visible (conf={conf:.2f})"
                    break
            found, matched_text = await self._device_ocr_has_text(
                texts, threshold=threshold
            )
            if found and fallback_entries:
                winner, conf = await self._template_fallback_state(
                    fallback_entries,
                    prefer_state=state_if_missing.value,
                )
                if winner:
                    found = False
                    matched_text = ""
                    template_override = f"{winner} visible (conf={conf:.2f})"
                    break
            if not found:
                break
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(retry_delay)

        if found:
            state = state_if_found
            reason = f"found '{matched_text}'"
        else:
            state = state_if_missing
            reason = template_override or f"'{texts[0]}' not found"
            if fallback_entries and state == state_if_missing and not template_override:
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

    async def _step_check_template_connected(
        self,
        step: WorkflowStepConfig,
        action: dict[str, Any],
    ) -> None:
        """Confirm VPN is on via toggle templates, not OCR status text."""
        active_template = str(action.get("active_template") or "bluetoggle").strip()
        inactive_template = str(action.get("inactive_template") or "vpntoggle").strip()
        min_confidence = float(action.get("min_confidence", 0.45))
        inactive_max_confidence = float(action.get("inactive_max_confidence", 0.42))
        retry_delay = float(action.get("retry_delay", 2.0))
        timeout = float(action.get("duration_seconds", 45))
        reconnect_cast = bool(action.get("reconnect_cast_during_poll"))
        focus_app_after_reconnect = str(
            action.get("focus_app_after_reconnect") or ""
        ).strip()
        require_state = action.get("require_state")
        required = DeviceState(require_state) if require_state else None

        deadline = time.monotonic() + timeout
        reason = f"{active_template} not visible after {int(timeout)}s"
        state = DeviceState.WAITING

        while self._running:
            if reconnect_cast:
                await self._device_manager.refresh_devices()
                device = self._device_manager.get_device(self._device_id)
                if device is not None and not device.is_online:
                    logger.info(
                        "template_connected_reconnect_cast",
                        device_id=self._device_id,
                        step=step.name,
                    )
                    await self._device_manager.reconnect_airplay(self._device_id)
                    await asyncio.sleep(2.0)
                    await self._device_manager.refresh_devices()
                    if focus_app_after_reconnect:
                        await self._log_activity(
                            "info",
                            "workflow",
                            f"Re-open app after cast reconnect ({focus_app_after_reconnect})",
                            step=step.name,
                        )
                        await self._tap_detection_inline(focus_app_after_reconnect)
                        await asyncio.sleep(2.0)

            active_conf = await self._device_template_confidence(active_template)
            if active_conf >= min_confidence:
                state = DeviceState.ACTIVE
                reason = f"{active_template} visible (conf={active_conf:.2f})"
                break

            inactive_conf = await self._device_template_confidence(inactive_template)
            if inactive_conf < inactive_max_confidence:
                state = DeviceState.ACTIVE
                reason = (
                    f"{inactive_template} gone after toggle "
                    f"(conf={inactive_conf:.2f})"
                )
                break

            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(retry_delay)

        await self._state_machine.transition(
            self._device_id, state, reason=f"workflow:{step.name}", force=True
        )
        await self._log_activity(
            "info",
            "workflow",
            f"VPN status → {state.value} ({reason})",
            step=step.name,
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
            await self._execute_direct(
                action_type,
                params,
                step_name=f"dismiss_{step.name}",
            )
            await self._step_capture(WorkflowStepConfig(type="screenshot", name="_post_dismiss"))
            await self._step_analyze(WorkflowStepConfig(type="analyze", name="_post_dismiss_analyze"))

    async def _step_action(self, step: WorkflowStepConfig) -> None:
        if step.name in ("tap_gallery_item", "type_onscreen_text", "type_final_post_caption"):
            post_index = int(self._variables.get("post_index", 0))
            if post_index >= 1:
                self._refresh_post_variables(post_index)
                if step.name in ("type_onscreen_text", "type_final_post_caption"):
                    await self._ensure_post_captions(post_index)
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

        if step.name == "tap_gallery":
            params["tap_count"] = max(2, int(params.get("tap_count", 2)))
            params.setdefault("tap_interval_seconds", 0.5)
        elif step.name == "tap_plus":
            params["tap_count"] = max(2, int(params.get("tap_count", 2)))
            params.setdefault("tap_interval_seconds", 0.5)
        elif step.name == "tap_favorites":
            params["tap_count"] = max(2, int(params.get("tap_count", 2)))
            params.setdefault("tap_interval_seconds", 0.5)
        elif step.name == "tap_aa":
            params["tap_count"] = 1
        elif step.name == "wait_for_recents":
            fallback = params.get("fallback_tap")
            if isinstance(fallback, dict):
                fallback["tap_count"] = max(2, int(fallback.get("tap_count", 2)))
                fallback.setdefault("tap_interval_seconds", 0.5)
        elif step.name == "swipe_left":
            params["swipe_count"] = max(2, int(params.get("swipe_count", 2)))
            params.setdefault("swipe_interval_seconds", 1.5)

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

        success = await self._execute_direct(
            action_type,
            params,
            step_name=step.name,
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

    async def _step_ensure_tiktok_account(self, step: WorkflowStepConfig) -> None:
        handle = str(self._variables.get("tiktok_account") or "").strip()
        if not handle:
            await self._log_activity(
                "info",
                "workflow",
                "Account switch skipped — set @ handle on dashboard for this slot",
                step=step.name,
            )
            return

        async def _log(level: str, category: str, message: str, *args: Any, **details: Any) -> None:
            await self._log_activity(level, category, message, *args, step=step.name, **details)

        async def _clear_popups(context: str) -> bool:
            return (await self._ensure_popups_cleared(context)) > 0

        await ensure_tiktok_account(
            controller=self._device_manager.controller,
            device_id=self._device_id,
            tiktok_handle=handle,
            navigation=self._config.tiktok_navigation,
            log_activity=_log,
            device_manager=self._device_manager,
            templates_dir=self._config.analysis.templates_directory,
            vision=self._vision,
            brand=self._brand,
            clear_popups=_clear_popups,
        )

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

    async def _try_dismiss_popups(self, context: str) -> bool:
        if not self._permission_watchers or not is_tiktok_workflow(self._workflow.name):
            return False
        dismissed = await self._permission_watchers.try_dismiss(self._device_id)
        if dismissed:
            await self._log_activity(
                "info",
                "workflow",
                f"Dismissed TikTok/iOS popup during {context}",
            )
            await asyncio.sleep(POPUP_DISMISS_SETTLE_SECONDS)
        return dismissed

    async def _ensure_popups_cleared(
        self,
        context: str,
        *,
        max_passes: int = 5,
    ) -> int:
        """Run the permission watcher until no popup is visible (TikTok only)."""
        cleared = 0
        for _ in range(max(1, max_passes)):
            if not await self._try_dismiss_popups(context):
                break
            cleared += 1
        if cleared >= max_passes:
            await self._log_activity(
                "warn",
                "workflow",
                f"Popup watcher still active after {max_passes} dismiss passes ({context})",
            )
        return cleared

    async def _execute_direct(
        self,
        action_type: ActionType,
        params: dict[str, Any],
        *,
        step_name: str,
    ) -> bool:
        """Execute a device action (popup clear runs once at workflow step entry)."""
        if action_type in TIKTOK_TAP_LOCK_ACTIONS:
            tap_lock = self._device_manager.get_tap_lock(self._device_id)
            async with tap_lock:
                return await self._actions.execute_direct(
                    self._device_id,
                    action_type,
                    params,
                    workflow_id=self._workflow.name,
                    step_name=step_name,
                )
        return await self._actions.execute_direct(
            self._device_id,
            action_type,
            params,
            workflow_id=self._workflow.name,
            step_name=step_name,
        )

    async def _sleep_with_popup_watch(self, seconds: float, context: str) -> None:
        if seconds <= 0:
            return
        await asyncio.sleep(seconds)

    async def _step_wait(self, step: WorkflowStepConfig) -> None:
        if step.type == "wait_random" or (step.min_seconds and step.max_seconds):
            duration = random.uniform(
                step.min_seconds or 1.0,
                step.max_seconds or step.min_seconds or 3.0,
            )
        else:
            duration = step.duration_seconds or 1.0
        if step.name and not step.name.startswith("_") and duration >= 1.0:
            await self._log_activity(
                "info",
                "workflow",
                f"Waiting {duration:g}s — {step.name}",
            )
        await self._sleep_with_popup_watch(duration, step.name or "wait")

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
        samples_per_poll = max(1, int(action_cfg.get("samples_per_poll", 1)))
        deadline = time.monotonic() + timeout
        attempt = 0
        restart_after = max(0, int(action_cfg.get("restart_app_after_attempts") or 0))
        max_restarts = max(1, int(action_cfg.get("max_app_restarts") or 5))
        attempts_since_restart = 0
        restart_count = 0
        phone_reset_used = False
        tiktok_restart_enabled = restart_after > 0 and is_tiktok_workflow(self._workflow.name)

        await self._log_activity(
            "info",
            "workflow",
            f"Waiting for {target}"
            + (f" or OCR {ocr_texts!r}" if ocr_texts else "")
            + f" (up to {int(timeout)}s"
            + (f", {samples_per_poll} captures/poll" if samples_per_poll > 1 else "")
            + ")",
            detection=target,
        )

        while self._running:
            if await self._device_manager.is_workflow_paused(self._device_id):
                await asyncio.sleep(2)
                continue

            attempt += 1
            if samples_per_poll > 1 or action_cfg.get("ocr_fallback_texts"):
                hit = await self._sample_best_detection(
                    step, target, templates, action_cfg
                )
            else:
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
                hit = None

            if self._has_detection(target) or hit:
                hit_dict = hit or pick_detection_hit(
                    apply_detection_fallbacks(self._current_detections()), target
                )
                conf = f"{float(hit_dict.get('confidence', 0)):.2f}" if hit_dict else "?"
                via = hit_dict.get("matched_via") if hit_dict else None
                await self._log_activity(
                    "info",
                    "workflow",
                    f"Found {target} after {attempt} attempt(s) (conf={conf}"
                    + (f", via={via})" if via else ")"),
                    detection=target,
                    attempts=attempt,
                    confidence=float(hit_dict.get("confidence", 0)) if hit_dict else None,
                )
                return

            if tiktok_restart_enabled:
                attempts_since_restart += 1
                if attempts_since_restart >= restart_after and restart_count < max_restarts:
                    await self._restart_tiktok(parent_step=step.name or target)
                    restart_count += 1
                    attempts_since_restart = 0
                    await self._log_activity(
                        "info",
                        "workflow",
                        f"TikTok reopened ({restart_count}/{max_restarts}) — waiting for {target} again",
                        step=step.name,
                        detection=target,
                    )
                elif (
                    not phone_reset_used
                    and restart_count >= max_restarts
                    and is_tiktok_workflow(self._workflow.name)
                ):
                    phone_reset_used = True
                    await self._log_activity(
                        "warn",
                        "workflow",
                        f"TikTok restarts exhausted — resetting phone and recasting",
                        step=step.name,
                        detection=target,
                    )
                    await self._reset_phone_recast_and_open_tiktok(
                        parent_step=step.name or target
                    )
                    restart_count = 0
                    attempts_since_restart = 0
                    await self._log_activity(
                        "info",
                        "workflow",
                        f"Phone reset complete — waiting for {target} again",
                        step=step.name,
                        detection=target,
                    )

            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Timeout waiting for '{target}'"
                    + (f" or OCR {ocr_texts!r}" if ocr_texts else "")
                    + f" after {int(timeout)}s ({attempt} attempts)"
                )

            await asyncio.sleep(poll)

        raise RuntimeError(f"Stopped while waiting for '{target}'")

    def _vision_recovery_should_reopen_tiktok(self, step: WorkflowStepConfig) -> bool:
        """Prep/end home/kill/album failures should not kill-reopen TikTok."""
        workflow = self._workflow.name or ""
        if workflow in ("tiktok_prep", "tiktok_valcoin_prep"):
            return (step.name or "") in ("open_tiktok", "wait_for_tiktok_icon")
        if workflow == "tiktok_end":
            return False
        return True

    async def _vision_recover(self, step: WorkflowStepConfig, exc: Exception) -> None:
        """On step failure: check for a blocking popup via OpenAI Vision.

        - If a popup is found → tap to dismiss it.
        - If no popup → kill TikTok and reopen it so the workflow can retry.
        Best-effort: logs and continues to normal on_failure handler on any error.
        """
        from imouse_farm.workflows.vision_recovery import kill_and_reopen_tiktok

        try:
            controller = self._actions._controller  # noqa: SLF001
            result = await ask_vision_for_recovery(
                controller,
                self._device_id,
                step_name=step.name,
                workflow_name=self._workflow.name,
                error_msg=str(exc),
                app_config=self._config,
            )
            if result.get("popup"):
                # Dismiss the blocking popup.
                await execute_recovery_action(
                    controller,
                    self._device_id,
                    result,
                    log_activity=self._log_activity,
                )
            else:
                if self._vision_recovery_should_reopen_tiktok(step):
                    await kill_and_reopen_tiktok(
                        controller,
                        self._device_id,
                        self._config,
                        log_activity=self._log_activity,
                    )
                else:
                    await self._log_activity(
                        "info",
                        "workflow",
                        "Vision recovery: no popup — skipping TikTok reopen for this step",
                        step=step.name,
                    )
        except Exception as recovery_exc:
            logger.warning(
                "vision_recovery_skipped",
                device_id=self._device_id,
                step=step.name,
                error=str(recovery_exc),
            )
            await self._log_activity(
                "warn",
                "workflow",
                f"Vision recovery skipped: {type(recovery_exc).__name__}: {recovery_exc}",
            )

    async def _verify_screen_check(self, step: WorkflowStepConfig) -> None:
        """After a step succeeds, verify screen_check element is present.

        If the expected element is not found, ask OpenAI Vision to recover.
        The step is not re-run — we just attempt to fix the screen state and
        continue. Detections can be a template stem or a short OCR keyword.
        """
        check = step.screen_check
        if not check:
            return

        found = False
        try:
            from pathlib import Path
            controller = self._actions._controller  # noqa: SLF001
            templates_dir = self._config.analysis.templates_directory
            template_path = Path(templates_dir) / f"{check}.jpg"
            if template_path.is_file():
                # Template match — one screenshot + local OpenCV (~0.5–1.5s).
                hit = await controller.find_template_on_device(
                    self._device_id, template_path, threshold=0.5
                )
                found = bool(hit)
            else:
                # OCR keyword — SDK handles screenshot+OCR internally (~1–2s).
                ocr = await controller.ocr_on_device(self._device_id)
                found = bool(ocr and check.lower() in ocr.lower())
        except Exception as exc:
            logger.warning(
                "screen_check_error",
                device_id=self._device_id,
                step=step.name,
                check=check,
                error=str(exc),
            )
            return

        if found:
            await self._log_activity(
                "debug",
                "workflow",
                f"Screen check OK — {check} detected after {step.name}",
            )
        else:
            await self._log_activity(
                "info",
                "workflow",
                f"Screen check FAILED — expected '{check}' after {step.name}, asking vision recovery",
            )
            await self._vision_recover(
                step,
                RuntimeError(f"screen_check: '{check}' not found after step '{step.name}'"),
            )

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
        brand: str = "labely",
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

        from imouse_farm.actions.cancel import clear_cancelled

        clear_cancelled(device_id)

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
            permission_watchers=self._permission_watchers,
            brand=brand,
        )
        self._runners[key] = runner
        await runner.start()
        return True

    async def stop_workflow(self, workflow_name: str, device_id: str) -> bool:
        return await self.stop_device(device_id, workflow_name)

    async def stop_device(self, device_id: str, workflow_name: str | None = None) -> bool:
        """Stop a running or paused workflow, including stale state after server restart."""
        await self._actions.abort_device(device_id)

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

        if self._permission_watchers:
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
