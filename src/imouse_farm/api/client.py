"""Backward-compatible re-exports — use controller.DeviceController instead."""

from imouse_farm.controller.device_controller import DeviceController, DeviceStatus

# Legacy aliases
IMouseClient = DeviceController
DeviceInfo = DeviceStatus
IMouseDeviceHandle = None  # removed: all ops go through DeviceController

__all__ = ["DeviceController", "DeviceStatus", "IMouseClient", "DeviceInfo"]
