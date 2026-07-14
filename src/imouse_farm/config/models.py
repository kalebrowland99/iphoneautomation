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
    VPN_ON = "vpn_on"
    VPN_OFF = "vpn_off"
    CLOSE_APP = "close_app"
    KILL_APP = "kill_app"
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
    permission_watcher_poll_seconds: float = 0.25
    contacts_watcher_poll_seconds: float = 0.2


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


class OpenAICaptionConfig(BaseModel):
    """OpenAI settings for AI-generated TikTok captions."""

    enabled: bool = True
    api_key: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = 0.85
    # Vision model for tapping the account-switcher dropdown arrow.
    account_switcher_vision_model: str = "gpt-5.5"


class DashboardConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    farm_slots: int = 20
    split_windows_on_run: bool = True
    chrome_side: str = "left"  # left | right — Chrome half; iMouseXP gets the other half
    imouse_window_title: str = "iMouse"


class TabCoord(BaseModel):
    x: int = 0
    y: int = 0


class TikTokNavigationConfig(BaseModel):
    tiktok_home_icon: TabCoord = Field(default_factory=lambda: TabCoord(x=507, y=1011))
    profile_tab: TabCoord = Field(default_factory=lambda: TabCoord(x=559, y=1037))
    home_tab: TabCoord = Field(default_factory=lambda: TabCoord(x=60, y=1041))
    account_switcher_opener: TabCoord = Field(
        default_factory=lambda: TabCoord(x=293, y=249)
    )
    account_switcher_opener_alt: TabCoord = Field(
        default_factory=lambda: TabCoord(x=301, y=288)
    )
    account_name_search_rect_pct: list[float] = Field(
        default_factory=lambda: [0.0, 0.0, 1.0, 0.35]
    )

    @property
    def tiktok_home_icon_x(self) -> int:
        return int(self.tiktok_home_icon.x)

    @property
    def tiktok_home_icon_y(self) -> int:
        return int(self.tiktok_home_icon.y)

    @property
    def profile_tab_x(self) -> int:
        return int(self.profile_tab.x)

    @property
    def profile_tab_y(self) -> int:
        return int(self.profile_tab.y)

    @property
    def home_tab_x(self) -> int:
        return int(self.home_tab.x)

    @property
    def home_tab_y(self) -> int:
        return int(self.home_tab.y)

    @property
    def account_switcher_opener_x(self) -> int:
        return int(self.account_switcher_opener.x)

    @property
    def account_switcher_opener_y(self) -> int:
        return int(self.account_switcher_opener.y)

    @property
    def account_switcher_opener_alt_x(self) -> int:
        return int(self.account_switcher_opener_alt.x)

    @property
    def account_switcher_opener_alt_y(self) -> int:
        return int(self.account_switcher_opener_alt.y)


class TikTokDeviceUiSlotConfig(BaseModel):
    """Per-phone TikTok UI differences (farm slot = device user_name)."""

    ui_label: str = "Different UI"
    account_switcher_opener: TabCoord = Field(
        default_factory=lambda: TabCoord(x=101, y=147)
    )
    use_alternate_account_switcher: bool = True


class TikTokDeviceUiConfig(BaseModel):
    slots: dict[str, TikTokDeviceUiSlotConfig] = Field(default_factory=dict)


class SlideshowConfig(BaseModel):
    """Local slideshow-ui → gallery ingest → farm batch pipeline."""

    enabled: bool = True
    app_base_url: str = "http://localhost:3000"
    app_port: int = 3000
    farm_secret: str = ""
    slideshows_per_slot: int = 3
    slides_per_slideshow: int = 1
    use_embedded_runner: bool = True
    use_playwright_runner: bool = False
    automation_timeout_seconds: float = 3600.0
    clear_slot_before_ingest: bool = True
    auto_generate_captions: bool = True
    default_onscreen_template: str = "america_sick"
    blank_video_max_retries: int = 2
    debug_slideshows_per_slot: int = 1


class WarmupConfig(BaseModel):
    """Pre-post TikTok feed scroll settings."""

    duration_seconds: float = 1200.0
    swipe_delay_min_seconds: float = 0.0
    swipe_delay_max_seconds: float = 53.0
    swipe_delay_mean_seconds: float = 4.0
    swipe_delay_long_watch_probability: float = 0.20
    double_tap_interval_seconds: float = 0.35
    max_retry_attempts: int = 3


class SessionRecordingConfig(BaseModel):
    """Debug MP4 recordings of each phone's batch session."""

    enabled: bool = True
    fps: float = 2.0


class KernelRecoveryConfig(BaseModel):
    """Restart iMouseXP kernel and recast after repeated infrastructure failures."""

    enabled: bool = True
    failure_threshold: int = 2
    max_recovery_attempts: int = 2
    kernel_restart_wait_seconds: float = 20.0


class VpnConfig(BaseModel):
    """Shadowrocket VPN via iMouse shortcut_exec_url (opens URL on the phone)."""

    shortcut_url_on: str = "shadowrocket://connect"
    shortcut_url_off: str = "shadowrocket://disconnect"
    shortcut_url_toggle: str = "shadowrocket://toggle"
    shortcut_url_open: str = "shadowrocket://"
    shortcut_settle_seconds: float = 120.0
    shortcut_url_timeout_ms: int = 120000
    confirm_via_vision: bool = False
    confirm_max_attempts: int = 2
    confirm_settle_seconds: float = 2.0


class BatchConfig(BaseModel):
    batch_size: int = 1
    cast_connect_max_attempts: int = 8
    cast_connect_retry_seconds: float = 15.0
    batch_device_timeout_seconds: float = 7200.0
    disconnect_on_complete: bool = True
    between_phones_pause_seconds: float = 2.0
    chain_valcoin_after_labely: bool = True
    skip_prep_when_valid: bool = True
    warmup: WarmupConfig = Field(default_factory=WarmupConfig)
    session_recording: SessionRecordingConfig = Field(default_factory=SessionRecordingConfig)
    kernel_recovery: KernelRecoveryConfig = Field(default_factory=KernelRecoveryConfig)


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "json"
    file: str | None = "data/logs/imouse_farm.log"


class DiagnosticsConfig(BaseModel):
    """Runtime diagnostics — phone restart recovery timing."""

    phone_restart_boot_wait_seconds: float = 90.0


class AppConfig(BaseModel):
    imouse: IMouseConfig = Field(default_factory=IMouseConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    screenshots: ScreenshotsConfig = Field(default_factory=ScreenshotsConfig)
    gallery: GalleryConfig = Field(default_factory=GalleryConfig)
    openai: OpenAICaptionConfig = Field(default_factory=OpenAICaptionConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    timing: TimingConfig = Field(default_factory=TimingConfig)
    device_groups: dict[str, DeviceGroupConfig] = Field(default_factory=dict)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    slideshow: SlideshowConfig = Field(default_factory=SlideshowConfig)
    batch: BatchConfig = Field(default_factory=BatchConfig)
    diagnostics: DiagnosticsConfig = Field(default_factory=DiagnosticsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    workflows_directory: str = "config/workflows"
    tiktok_navigation: TikTokNavigationConfig = Field(default_factory=TikTokNavigationConfig)
    tiktok_device_ui: TikTokDeviceUiConfig = Field(default_factory=TikTokDeviceUiConfig)
    vpn: VpnConfig = Field(default_factory=VpnConfig)


class WorkflowStepConfig(BaseModel):
    type: str
    name: str
    on_failure: str = "continue"  # continue | retry | escalate | stop | pause
    when_state: DeviceState | None = None
    when_detection: str | None = None
    unless_detection: str | None = None
    when_post_index: int | None = None
    when_debug_skip_post: bool | None = None
    unless_debug_skip_post: bool | None = None
    when_use_supplied_videos: bool | None = None
    unless_use_supplied_videos: bool | None = None
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
    # After this step succeeds, verify the expected screen element is present
    # before moving on. Set to a template filename stem (e.g. "plus") or OCR
    # keyword (e.g. "Next"). If detection fails, vision recovery is triggered.
    screen_check: str | None = None


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
