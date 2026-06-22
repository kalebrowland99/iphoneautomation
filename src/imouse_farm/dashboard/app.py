"""FastAPI dashboard with real-time WebSocket updates."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from imouse_farm.config.models import ActionType, AppConfig
from imouse_farm.dashboard.activity import enrich_activity
from imouse_farm.dashboard.test_actions import list_debug_tests, run_debug_test, tap_vpntoggle
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


class ActionBody(BaseModel):
    action_type: ActionType
    params: dict[str, Any] = Field(default_factory=dict)


class WorkflowStartBody(BaseModel):
    workflow_name: str
    device_id: str


class ApplicationState:
    """Shared application state for dashboard routes."""

    def __init__(self) -> None:
        self.app_instance: Any = None
        self.ws_clients: list[WebSocket] = []

    async def broadcast(self, event: str, data: dict[str, Any]) -> None:
        message = json.dumps({"event": event, "data": data})
        dead: list[WebSocket] = []
        for ws in self.ws_clients:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.ws_clients.remove(ws)


app_state = ApplicationState()
_restart_scheduled = False
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _schedule_server_restart(app_instance: Any) -> None:
    global _restart_scheduled
    if _restart_scheduled:
        return
    _restart_scheduled = True

    async def _restart() -> None:
        await asyncio.sleep(0.4)
        logger.info("server_restart_requested")
        try:
            await app_instance.stop()
        except Exception as exc:
            logger.error("stop_before_restart_failed", error=str(exc))

        if os.environ.get("IMOUSE_FARM_WATCHER"):
            os._exit(0)

        restart_script = PROJECT_ROOT / "restart.ps1"
        if sys.platform == "win32" and restart_script.is_file():
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
                subprocess, "DETACHED_PROCESS", 0x00000008
            )
            subprocess.Popen(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(restart_script),
                ],
                cwd=PROJECT_ROOT,
                creationflags=flags,
            )
        os._exit(0)

    asyncio.create_task(_restart())


def create_app(config: AppConfig, app_instance: Any) -> FastAPI:
    """Create and configure the FastAPI dashboard application."""
    app_state.app_instance = app_instance

    app = FastAPI(
        title="iMouse Farm Dashboard",
        description="Multi-device iPhone automation dashboard for iMouseXP",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.dashboard.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        template_path = Path(__file__).parent / "templates" / "index.html"
        return template_path.read_text(encoding="utf-8")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/server/restart")
    async def restart_server() -> dict[str, Any]:
        if _restart_scheduled:
            return {"success": True, "message": "Restart already in progress"}
        _schedule_server_restart(app_instance)
        return {"success": True, "message": "Server restarting…"}

    @app.get("/api/devices")
    async def list_devices() -> list[dict[str, Any]]:
        dm = app_instance.device_manager
        return [dm.to_dict(d) for d in dm.devices.values()]

    _IMAGE_MEDIA = {
        ".bmp": "image/bmp",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }

    @app.get("/api/devices/{device_id:path}/screenshot")
    async def get_screenshot(device_id: str) -> FileResponse:
        path = await app_instance.screenshot_service.get_latest_path(device_id)
        if not path or not Path(path).exists():
            raise HTTPException(404, "No screenshot available")
        media_type = _IMAGE_MEDIA.get(Path(path).suffix.lower(), "application/octet-stream")
        return FileResponse(path, media_type=media_type)

    @app.post("/api/devices/{device_id:path}/screenshot")
    async def capture_screenshot(device_id: str) -> dict[str, Any]:
        device = app_instance.device_manager.get_device(device_id)
        if not device:
            raise HTTPException(404, "Device not found")
        if not device.is_online:
            raise HTTPException(
                503,
                "Device is offline in iMouse — connect AirPlay in iMouseXP first, then retry",
            )
        result = await app_instance.screenshot_service.capture(device_id)
        if not result:
            raise HTTPException(
                500,
                "Screenshot capture failed — ensure the device screen is mirrored in iMouseXP",
            )
        await app_state.broadcast("screenshot_captured", result)
        return result

    @app.get("/api/devices/{device_id:path}/actions")
    async def get_actions(device_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return await app_instance.db.get_action_history(device_id, limit)

    @app.get("/api/devices/{device_id:path}/errors")
    async def get_errors(device_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return await app_instance.db.get_error_history(device_id, limit)

    @app.get("/api/devices/{device_id:path}/states")
    async def get_states(device_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return await app_instance.db.get_state_transitions(device_id, limit)

    @app.post("/api/devices/{device_id:path}/connect")
    async def connect_device_airplay(device_id: str) -> dict[str, Any]:
        device = app_instance.device_manager.get_device(device_id)
        if not device:
            raise HTTPException(404, "Device not found")
        success = await app_instance.device_manager.reconnect_airplay(device_id)
        updated = app_instance.device_manager.get_device(device_id)
        return {"success": success, "connected": bool(updated and updated.is_online)}

    @app.get("/api/debug/tests")
    async def get_debug_tests() -> list[dict[str, str]]:
        return list_debug_tests()

    @app.post("/api/devices/{device_id:path}/debug/{test_id}")
    async def run_device_debug_test(device_id: str, test_id: str) -> dict[str, Any]:
        return await run_debug_test(app_instance, device_id, test_id)

    @app.post("/api/devices/{device_id:path}/test/tap-vpntoggle")
    async def test_tap_vpntoggle(device_id: str) -> dict[str, Any]:
        return await tap_vpntoggle(app_instance, device_id)

    @app.post("/api/devices/{device_id:path}/actions/execute")
    async def execute_action(device_id: str, body: ActionBody) -> dict[str, Any]:
        success = await app_instance.action_engine.execute_direct(
            device_id, body.action_type, body.params
        )
        return {"success": success}

    @app.post("/api/devices/{device_id:path}/workflows/stop")
    async def stop_device_workflow(device_id: str) -> dict[str, Any]:
        """Stop whatever workflow is on this device (running or paused)."""
        success = await app_instance.workflow_engine.stop_device(device_id)
        if success:
            await app_instance.db.log_activity(
                "warn", "workflow", "Stopped workflow", device_id, {"source": "dashboard"}
            )
        return {"success": success}

    @app.get("/api/devices/{device_id:path}")
    async def get_device(device_id: str) -> dict[str, Any]:
        device = app_instance.device_manager.get_device(device_id)
        if not device:
            raise HTTPException(404, "Device not found")
        return app_instance.device_manager.to_dict(device)

    @app.get("/api/workflows")
    async def list_workflows() -> list[dict[str, Any]]:
        return app_instance.workflow_engine.list_workflows()

    @app.get("/api/workflows/running")
    async def list_running_workflows() -> list[dict[str, str]]:
        return app_instance.workflow_engine.list_running()

    @app.post("/api/workflows/start")
    async def start_workflow(body: WorkflowStartBody) -> dict[str, Any]:
        success = await app_instance.workflow_engine.start_workflow(
            body.workflow_name, body.device_id
        )
        if not success:
            raise HTTPException(400, "Failed to start workflow")
        await app_instance.db.log_activity(
            "info",
            "workflow",
            f"Start requested: {body.workflow_name}",
            body.device_id,
            {"workflow_name": body.workflow_name, "source": "dashboard"},
        )
        await app_state.broadcast("workflow_started", body.model_dump())
        return {"success": True}

    @app.post("/api/workflows/stop")
    async def stop_workflow(body: WorkflowStartBody) -> dict[str, Any]:
        success = await app_instance.workflow_engine.stop_device(
            body.device_id, body.workflow_name or None
        )
        if success:
            await app_instance.db.log_activity(
                "warn",
                "workflow",
                f"Stopped: {body.workflow_name or 'all workflows'}",
                body.device_id,
                {"workflow_name": body.workflow_name, "source": "dashboard"},
            )
        return {"success": success}

    @app.get("/api/errors")
    async def list_all_errors(limit: int = 100) -> list[dict[str, Any]]:
        return await app_instance.db.get_error_history(limit=limit)

    @app.get("/api/activity")
    async def list_activity(
        limit: int = 150,
        device_id: str | None = None,
        level: str | None = None,
        category: str | None = None,
        since_id: int | None = None,
    ) -> list[dict[str, Any]]:
        dm = app_instance.device_manager
        labels = {d.device_id: d.display_label for d in dm.devices.values()}
        rows = await app_instance.db.get_activity_logs(
            device_id=device_id,
            level=level,
            category=category,
            limit=min(limit, 500),
            since_id=since_id,
        )
        return [enrich_activity(row, labels) for row in rows]

    @app.delete("/api/activity")
    async def clear_activity() -> dict[str, bool]:
        await app_instance.db.clear_activity_logs()
        return {"success": True}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        app_state.ws_clients.append(websocket)
        try:
            while True:
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                    if data == "ping":
                        await websocket.send_text(json.dumps({"event": "pong", "data": {}}))
                except asyncio.TimeoutError:
                    await websocket.send_text(json.dumps({"event": "heartbeat", "data": {}}))
        except WebSocketDisconnect:
            pass
        finally:
            if websocket in app_state.ws_clients:
                app_state.ws_clients.remove(websocket)

    return app
