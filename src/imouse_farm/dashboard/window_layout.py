"""Windows desktop helpers for farm operator layout."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from imouse_farm.config.models import DashboardConfig
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TILE_SCRIPT = PROJECT_ROOT / "scripts" / "tile_chrome_imouse.ps1"


def farm_dashboard_url(config: DashboardConfig, brand: str) -> str:
    port = int(config.port or 8080)
    host = "localhost"
    base = f"http://{host}:{port}"
    key = str(brand or "labely").strip().lower()
    if key == "valcoin":
        return f"{base}/valcoin"
    return f"{base}/"


def tile_chrome_imouse(
    config: DashboardConfig,
    *,
    brand: str = "labely",
) -> dict[str, Any]:
    """Launch/focus Chrome and tile it 50/50 with iMouseXP (Windows only)."""
    if sys.platform != "win32":
        return {"ok": False, "skipped": True, "reason": "Windows only"}

    if not config.split_windows_on_run:
        return {"ok": False, "skipped": True, "reason": "split_windows_on_run disabled"}

    if not TILE_SCRIPT.is_file():
        return {"ok": False, "error": f"Missing script: {TILE_SCRIPT}"}

    farm_url = farm_dashboard_url(config, brand)
    side = str(config.chrome_side or "left").strip().lower()
    if side not in ("left", "right"):
        side = "left"

    cmd = [
        "powershell.exe",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(TILE_SCRIPT),
        "-FarmUrl",
        farm_url,
        "-ChromeSide",
        side,
        "-IMouseTitleContains",
        str(config.imouse_window_title or "iMouse"),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        raw = (proc.stdout or "").strip()
        if raw:
            try:
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                pass
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
            logger.warning("tile_chrome_imouse_failed", error=err)
            return {"ok": False, "error": err}
        return {"ok": True, "stdout": raw}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "tile script timed out"}
    except OSError as exc:
        logger.warning("tile_chrome_imouse_error", error=str(exc))
        return {"ok": False, "error": str(exc)}
