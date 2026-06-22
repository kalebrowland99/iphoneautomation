"""Application orchestrator — SDK-based multi-device orchestration platform."""

from __future__ import annotations

import asyncio
from typing import Any

from imouse_farm.actions.engine import ActionEngine
from imouse_farm.config.loader import load_config, load_workflows
from imouse_farm.config.models import AppConfig, DeviceState, WorkflowConfig
from imouse_farm.controller.device_controller import DeviceController
from imouse_farm.dashboard.activity import activity_from_event
from imouse_farm.dashboard.app import app_state, create_app
from imouse_farm.database.repository import DatabaseRepository
from imouse_farm.devices.manager import DeviceManager
from imouse_farm.notifications.service import NotificationService
from imouse_farm.popups.manager import PopupManager
from imouse_farm.screenshots.service import ScreenshotService
from imouse_farm.state.machine import StateMachine
from imouse_farm.utils.logging import get_logger, setup_logging
from imouse_farm.vision.factory import create_vision_provider
from imouse_farm.workflows.engine import WorkflowEngine

logger = get_logger(__name__)


class IMouseFarmApp:
    """Multi-device orchestration platform built on the iMouseXP Python SDK."""

    def __init__(self, config: AppConfig, workflows: dict[str, WorkflowConfig]) -> None:
        self.config = config
        self.workflows = workflows

        self.db = DatabaseRepository(config.database.path)
        self.controller = DeviceController(config.imouse)
        self.device_manager = DeviceManager(config, self.controller, self.db)
        self.screenshot_service = ScreenshotService(
            config, self.controller, self.device_manager, self.db
        )
        self.vision = create_vision_provider(config)
        self.popup_manager = PopupManager(config.workflows_directory)
        self.state_machine = StateMachine(self.device_manager)
        self.action_engine = ActionEngine(
            config, self.controller, self.device_manager, self.db
        )
        self.notification_service = NotificationService(config.notifications)
        self.workflow_engine = WorkflowEngine(
            config,
            workflows,
            self.device_manager,
            self.screenshot_service,
            self.vision,
            self.popup_manager,
            self.state_machine,
            self.action_engine,
            self.db,
        )
        self._frozen_check_task: asyncio.Task[None] | None = None
        self._running = False

    async def _on_event(self, event: str, data: dict[str, Any]) -> None:
        if event != "activity":
            mapped = activity_from_event(event, data)
            if mapped:
                await self.db.log_activity(
                    mapped["level"],
                    mapped["category"],
                    mapped["message"],
                    mapped.get("device_id"),
                    mapped.get("details"),
                )
        await self.notification_service.handle_event(event, data)
        if event != "activity":
            await app_state.broadcast(event, data)

    async def start(self) -> None:
        setup_logging(
            self.config.logging.level,
            self.config.logging.format,
            self.config.logging.file,
        )
        await self.db.connect()

        async def _broadcast_activity(entry: dict[str, Any]) -> None:
            device = self.device_manager.get_device(entry.get("device_id") or "")
            if device:
                entry = dict(entry)
                entry["device_label"] = device.display_label
            await app_state.broadcast("activity", entry)

        self.db.on_activity(_broadcast_activity)

        self.device_manager.on_event(self._on_event)
        self.action_engine.on_event(self._on_event)
        self.workflow_engine.on_event(self._on_event)
        self.popup_manager.on_event(self._on_event)

        await self.device_manager.start()
        await self.screenshot_service.start()
        await self.action_engine.start()

        self._frozen_check_task = asyncio.create_task(self._frozen_check_loop())
        self._running = True
        logger.info("orchestrator_started", vision_provider=self.vision.name)

    async def stop(self) -> None:
        self._running = False
        await self.workflow_engine.stop_all()
        await self.screenshot_service.stop()
        await self.action_engine.stop()
        await self.device_manager.stop()
        await self.controller.disconnect()
        await self.notification_service.close()
        await self.db.close()
        logger.info("orchestrator_stopped")

    async def _frozen_check_loop(self) -> None:
        while self._running:
            for device_id in list(self.device_manager.devices.keys()):
                try:
                    if await self.device_manager.is_frozen(device_id):
                        await self.db.log_error(
                            "frozen_device", f"Device {device_id} appears frozen",
                            device_id, escalated=True,
                        )
                        await self.state_machine.transition(
                            device_id, DeviceState.ERROR, "frozen_detected", force=True
                        )
                        await self._on_event("frozen_device", {"device_id": device_id})
                except Exception as exc:
                    logger.error("frozen_check_error", device_id=device_id, error=str(exc))
            await asyncio.sleep(30)


async def create_application(config_path: str = "config/config.yaml") -> IMouseFarmApp:
    config = load_config(config_path)
    workflows = load_workflows(config.workflows_directory)
    return IMouseFarmApp(config, workflows)
