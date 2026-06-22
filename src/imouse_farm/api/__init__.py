"""iMouseXP SDK client (use controller.DeviceController)."""

from imouse_farm.controller.device_controller import DeviceController, DeviceStatus

IMouseClient = DeviceController
DeviceInfo = DeviceStatus

__all__ = ["DeviceController", "DeviceStatus", "IMouseClient", "DeviceInfo"]
