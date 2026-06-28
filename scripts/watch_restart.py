"""Development helper — run the server and restart when source files change."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
CONFIG = PROJECT_ROOT / "config" / "config.yaml"
LOCK_FILE = PROJECT_ROOT / "data" / "watch_restart.lock"

# Load .env before spawning the server subprocess.
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from imouse_farm.utils.env_file import load_env_file  # noqa: E402

load_env_file(PROJECT_ROOT / ".env")

WATCH_DIRS = (
    PROJECT_ROOT / "src",
    PROJECT_ROOT / "config",
)
WATCH_EXTENSIONS = {".py", ".yaml", ".yml", ".html"}
IGNORE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".venv"}
DEBOUNCE_SECONDS = 1.5
POLL_INTERVAL = 0.5


def _iter_watch_files() -> list[Path]:
    files: list[Path] = []
    for root in WATCH_DIRS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in IGNORE_DIR_NAMES for part in path.parts):
                continue
            if path.suffix.lower() in WATCH_EXTENSIONS:
                files.append(path)
    return files


def _snapshot_mtimes() -> dict[Path, float]:
    snapshot: dict[Path, float] = {}
    for path in _iter_watch_files():
        try:
            snapshot[path] = path.stat().st_mtime
        except OSError:
            continue
    return snapshot


def _files_changed(before: dict[Path, float], after: dict[Path, float]) -> bool:
    if before.keys() != after.keys():
        return True
    return any(before.get(path) != mtime for path, mtime in after.items())


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _acquire_watcher_lock() -> bool:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        try:
            existing = int(LOCK_FILE.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            existing = 0
        if existing and existing != os.getpid() and _pid_alive(existing):
            print(
                f"Another watch_restart is already running (PID {existing}). Exiting.",
                file=sys.stderr,
            )
            return False
    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _release_watcher_lock() -> None:
    if not LOCK_FILE.exists():
        return
    try:
        if int(LOCK_FILE.read_text(encoding="utf-8").strip()) == os.getpid():
            LOCK_FILE.unlink(missing_ok=True)
    except (OSError, ValueError):
        LOCK_FILE.unlink(missing_ok=True)


def _start_server() -> subprocess.Popen[bytes]:
    print("Starting iMouse Farm...", flush=True)
    print("Dashboard: http://localhost:8080", flush=True)
    print("Auto-restart enabled — edit src/ or config/ to reload.", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    print("", flush=True)
    return subprocess.Popen(
        [str(PYTHON), "-m", "imouse_farm.main", "-c", str(CONFIG.relative_to(PROJECT_ROOT))],
        cwd=PROJECT_ROOT,
        env={**dict(os.environ), "IMOUSE_FARM_WATCHER": "1"},
    )


def _stop_server(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    print("Stopping server...", flush=True)
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


def main() -> int:
    if not PYTHON.exists():
        print("Missing .venv — run setup.ps1 first.", file=sys.stderr)
        return 1
    if not _acquire_watcher_lock():
        return 1

    mtimes = _snapshot_mtimes()
    proc = _start_server()
    pending_restart = False
    change_seen_at = 0.0

    try:
        while True:
            time.sleep(POLL_INTERVAL)

            if proc.poll() is not None:
                print("Server exited — restarting in 2s...", flush=True)
                time.sleep(2)
                mtimes = _snapshot_mtimes()
                proc = _start_server()
                pending_restart = False
                continue

            current = _snapshot_mtimes()
            if _files_changed(mtimes, current):
                if not pending_restart:
                    pending_restart = True
                    change_seen_at = time.time()
                elif time.time() - change_seen_at >= DEBOUNCE_SECONDS:
                    print("Changes detected — restarting server...", flush=True)
                    _stop_server(proc)
                    time.sleep(1)
                    mtimes = _snapshot_mtimes()
                    proc = _start_server()
                    pending_restart = False
            else:
                pending_restart = False

    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
        _stop_server(proc)
        return 0
    finally:
        _release_watcher_lock()


if __name__ == "__main__":
    raise SystemExit(main())
