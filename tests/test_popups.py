"""Tests for popup manager."""

from imouse_farm.config.models import DetectionResult, DeviceState
from imouse_farm.popups.manager import PopupManager, PopupType
from imouse_farm.vision.base import VisionAnalysis


def test_detect_unknown_screen() -> None:
    manager = PopupManager("config/workflows")
    analysis = VisionAnalysis(
        device_id="test-device",
        screenshot_path="/tmp/test.bmp",
        detected_state=DeviceState.UNKNOWN_SCREEN,
    )
    result = manager.detect(analysis)
    assert result.detected is True
    assert result.popup_type == PopupType.UNKNOWN
    assert result.should_pause is True


def test_detect_permission_popup() -> None:
    manager = PopupManager("config/workflows")
    analysis = VisionAnalysis(
        device_id="test-device",
        screenshot_path="/tmp/test.bmp",
        popup_type="permission_dialog",
        detections=[DetectionResult(name="permission_allow", confidence=0.9, x=100, y=200)],
    )
    result = manager.detect(analysis)
    assert result.detected is True
    assert result.popup_type == PopupType.PERMISSION


def test_no_popup_on_known_screen() -> None:
    manager = PopupManager("config/workflows")
    analysis = VisionAnalysis(
        device_id="test-device",
        screenshot_path="/tmp/test.bmp",
        detected_state=DeviceState.IDLE,
        detections=[DetectionResult(name="home_screen", confidence=0.95, x=0, y=0)],
    )
    result = manager.detect(analysis)
    assert result.detected is False
