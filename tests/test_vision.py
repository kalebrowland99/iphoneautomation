"""Tests for vision provider."""

from imouse_farm.config.models import AnalysisConfig, VisionConfig, AppConfig
from imouse_farm.vision.factory import create_vision_provider
from imouse_farm.vision.opencv_provider import OpenCVVisionProvider


def test_create_opencv_provider() -> None:
    config = AppConfig(
        analysis=AnalysisConfig(),
        vision=VisionConfig(provider="opencv_tesseract"),
        workflows_directory="config/workflows",
    )
    provider = create_vision_provider(config)
    assert provider.name == "opencv_tesseract"


def test_iter_ui_elements_list_format() -> None:
    provider = OpenCVVisionProvider(AnalysisConfig(), "config/workflows")
    names = {e.get("name") for e in provider._iter_ui_elements()}
    assert "vpntoggle" in names
    assert "bluetoggle" in names


def test_evaluate_state_rules_ocr_missing() -> None:
    from imouse_farm.config.models import DeviceState
    from imouse_farm.vision.base import VisionAnalysis

    provider = OpenCVVisionProvider(AnalysisConfig(), "config/workflows")
    analysis = VisionAnalysis(
        device_id="d1",
        screenshot_path="test.bmp",
        ocr_text="Connected",
        detections=[],
    )
    rules = [{"condition": "ocr_missing", "text": "Not Connected", "state": "ACTIVE"}]
    state = provider.evaluate_state_rules(rules, analysis)
    assert state == DeviceState.ACTIVE


def test_evaluate_state_rules() -> None:
    from imouse_farm.config.models import DeviceState
    from imouse_farm.vision.base import VisionAnalysis

    provider = OpenCVVisionProvider(AnalysisConfig(), "config/workflows")
    analysis = VisionAnalysis(
        device_id="d1",
        screenshot_path="test.bmp",
        detections=[],
    )
    rules = [{"condition": "default", "state": "IDLE"}]
    state = provider.evaluate_state_rules(rules, analysis)
    assert state == DeviceState.IDLE
