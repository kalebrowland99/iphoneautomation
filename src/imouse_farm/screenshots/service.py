"""Screenshot capture via DeviceController SDK."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from imouse_farm.config.models import AppConfig
from imouse_farm.controller.device_controller import DeviceController
from imouse_farm.database.repository import DatabaseRepository
from imouse_farm.devices.manager import DeviceManager
from imouse_farm.utils.logging import get_logger
from imouse_farm.utils.paths import safe_device_dir_name

logger = get_logger(__name__)


def _image_extension(data: bytes) -> str:
    if data.startswith(b"\xff\xd8"):
        return ".jpg"
    if data.startswith(b"BM"):
        return ".bmp"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    return ".bin"


class ScreenshotService:
    """Capture device screenshots through the iMouseXP SDK."""

    def __init__(
        self,
        config: AppConfig,
        controller: DeviceController,
        device_manager: DeviceManager,
        db: DatabaseRepository,
    ) -> None:
        self._config = config
        self._controller = controller
        self._device_manager = device_manager
        self._db = db
        self._screenshot_dir = Path(config.screenshots.directory)
        self._periodic_task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._running = False
        self._latest: dict[str, str] = {}

    async def start(self) -> None:
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._running = True
        self._periodic_task = asyncio.create_task(self._periodic_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("screenshot_service_started", directory=str(self._screenshot_dir))

    async def stop(self) -> None:
        self._running = False
        for task in (self._periodic_task, self._cleanup_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def capture(
        self,
        device_id: str,
        workflow_id: str | None = None,
    ) -> dict[str, Any] | None:
        device = self._device_manager.get_device(device_id)
        if not device or not device.is_online:
            logger.warning("screenshot_device_offline", device_id=device_id)
            return None

        data = await self._controller.capture_screenshot(device_id)
        if not data:
            await self._device_manager.record_failure(device_id)
            return None

        await self._device_manager.record_activity(device_id)

        device_dir = self._screenshot_dir / safe_device_dir_name(device_id)
        device_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        file_path = device_dir / f"{timestamp}{_image_extension(data)}"
        file_path.write_bytes(data)

        width, height = 0, 0
        try:
            arr = np.frombuffer(data, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is not None:
                height, width = img.shape[:2]
        except Exception:
            pass

        screenshot_id = await self._db.save_screenshot(
            device_id, str(file_path), width, height, workflow_id
        )
        self._latest[device_id] = str(file_path)

        logger.info(
            "screenshot_saved",
            device_id=device_id,
            path=str(file_path),
            width=width,
            height=height,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        return {
            "id": screenshot_id,
            "device_id": device_id,
            "file_path": str(file_path),
            "width": width,
            "height": height,
        }

    async def get_latest_path(self, device_id: str) -> str | None:
        if device_id in self._latest:
            return self._latest[device_id]
        record = await self._db.get_latest_screenshot(device_id)
        if record:
            self._latest[device_id] = record["file_path"]
            return record["file_path"]
        return None

    async def get_by_device(self, device_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return await self._db.list_screenshots(device_id, limit)

    async def _periodic_loop(self) -> None:
        interval = self._config.screenshots.periodic_interval_seconds
        while self._running:
            for device in self._device_manager.devices.values():
                if device.is_online:
                    try:
                        await self.capture(device.device_id)
                    except Exception as exc:
                        logger.error("periodic_screenshot_failed", device_id=device.device_id, error=str(exc))
            await asyncio.sleep(interval)

    async def _cleanup_loop(self) -> None:
        while self._running:
            try:
                await self._cleanup_old()
            except Exception as exc:
                logger.error("screenshot_cleanup_failed", error=str(exc))
            await asyncio.sleep(3600)

    async def _cleanup_old(self) -> None:
        retention = self._config.screenshots.retention_hours
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=retention)).isoformat()
        paths = await self._db.delete_old_screenshots(cutoff)
        for path in paths:
            Path(path).unlink(missing_ok=True)
        if paths:
            logger.info("screenshots_cleaned", count=len(paths))
