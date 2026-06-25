"""Tests for OCR search region helpers."""

from types import SimpleNamespace

from imouse_farm.actions.engine import _ocr_search_rect


class _FakeDeviceManager:
    def __init__(self, device: SimpleNamespace | None = None) -> None:
        self._device = device

    def get_device(self, device_id: str) -> SimpleNamespace | None:
        return self._device


def test_ocr_search_rect_from_pct() -> None:
    dm = _FakeDeviceManager(SimpleNamespace(screen_width=400, screen_height=800))
    rect = _ocr_search_rect(
        dm,
        "dev1",
        {"search_rect_pct": [0.0, 0.0, 1.0, 0.32]},
    )
    assert rect == [0, 0, 400, 256]


def test_ocr_search_rect_explicit() -> None:
    dm = _FakeDeviceManager()
    rect = _ocr_search_rect(dm, "missing", {"rect": [10, 20, 300, 100]})
    assert rect == [10, 20, 300, 100]
