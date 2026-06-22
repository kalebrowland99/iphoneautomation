"""Device state machine with transition tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from imouse_farm.config.models import DeviceState
from imouse_farm.devices.manager import DeviceManager
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

# Valid state transitions
VALID_TRANSITIONS: dict[DeviceState, set[DeviceState]] = {
    DeviceState.DISCONNECTED: {DeviceState.IDLE, DeviceState.ERROR},
    DeviceState.IDLE: {
        DeviceState.ACTIVE,
        DeviceState.WAITING,
        DeviceState.ERROR,
        DeviceState.UNKNOWN_SCREEN,
        DeviceState.DISCONNECTED,
    },
    DeviceState.ACTIVE: {
        DeviceState.IDLE,
        DeviceState.WAITING,
        DeviceState.ERROR,
        DeviceState.UNKNOWN_SCREEN,
        DeviceState.DISCONNECTED,
    },
    DeviceState.WAITING: {
        DeviceState.IDLE,
        DeviceState.ACTIVE,
        DeviceState.ERROR,
        DeviceState.UNKNOWN_SCREEN,
        DeviceState.DISCONNECTED,
    },
    DeviceState.ERROR: {
        DeviceState.IDLE,
        DeviceState.ACTIVE,
        DeviceState.DISCONNECTED,
    },
    DeviceState.UNKNOWN_SCREEN: {
        DeviceState.IDLE,
        DeviceState.ACTIVE,
        DeviceState.WAITING,
        DeviceState.ERROR,
        DeviceState.DISCONNECTED,
    },
}


class StateMachine:
    """Manage per-device state transitions with validation."""

    def __init__(self, device_manager: DeviceManager) -> None:
        self._device_manager = device_manager
        self._last_transition: dict[str, datetime] = {}

    async def transition(
        self,
        device_id: str,
        new_state: DeviceState,
        reason: str = "",
        force: bool = False,
    ) -> bool:
        """Transition device to new state if valid."""
        device = self._device_manager.get_device(device_id)
        if not device:
            logger.warning("state_transition_unknown_device", device_id=device_id)
            return False

        current = device.current_state
        if not force and new_state not in VALID_TRANSITIONS.get(current, set()):
            if new_state != current:
                logger.warning(
                    "invalid_state_transition",
                    device_id=device_id,
                    from_state=current.value,
                    to_state=new_state.value,
                )
                return False

        if current == new_state:
            return True

        await self._device_manager.set_state(device_id, new_state, reason)
        self._last_transition[device_id] = datetime.now(timezone.utc)

        if new_state == DeviceState.UNKNOWN_SCREEN:
            device.unknown_screen_count += 1
        elif new_state in (DeviceState.IDLE, DeviceState.ACTIVE):
            device.unknown_screen_count = 0

        logger.info(
            "state_transition",
            device_id=device_id,
            from_state=current.value,
            to_state=new_state.value,
            reason=reason,
        )
        return True

    def get_last_transition(self, device_id: str) -> datetime | None:
        return self._last_transition.get(device_id)

    def get_state_info(self, device_id: str) -> dict[str, Any] | None:
        device = self._device_manager.get_device(device_id)
        if not device:
            return None
        return {
            "device_id": device_id,
            "current_state": device.current_state.value,
            "last_transition": (
                self._last_transition.get(device_id, datetime.now(timezone.utc)).isoformat()
            ),
            "unknown_screen_count": device.unknown_screen_count,
        }
