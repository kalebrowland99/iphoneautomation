"""Tests for VPN status via Shadowrocket OCR."""

from imouse_farm.config.models import DeviceState
from imouse_farm.vision.base import VisionAnalysis
from imouse_farm.vision.opencv_provider import OpenCVVisionProvider
from imouse_farm.config.models import AnalysisConfig


def _provider() -> OpenCVVisionProvider:
    return OpenCVVisionProvider(AnalysisConfig(), "config/workflows")


def test_vpn_off_when_not_connected_visible() -> None:
    analysis = VisionAnalysis(
        device_id="d1",
        screenshot_path="x.png",
        ocr_text="Status Not Connected",
        detections=[],
    )
    rules = [
        {"condition": "ocr_contains", "text": "Not Connected", "state": "WAITING"},
        {"condition": "default", "state": "ACTIVE"},
    ]
    assert _provider().evaluate_state_rules(rules, analysis) == DeviceState.WAITING


def test_vpn_on_when_not_connected_absent() -> None:
    analysis = VisionAnalysis(
        device_id="d1",
        screenshot_path="x.png",
        ocr_text="Connected 12ms",
        detections=[],
    )
    rules = [
        {"condition": "ocr_contains", "text": "Not Connected", "state": "WAITING"},
        {"condition": "default", "state": "ACTIVE"},
    ]
    assert _provider().evaluate_state_rules(rules, analysis) == DeviceState.ACTIVE
