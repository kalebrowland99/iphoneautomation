"""Tests for per-phone session screen recordings."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from imouse_farm.recordings.session_recorder import (
    SessionRecordingManager,
    session_recording_dir,
    session_recording_path,
)


def test_session_recording_path_uses_slot_and_date() -> None:
    when = datetime(2026, 7, 6, 21, 30, 0)
    path = session_recording_path("gallery", "7", when=when)
    assert path.name == "session_213000.mp4"
    assert path.parent.name == "2026-07-06"
    assert path.parent.parent.name == "7"


def test_session_recording_dir_creates_date_folder(tmp_path: Path) -> None:
    folder = session_recording_dir(str(tmp_path), "12", when=datetime(2026, 7, 6))
    assert folder.is_dir()
    assert folder.name == "2026-07-06"


@pytest.mark.asyncio
async def test_session_recording_writes_mp4(tmp_path: Path) -> None:
    manager = SessionRecordingManager()
    controller = MagicMock()
    frame = np.zeros((120, 80, 3), dtype=np.uint8)
    ok, encoded = __import__("cv2").imencode(".jpg", frame)
    assert ok
    controller.capture_screenshot = AsyncMock(return_value=encoded.tobytes())

    output = tmp_path / "2" / "2026-07-06" / "session_120000.mp4"
    await manager.start(controller, "dev-2", "2", output, fps=10.0)
    await asyncio.sleep(0.35)
    saved = await manager.stop("dev-2")

    assert saved is not None
    assert saved.is_file()
    assert saved.stat().st_size > 0
