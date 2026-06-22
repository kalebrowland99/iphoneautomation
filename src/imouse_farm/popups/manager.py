"""PopupManager — detect and handle iOS dialogs and unknown screens."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Awaitable

import yaml

from imouse_farm.config.models import DeviceState
from imouse_farm.utils.logging import get_logger
from imouse_farm.vision.base import VisionAnalysis

logger = get_logger(__name__)

EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class PopupType(str, Enum):
    PERMISSION = "permission_dialog"
    UPDATE = "update_prompt"
    LOGIN = "login_prompt"
    CONFIRMATION = "confirmation_dialog"
    UNKNOWN = "unknown_screen"


@dataclass
class PopupResult:
    """Result of popup detection."""

    popup_type: PopupType | None
    detected: bool
    should_pause: bool = False
    dismiss_action: dict[str, Any] | None = None
    message: str = ""


class PopupManager:
    """Detect common dialogs and handle unknown screens.

    When an unknown screen appears:
    - Save screenshot (caller responsibility)
    - Log event
    - Pause workflow
    - Send notification
    """

    def __init__(self, workflows_dir: str = "config/workflows") -> None:
        path = Path(workflows_dir) / "popups.yaml"
        self._definitions: dict[str, Any] = {}
        if path.exists():
            with path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self._definitions = data.get("popups", {})
        self._event_callbacks: list[EventCallback] = []

    def on_event(self, callback: EventCallback) -> None:
        self._event_callbacks.append(callback)

    async def _emit(self, event: str, data: dict[str, Any]) -> None:
        for cb in self._event_callbacks:
            try:
                await cb(event, data)
            except Exception as exc:
                logger.error("popup_event_failed", error=str(exc))

    def detect(self, analysis: VisionAnalysis) -> PopupResult:
        """Detect popups from vision analysis results."""
        if analysis.popup_type:
            popup_def = self._definitions.get(analysis.popup_type, {})
            return PopupResult(
                popup_type=PopupType(analysis.popup_type)
                if analysis.popup_type in PopupType._value2member_map_
                else PopupType.UNKNOWN,
                detected=True,
                should_pause=popup_def.get("pause_workflow", True),
                dismiss_action=popup_def.get("dismiss_action"),
                message=popup_def.get("description", analysis.popup_type),
            )

        if analysis.detected_state == DeviceState.UNKNOWN_SCREEN:
            return PopupResult(
                popup_type=PopupType.UNKNOWN,
                detected=True,
                should_pause=True,
                message="Unknown screen detected",
            )

        return PopupResult(popup_type=None, detected=False)

    async def handle(
        self,
        device_id: str,
        analysis: VisionAnalysis,
        screenshot_path: str,
        workflow_name: str | None = None,
    ) -> PopupResult:
        """Detect popup and trigger logging / notifications."""
        result = self.detect(analysis)

        if not result.detected:
            return result

        logger.warning(
            "popup_detected",
            device_id=device_id,
            popup_type=result.popup_type.value if result.popup_type else None,
            screenshot=screenshot_path,
            workflow=workflow_name,
        )

        await self._emit("popup_detected", {
            "device_id": device_id,
            "popup_type": result.popup_type.value if result.popup_type else "unknown",
            "screenshot_path": screenshot_path,
            "workflow": workflow_name,
            "should_pause": result.should_pause,
        })

        if result.popup_type == PopupType.UNKNOWN:
            await self._emit("unknown_screen", {
                "device_id": device_id,
                "screenshot_path": screenshot_path,
                "workflow": workflow_name,
            })

        return result
