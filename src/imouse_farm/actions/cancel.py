"""Cooperative cancellation for in-flight device actions (dashboard Kill / Stop)."""

from __future__ import annotations

_cancelled_devices: set[str] = set()


def mark_cancelled(device_id: str) -> None:
    _cancelled_devices.add(device_id)


def clear_cancelled(device_id: str) -> None:
    _cancelled_devices.discard(device_id)


def is_cancelled(device_id: str) -> bool:
    return device_id in _cancelled_devices
