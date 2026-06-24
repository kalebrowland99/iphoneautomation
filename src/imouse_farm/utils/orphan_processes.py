"""Remove duplicate iMouse Farm / watch_restart Python processes (Windows)."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


def cleanup_orphan_imouse_processes(port: int = 8080) -> dict[str, Any]:
    """Kill stray watch_restart / imouse_farm PIDs; keep the server on ``port``."""
    if sys.platform != "win32":
        return {"killed_pids": [], "kept_pids": [os.getpid()], "skipped": True}

    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
$keep = @({os.getpid()})
$listeners = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue
foreach ($l in $listeners) {{ $keep += $l.OwningProcess }}
foreach ($seed in @($keep)) {{
    $p = $seed
    for ($i = 0; $i -lt 8; $i++) {{
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$p"
        if (-not $proc) {{ break }}
        $keep += $proc.ProcessId
        if (-not $proc.ParentProcessId -or $proc.ParentProcessId -eq 0) {{ break }}
        $p = $proc.ParentProcessId
    }}
}}
$keep = @($keep | Select-Object -Unique)
$killed = @()
Get-CimInstance Win32_Process -Filter "name='python.exe'" |
    Where-Object {{
        ($_.CommandLine -like '*imouse_farm*' -or $_.CommandLine -like '*watch_restart*') -and
        ($keep -notcontains $_.ProcessId)
    }} |
    ForEach-Object {{
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        $killed += $_.ProcessId
    }}
Write-Output ("KEEP:" + ($keep -join ','))
Write-Output ("KILLED:" + ($killed -join ','))
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        logger.warning("orphan_cleanup_failed", error=str(exc))
        return {"killed_pids": [], "kept_pids": [], "error": str(exc)}

    kept: list[int] = []
    killed: list[int] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("KEEP:"):
            kept = [int(p) for p in line[5:].split(",") if p.isdigit()]
        elif line.startswith("KILLED:"):
            killed = [int(p) for p in line[7:].split(",") if p.isdigit()]

    if killed:
        logger.info("orphan_processes_killed", pids=killed, kept=kept)
    return {"killed_pids": killed, "kept_pids": kept}
