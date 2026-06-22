"""Screenshot-driven workflow execution engine."""

from __future__ import annotations

import asyncio
import random
import re
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
from imouse_farm.popups.manager import PopupManager
from imouse_farm.screenshots.service import ScreenshotService
from imouse_farm.state.machine import StateMachine
from imouse_farm.utils.gallery import phone_gallery_folder
from imouse_farm.utils.logging import get_logger
from imouse_farm.vision.base import VisionAnalysis, VisionProvider

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
        await self._log_activity(
            "info",
            "workflow",
            f"Started {self._workflow.name}",
        )
        logger.info("workflow_started", workflow=self._workflow.name, device_id=self._device_id)

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
        iteration = 0
        try:
            while self._running:
                if await self._device_manager.is_workflow_paused(self._device_id):
                    await asyncio.sleep(2)
                    continue

                iteration += 1
                if self._workflow.max_iterations > 0 and iteration > self._workflow.max_iterations:
                    break

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

    def _has_detection(self, name: str) -> bool:
        if not self._last_analysis or not name:
            return False
        return any(d.name == name for d in self._last_analysis.detections)

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
        if step.when_detection and not self._has_detection(step.when_detection):
            return f"'{step.when_detection}' not detected"
        if step.unless_detection and self._has_detection(step.unless_detection):
            return f"'{step.unless_detection}' is present"
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
                case "check_popups" | "handle_popups":
                    await self._step_check_popups(step)
                case "execute_action":
                    await self._step_action(step)
                case "verify":
                    await self._step_verify(step)
                case "wait" | "wait_random":
                    await self._step_wait(step)
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

    async def _step_analyze(self, step: WorkflowStepConfig) -> None:
        if not self._last_screenshot:
            path = await self._screenshots.get_latest_path(self._device_id)
            if not path:
                raise RuntimeError("No screenshot available — capture first")
            screenshot_path = path
        else:
            screenshot_path = self._last_screenshot["file_path"]

        self._last_analysis = self._vision.analyze(
            self._device_id,
            screenshot_path,
            template_names=step.templates or None,
            ocr_regions=step.ocr_regions or None,
            ocr_keywords=step.ocr_keywords or None,
        )
        self._has_recent_analysis = True

        detections = {
            d.name: {"x": d.x, "y": d.y, "confidence": d.confidence}
            for d in self._last_analysis.detections
        }
        detections = await self._merge_device_template_detections(
            step.templates or [], detections
        )
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
            det_list = ", ".join(detections.keys()) if detections else "none"
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
        for name in template_names:
            path = self._vision.template_path_for(name)
            if not path:
                continue
            threshold = self._vision.threshold_for(name)
            hit = await controller.find_template_on_device(
                self._device_id, path, threshold
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
        if step.requires_analysis and not self._has_recent_analysis:
            raise RuntimeError(
                f"Action '{step.name}' blocked: screenshot-driven automation requires "
                "analyze step before execute_action"
            )

        action_def = self._resolve_variables(step.action)
        action_type = ActionType(action_def.get("type", "tap_detection"))
        params = {k: v for k, v in action_def.items() if k != "type"}

        if action_type == ActionType.TAP and "x" in params and "y" in params and "detection" not in params:
            logger.warning(
                "blind_tap_warning",
                device_id=self._device_id,
                step=step.name,
                message="Coordinate tap without detection — prefer tap_detection",
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
            return str(self._variables.get(match.group(1), match.group(0)))
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

    async def start_workflow(self, workflow_name: str, device_id: str) -> bool:
        workflow = self._workflows.get(workflow_name)
        if not workflow or not workflow.enabled:
            return False
        key = f"{device_id}:{workflow_name}"
        if key in self._runners and self._runners[key].is_running:
            return False

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

        device = self._device_manager.get_device(device_id)
        if device:
            name_match = not workflow_name or device.workflow_name == workflow_name
            if name_match and (device.workflow_name or device.workflow_paused):
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
