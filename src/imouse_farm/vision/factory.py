"""Vision provider factory."""

from __future__ import annotations

from imouse_farm.config.models import AppConfig
from imouse_farm.vision.base import VisionProvider
from imouse_farm.vision.model_provider import LocalModelVisionProvider
from imouse_farm.vision.opencv_provider import OpenCVVisionProvider


def create_vision_provider(config: AppConfig) -> VisionProvider:
    """Create the configured vision provider."""
    opencv = OpenCVVisionProvider(config.analysis, config.workflows_directory)
    provider_name = config.vision.provider

    if provider_name == "local_model":
        return LocalModelVisionProvider(opencv, config.vision.model_path)
    return opencv
