"""Pydantic configuration models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DeviceState(str, Enum):
    """Per-device operational state."""

    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    WAITING = "WAITING"
    ERROR = "ERROR"
    UNKNOWN_SCREEN = "UNKNOWN_SCREEN"
    DISCONNECTED = "DISCONNECTED"


class ActionType(str, Enum):
    """Supported device action types (all executed via iMouseXP SDK)."""

    TAP = "tap"
    TAP_DETECTION = "tap_detection"  # tap on vision-detected element (state-based)
    TAP_OCR = "tap_ocr"  # tap text found via iMouse on-device OCR
    SWIPE = "swipe"
    LONG_PRESS = "long_press"
    DRAG = "drag"  # press-hold at start, swipe to end, release
    TEXT_INPUT = "text_input"
    HOME = "home"
    MOUSE_RESET = "mouse_reset"  # iMouse cursor reset
    LOCK = "lock"
    UNLOCK = "unlock"
    LAUNCH_APP = "launch_app"
    OPEN_URL = "open_url"
    CLOSE_APP = "close_app"
    ALBUM_CLEAR = "album_clear"
    ALBUM_UPLOAD = "album_upload"
    CLEAR_TEXT = "clear_text"
    KEY = "key"


class IMouseConfig(BaseModel):
    host: str = "localhost"
    port: int = 9911
    mode: str = "websocket"
    reconnect_interval_seconds: float = 5.0
    device_poll_interval_seconds: float = 10.0
    auto_airplay_reconnect: bool = False
    airplay_reconnect_on_startup: bool = False
    airplay_connect_delay_seconds: float = 4.0
    airplay_reconnect_interval_seconds: float = 30.0


class DatabaseConfig(BaseModel):
    path: str = "data/imouse_farm.db"


class GalleryConfig(BaseModel):
    """PC-side media folders pushed to devices via iMouse album APIs."""

    base_directory: str = "gallery"
    media_extensions: list[str] = Field(
        default_factory=lambda: [".mp4", ".mov", ".m4v", ".jpg", ".jpeg", ".png", ".heic"]
    )
    upload_timeout_ms: int = 300000


class ScreenshotsConfig(BaseModel):
    directory: str = "data/screenshots"
    retention_hours: int = 24
    periodic_interval_seconds: float = 60.0
    max_per_device: int = 100


class AnalysisConfig(BaseModel):
    template_match_threshold: float = 0.8
    small_template_threshold: float = 0.42
    use_device_template_match: bool = True
    ocr_language: str = "eng"
    tesseract_cmd: str | None = None
    templates_directory: str = "config/templates"


class VisionConfig(BaseModel):
    """Pluggable vision provider configuration."""

    provider: str = "opencv_tesseract"  # opencv_tesseract | local_model
    model_path: str = ""


class TimingConfig(BaseModel):
    action_retry_count: int = 0
    action_retry_delay_seconds: float = 2.0
    action_timeout_seconds: float = 30.0
    frozen_device_threshold_seconds: float = 120.0
    workflow_step_delay_seconds: float = 0.25
    unknown_screen_escalation_count: int = 5


class DeviceGroupConfig(BaseModel):
    description: str = ""
    workflow: str = "basic_monitor"


class DiscordConfig(BaseModel):
    enabled: bool = False
    webhook_url: str = ""


class TelegramConfig(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


class NotificationEventsConfig(BaseModel):
    device_disconnect: bool = True
    unknown_screen: bool = True
    repeated_failures: bool = True
    workflow_completion: bool = True


class NotificationsConfig(BaseModel):
    enabled: bool = True
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    events: NotificationEventsConfig = Field(default_factory=NotificationEventsConfig)
    repeated_failure_threshold: int = 3


class DashboardConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "json"
    file: str | None = "data/logs/imouse_farm.log"


class AppConfig(BaseModel):
    imouse: IMouseConfig = Field(default_factory=IMouseConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    screenshots: ScreenshotsConfig = Field(default_factory=ScreenshotsConfig)
    gallery: GalleryConfig = Field(default_factory=GalleryConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    timing: TimingConfig = Field(default_factory=TimingConfig)
    device_groups: dict[str, DeviceGroupConfig] = Field(default_factory=dict)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    workflows_directory: str = "config/workflows"


class WorkflowStepConfig(BaseModel):
    type: str
    name: str
    on_failure: str = "continue"  # continue | retry | escalate | stop | pause
    when_state: DeviceState | None = None
    when_detection: str | None = None
    unless_detection: str | None = None
    requires_screenshot: bool = False
    requires_analysis: bool = False
    duration_seconds: float | None = None
    min_seconds: float | None = None
    max_seconds: float | None = None
    templates: list[str] = Field(default_factory=list)
    ocr_keywords: list[str] = Field(default_factory=list)
    ocr_regions: list[dict[str, Any]] = Field(default_factory=list)
    skip_post_action: bool = False
    state_rules: list[dict[str, Any]] = Field(default_factory=list)
    action: dict[str, Any] = Field(default_factory=dict)
    condition: str | None = None
    template: str | None = None


class WorkflowConfig(BaseModel):
    name: str
    description: str = ""
    enabled: bool = True
    loop: bool = True
    max_iterations: int = 0
    device_groups: list[str] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    steps: list[WorkflowStepConfig] = Field(default_factory=list)


class ActionRequest(BaseModel):
    """Queued action for a device."""

    device_id: str
    action_type: ActionType
    params: dict[str, Any] = Field(default_factory=dict)
    workflow_id: str | None = None
    step_name: str | None = None


class DetectionResult(BaseModel):
    """Screen analysis detection result."""

    name: str
    confidence: float
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None
    detection_type: str = "template"  # template | ocr | ui_element


class ScreenAnalysisResult(BaseModel):
    """Aggregated screen analysis."""

    device_id: str
    screenshot_path: str
    detections: list[DetectionResult] = Field(default_factory=list)
    detected_state: DeviceState | None = None
    ocr_text: str = ""
