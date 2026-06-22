"""Tests for state machine."""

import pytest

from imouse_farm.config.models import DeviceState
from imouse_farm.state.machine import VALID_TRANSITIONS


def test_valid_transitions_from_idle() -> None:
    assert DeviceState.ACTIVE in VALID_TRANSITIONS[DeviceState.IDLE]
    assert DeviceState.DISCONNECTED in VALID_TRANSITIONS[DeviceState.IDLE]


def test_disconnected_can_reconnect() -> None:
    assert DeviceState.IDLE in VALID_TRANSITIONS[DeviceState.DISCONNECTED]
