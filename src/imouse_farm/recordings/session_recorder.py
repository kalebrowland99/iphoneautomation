"""Per-phone session screen recordings for batch debugging."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


def session_recording_dir(base_directory: str, slot: str, *, when: datetime | None = None) -> Path:
    """``gallery/<slot>/<YYYY-MM-DD>/`` for debug session videos."""
    day = (when or datetime.now()).strftime("%Y-%m-%d")
    folder = Path(base_directory).resolve() / str(slot).strip() / day
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def session_recording_path(base_directory: str, slot: str, *, when: datetime | None = None) -> Path:
    """``gallery/<slot>/<date>/session_HHMMSS.mp4``."""
    ts = (when or datetime.now()).strftime("%H%M%S")
    return session_recording_dir(base_directory, slot, when=when) / f"session_{ts}.mp4"


def _decode_frame(screenshot_bytes: bytes) -> np.ndarray | None:
    arr = np.frombuffer(screenshot_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


@dataclass
class _ActiveRecording:
    device_id: str
    slot: str
    output_path: Path
    task: asyncio.Task[None]
    writer: Any
    frame_size: tuple[int, int] | None = None
    frames_written: int = 0
    started_at: float = field(default_factory=time.monotonic)


class SessionRecordingManager:
    """Capture cast screenshots into an MP4 while a phone session is active."""

    def __init__(self) -> None:
        self._active: dict[str, _ActiveRecording] = {}

    def is_recording(self, device_id: str) -> bool:
        return device_id in self._active

    async def start(
        self,
        controller: Any,
        device_id: str,
        slot: str,
        output_path: Path,
        *,
        fps: float = 2.0,
        log_activity: Any | None = None,
    ) -> Path | None:
        if device_id in self._active:
            return self._active[device_id].output_path

        path = Path(output_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        interval = 1.0 / max(0.5, float(fps))

        async def _loop() -> None:
            recording = self._active.get(device_id)
            if not recording:
                return
            try:
                while device_id in self._active:
                    try:
                        screenshot = await controller.capture_screenshot(device_id)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "session_recording_capture_failed",
                            device_id=device_id,
                            slot=slot,
                            error=str(exc),
                        )
                        await asyncio.sleep(interval)
                        continue

                    if not screenshot:
                        await asyncio.sleep(interval)
                        continue

                    frame = _decode_frame(screenshot)
                    if frame is None:
                        await asyncio.sleep(interval)
                        continue

                    h, w = frame.shape[:2]
                    if recording.writer is None:
                        fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # type: ignore[attr-defined]
                        recording.writer = cv2.VideoWriter(str(path), fourcc, float(fps), (w, h))
                        recording.frame_size = (w, h)
                        logger.info(
                            "session_recording_started",
                            device_id=device_id,
                            slot=slot,
                            path=str(path),
                            fps=fps,
                            width=w,
                            height=h,
                        )
                        if log_activity:
                            await log_activity(
                                "info",
                                "batch",
                                f"Session recording started — {path.name} (slot {slot})",
                                device_id,
                            )
                    elif recording.frame_size != (w, h):
                        frame = cv2.resize(frame, recording.frame_size)

                    recording.writer.write(frame)
                    recording.frames_written += 1
                    await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "session_recording_loop_failed",
                    device_id=device_id,
                    slot=slot,
                    error=str(exc),
                )

        task = asyncio.create_task(_loop(), name=f"session-recording-{device_id}")
        self._active[device_id] = _ActiveRecording(
            device_id=device_id,
            slot=str(slot),
            output_path=path,
            task=task,
            writer=None,
        )
        return path

    async def stop(self, device_id: str, *, log_activity: Any | None = None) -> Path | None:
        recording = self._active.pop(device_id, None)
        if not recording:
            return None

        recording.task.cancel()
        try:
            await recording.task
        except asyncio.CancelledError:
            pass

        if recording.writer is not None:
            recording.writer.release()

        elapsed = time.monotonic() - recording.started_at
        if recording.frames_written > 0 and recording.output_path.is_file():
            logger.info(
                "session_recording_saved",
                device_id=device_id,
                slot=recording.slot,
                path=str(recording.output_path),
                frames=recording.frames_written,
                elapsed_seconds=round(elapsed, 1),
            )
            if log_activity:
                await log_activity(
                    "info",
                    "batch",
                    (
                        f"Session recording saved — {recording.output_path} "
                        f"({recording.frames_written} frames)"
                    ),
                    device_id,
                )
            return recording.output_path

        if recording.output_path.exists():
            recording.output_path.unlink(missing_ok=True)
        logger.info(
            "session_recording_empty",
            device_id=device_id,
            slot=recording.slot,
            elapsed_seconds=round(elapsed, 1),
        )
        return None

    async def stop_all(self) -> None:
        for device_id in list(self._active):
            await self.stop(device_id)
