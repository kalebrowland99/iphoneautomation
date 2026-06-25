"""Double iMouse cursor reset before TikTok screen-touch actions."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from imouse_farm.config.models import ActionRequest, ActionType
from imouse_farm.utils.logging import get_logger

if TYPE_CHECKING:
    from imouse_farm.controller.device_controller import DeviceController
    from imouse_farm.devices.manager import DeviceManager

logger = get_logger(__name__)

TIKTOK_WORKFLOWS = frozenset({"tiktok_prep", "tiktok_post", "tiktok_end"})
TOUCH_ACTIONS = frozenset({
    ActionType.TAP,
    ActionType.TAP_DETECTION,
    ActionType.TAP_OCR,
    ActionType.SWIPE,
    ActionType.DRAG,
    ActionType.LONG_PRESS,
    ActionType.TEXT_INPUT,
    ActionType.CLEAR_TEXT,
    ActionType.KEY,
})
PRE_TOUCH_RESET_WAIT_SECONDS = 0.25


def is_tiktok_workflow(workflow_name: str | None) -> bool:
    return bool(workflow_name and workflow_name in TIKTOK_WORKFLOWS)


def needs_pre_touch_reset(
    workflow_name: str | None,
    action_type: ActionType,
) -> bool:
    return is_tiktok_workflow(workflow_name) and action_type in TOUCH_ACTIONS


def resolve_tiktok_workflow(
    device_manager: DeviceManager,
    device_id: str,
    workflow_id: str | None,
) -> str | None:
    if is_tiktok_workflow(workflow_id):
        return workflow_id
    device = device_manager.get_device(device_id)
    if device and is_tiktok_workflow(device.workflow_name):
        return device.workflow_name
    return None


def request_needs_pre_touch_reset(
    device_manager: DeviceManager,
    request: ActionRequest,
) -> bool:
    workflow_name = resolve_tiktok_workflow(
        device_manager, request.device_id, request.workflow_id
    )
    return needs_pre_touch_reset(workflow_name, request.action_type)


async def pre_touch_mouse_reset(
    controller: DeviceController,
    device_id: str,
    *,
    step_name: str | None = None,
) -> None:
    """Reset the iMouse cursor twice to reduce tap offset drift."""
    for index in (1, 2):
        ok = await controller.reset_cursor(device_id)
        if not ok:
            logger.warning(
                "pre_touch_mouse_reset_failed",
                device_id=device_id,
                step=step_name or "",
                attempt=index,
            )
        if index == 1:
            await asyncio.sleep(PRE_TOUCH_RESET_WAIT_SECONDS)
