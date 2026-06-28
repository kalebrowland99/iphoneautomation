"""Album clear timing defaults."""

import inspect

from imouse_farm.controller.device_controller import DeviceController


def test_album_clear_sheet_appear_timeout_default() -> None:
    sig = inspect.signature(DeviceController.album_clear)
    assert sig.parameters["sheet_appear_timeout"].default == 18.0
    assert sig.parameters["round_active_timeout"].default == 60.0
    assert sig.parameters["sheet_poll_interval_seconds"].default == 5.0
    assert sig.parameters["timeout_ms"].default == 60000
    assert sig.parameters["post_grace_seconds"].default == 20.0
