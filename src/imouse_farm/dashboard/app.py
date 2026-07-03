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
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from imouse_farm.config.models import ActionType, AppConfig
from imouse_farm.dashboard.activity import enrich_activity
from imouse_farm.dashboard.brands import get_brand, load_brands, render_dashboard_html
from imouse_farm.dashboard.stop import stop_device_automation
from imouse_farm.dashboard.window_layout import tile_chrome_imouse
from imouse_farm.dashboard.test_actions import (
    list_debug_tests,
    run_debug_test,
    tap_vpntoggle,
)
from imouse_farm.captions.ai_generator import (
    extract_food_names_from_stems,
    generate_labely_onscreen_texts,
    stem_to_food_name,
)
from imouse_farm.captions.onscreen_templates import apply_onscreen_for_stems
from imouse_farm.captions.prompt_store import (
    get_ai_settings,
    set_ai_hashtags,
    set_ai_prompt,
)
from imouse_farm.captions.service import (
    farm_devices_sorted,
    generate_captions_for_device,
    generate_captions_for_devices,
)
from imouse_farm.post.account_profile_store import (
    brand_profile_key,
    clear_cant_cast_imouse,
    clear_prep_completed,
    reset_all_session_states,
    get_brand_profile,
    get_profile,
    get_profile_for_device,
    is_cant_cast_imouse,
    list_profiles,
    mark_run_failed,
    mark_run_started,
    mark_run_success,
    set_cant_cast_imouse,
    set_profile,
)
from imouse_farm.post.brand_keys import device_storage_key as _device_storage_key
from imouse_farm.post.post_caption_store import (
    POST_COUNT,
    clear_all_post_texts,
    device_storage_key,
    get_final_caption,
    get_onscreen_text,
    list_post_texts,
    media_index_for_post,
    post_media_stem,
    set_final_caption,
    set_onscreen_text,
    text_key_for_device,
    validate_post_texts,
)
from imouse_farm.settings.device_settings import (
    get_debug_skip_post,
    get_device_settings,
    set_debug_skip_post,
)
from imouse_farm.dashboard.run_status import compute_run_progress
from imouse_farm.dashboard.slideshow_routes import register_slideshow_routes
from imouse_farm.utils.gallery import list_media_stems_for_posts, phone_gallery_folder
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


def _normalize_brand(brand: str | None) -> str:
    b = str(brand or "labely").strip().lower()
    return b if b in ("labely", "valcoin") else "labely"


def _post_text_key(device: Any, brand: str | None = None) -> str:
    return text_key_for_device(
        device.device_id,
        device.user_name,
        brand=_normalize_brand(brand),
    )


def _slot_profile_key(slot: int) -> str:
    return f"slot:{int(slot)}"


class ActionBody(BaseModel):
    action_type: ActionType
    params: dict[str, Any] = Field(default_factory=dict)


class WorkflowStartBody(BaseModel):
    workflow_name: str
    device_id: str
    start_post_index: int | None = None


class PipelineStartBody(BaseModel):
    from_post: int | None = None  # omit / null = full prep→post→end; 1–3 = post N→3 + end only
    brand: str | None = None


class BatchStartBody(BaseModel):
    slots: list[int] | None = None  # farm slot numbers; default = all registered phones
    from_post: int | None = None
    brand: str | None = None


class CaptionAISettingsBody(BaseModel):
    prompt: str = ""
    hashtags: str = ""
    brand: str | None = None


class CaptionAIGenerateBody(BaseModel):
    prompt: str | None = None
    hashtags: str | None = None
    onscreen_template: str | None = None
    all_phones: bool = False
    brand: str | None = None


class OnscreenTemplateApplyBody(BaseModel):
    template_key: str
    brand: str | None = None


class PostTextFieldBody(BaseModel):
    text: str = ""


class DeviceSettingsBody(BaseModel):
    debug_skip_post: bool = False


class WindowLayoutBody(BaseModel):
    brand: str = "labely"


class AccountProfileBody(BaseModel):
    tiktok_handle: str | None = None
    brand: str = "labely"
    warmup_enabled: bool | None = None


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
    brands = load_brands()
    farm_slots = int(getattr(config.dashboard, "farm_slots", 20) or 20)

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
    async def index_labely() -> str:
        return render_dashboard_html(
            Path(__file__).parent / "templates" / "index.html",
            brand_id="labely",
            farm_slots=farm_slots,
            brands=brands,
        )

    @app.get("/valcoin", response_class=HTMLResponse)
    async def index_valcoin() -> str:
        return render_dashboard_html(
            Path(__file__).parent / "templates" / "index.html",
            brand_id="valcoin",
            farm_slots=farm_slots,
            brands=brands,
        )

    @app.get("/api/brands")
    async def list_brand_definitions() -> dict[str, Any]:
        return {"brands": brands, "default": "labely"}

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/window-layout/split")
    async def split_chrome_imouse_windows(body: WindowLayoutBody | None = None) -> dict[str, Any]:
        brand = str((body.brand if body else None) or "labely").strip().lower()
        return tile_chrome_imouse(app_instance.config.dashboard, brand=brand)

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=204)

    @app.post("/api/server/restart")
    async def restart_server() -> dict[str, Any]:
        if _restart_scheduled:
            return {"success": True, "message": "Restart already in progress"}
        _schedule_server_restart(app_instance)
        return {"success": True, "message": "Server restarting…"}

    @app.get("/api/devices")
    async def list_devices(brand: str | None = None) -> list[dict[str, Any]]:
        dm = app_instance.device_manager
        brand_filter = str(brand or "").strip().lower()
        result: list[dict[str, Any]] = []
        for device in dm.devices.values():
            base_key = device_storage_key(device.device_id, device.user_name)
            profile = (
                get_brand_profile(base_key, brand_filter)
                if brand_filter
                else get_profile(base_key)
            )
            data = dm.to_dict(device)
            data["debug_skip_post"] = get_debug_skip_post(device.device_id)
            data["pipeline"] = app_instance.workflow_pipeline.get_status(device.device_id)
            data["account_profile"] = profile
            result.append(data)
        return result

    @app.get("/api/account-profiles")
    async def get_account_profiles(brand: str | None = None) -> dict[str, Any]:
        return {"profiles": list_profiles(brand=brand)}

    @app.get("/api/devices/{device_id:path}/account-profile")
    async def get_device_account_profile(
        device_id: str,
        brand: str | None = None,
    ) -> dict[str, Any]:
        device = app_instance.device_manager.get_device(device_id)
        if not device:
            raise HTTPException(404, "Device not found")
        b = str(brand or "labely").strip().lower()
        return {"profile": get_profile_for_device(device_id, device.user_name, brand=b)}

    @app.put("/api/devices/{device_id:path}/account-profile")
    async def update_device_account_profile(
        device_id: str,
        body: AccountProfileBody,
    ) -> dict[str, Any]:
        device = app_instance.device_manager.get_device(device_id)
        if not device:
            raise HTTPException(404, "Device not found")
        key = device_storage_key(device.device_id, device.user_name)
        fields = body.model_dump(exclude_unset=True)
        brand = str(fields.pop("brand", body.brand) or "labely")
        profile = set_profile(key, brand=brand, **fields)
        return {"profile": profile}

    @app.get("/api/slots/{slot}/account-profile")
    async def get_slot_account_profile(slot: int, brand: str | None = None) -> dict[str, Any]:
        if slot < 1 or slot > farm_slots:
            raise HTTPException(400, "Invalid slot")
        b = str(brand or "labely").strip().lower()
        return {"profile": get_brand_profile(f"slot:{int(slot)}", b)}

    @app.put("/api/slots/{slot}/account-profile")
    async def update_slot_account_profile(
        slot: int,
        body: AccountProfileBody,
    ) -> dict[str, Any]:
        if slot < 1 or slot > farm_slots:
            raise HTTPException(400, "Invalid slot")
        profile = set_profile(
            f"slot:{int(slot)}",
            brand=body.brand or "labely",
            **body.model_dump(exclude_unset=True, exclude={"brand"}),
        )
        return {"profile": profile}

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

    @app.post("/api/devices/{device_id:path}/disconnect")
    async def disconnect_device_airplay(device_id: str) -> dict[str, Any]:
        device = app_instance.device_manager.get_device(device_id)
        if not device:
            raise HTTPException(404, "Device not found")
        success = await app_instance.device_manager.disconnect_airplay(device_id)
        updated = app_instance.device_manager.get_device(device_id)
        return {"success": success, "connected": bool(updated and updated.is_online)}

    @app.get("/api/batch/status")
    async def get_batch_status() -> dict[str, Any]:
        return app_instance.farm_batch.get_status()

    @app.post("/api/batch/start")
    async def start_farm_batch(body: BatchStartBody | None = None) -> dict[str, Any]:
        if app_instance.farm_batch.is_running():
            raise HTTPException(400, "A batch run is already in progress")
        from_post = body.from_post if body else None
        brand = str((body.brand if body else None) or "labely").strip().lower()
        devices = farm_devices_sorted(app_instance.device_manager)
        if body and body.slots:
            wanted = {str(s) for s in body.slots}
            devices = [d for d in devices if str(d.user_name) in wanted]
        if not devices:
            raise HTTPException(400, "No farm phones found for batch run")
        started = await app_instance.farm_batch.start(
            devices, from_post=from_post, brand=brand
        )
        if not started:
            raise HTTPException(400, "Failed to start batch run")
        return {"success": True, "device_count": len(devices), "status": app_instance.farm_batch.get_status()}

    @app.post("/api/batch/stop")
    async def stop_farm_batch() -> dict[str, Any]:
        await app_instance.slideshow_orchestrator.cancel_running_jobs()
        await app_instance.farm_batch.stop()
        return {"success": True, "status": app_instance.farm_batch.get_status()}

    @app.post("/api/batch/reset-session")
    async def reset_batch_session() -> dict[str, Any]:
        """Clear prep, last-run, and gallery videos for all slots."""
        from imouse_farm.integrations.slideshow_ingest import clear_all_slot_media

        farm_slots = int(getattr(app_instance.config.dashboard, "farm_slots", 20) or 20)
        cleared = reset_all_session_states(farm_slots=farm_slots)
        videos_removed = clear_all_slot_media(
            app_instance.config.gallery.base_directory,
            list(app_instance.config.gallery.media_extensions),
            farm_slots=farm_slots,
        )
        return {
            "success": True,
            "cleared_slots": cleared,
            "videos_removed": videos_removed,
        }

    @app.post("/api/batch/clear-cant-cast/{slot}")
    async def clear_cant_cast_slot(slot: str) -> dict[str, Any]:
        """Remove the cant_cast_imouse tag from a slot so it will be attempted again."""
        base_key = f"slot:{slot.lower()}"
        clear_cant_cast_imouse(base_key)
        return {"success": True, "slot": slot}

    @app.get("/api/debug/tests")
    async def get_debug_tests(group: str | None = None) -> list[dict[str, Any]]:
        return list_debug_tests(group)

    @app.get("/api/devices/{device_id:path}/settings")
    async def get_device_settings_route(device_id: str) -> dict[str, Any]:
        device = app_instance.device_manager.get_device(device_id)
        if not device:
            raise HTTPException(404, "Device not found")
        settings = get_device_settings(device_id)
        pipeline = app_instance.workflow_pipeline.get_status(device_id)
        return {"settings": settings, "pipeline": pipeline}

    @app.put("/api/devices/{device_id:path}/settings")
    async def update_device_settings(device_id: str, body: DeviceSettingsBody) -> dict[str, Any]:
        device = app_instance.device_manager.get_device(device_id)
        if not device:
            raise HTTPException(404, "Device not found")
        set_debug_skip_post(device_id, body.debug_skip_post)
        return {"settings": get_device_settings(device_id)}

    @app.post("/api/devices/{device_id:path}/pipeline/start")
    async def start_pipeline(device_id: str, body: PipelineStartBody | None = None) -> dict[str, Any]:
        device = app_instance.device_manager.get_device(device_id)
        if not device:
            raise HTTPException(404, "Device not found")
        from_post = body.from_post if body else None
        brand = str((body.brand if body else None) or "labely").strip().lower()
        brand = _normalize_brand(body.brand if body else None)
        text_key = _post_text_key(device, brand)
        check_from = from_post if from_post is not None else 1
        missing = validate_post_texts(text_key, from_post=check_from, brand=brand)
        if missing:
            raise HTTPException(400, "; ".join(missing))
        success = await app_instance.workflow_pipeline.start(
            device_id,
            from_post=from_post,
            brand=brand,
            chain_valcoin_after_labely=(
                brand == "labely"
                and from_post is None
                and app_instance.config.batch.chain_valcoin_after_labely
            ),
        )
        if not success:
            raise HTTPException(400, "Failed to start full run — workflow may already be active")
        return {"success": True, "from_post": from_post}

    @app.post("/api/devices/{device_id:path}/pipeline/pause")
    async def pause_pipeline(device_id: str) -> dict[str, Any]:
        success = await app_instance.workflow_pipeline.pause(device_id)
        if not success:
            raise HTTPException(400, "No active full run to pause")
        return {"success": True}

    @app.post("/api/devices/{device_id:path}/pipeline/resume")
    async def resume_pipeline(device_id: str) -> dict[str, Any]:
        success = await app_instance.workflow_pipeline.resume(device_id)
        if not success:
            raise HTTPException(400, "Full run is not paused")
        return {"success": True}

    @app.post("/api/devices/{device_id:path}/pipeline/stop")
    async def stop_pipeline(device_id: str) -> dict[str, Any]:
        return await stop_device_automation(app_instance, device_id)

    @app.get("/api/devices/{device_id:path}/post-texts")
    async def get_device_post_texts(
        device_id: str,
        brand: str | None = None,
    ) -> dict[str, Any]:
        device = app_instance.device_manager.get_device(device_id)
        if not device:
            raise HTTPException(404, "Device not found")
        brand_key = _normalize_brand(brand)
        gallery = app_instance.config.gallery
        folder = phone_gallery_folder(
            gallery.base_directory,
            device.user_name,
            device.phone_name,
            brand=brand_key,
        )
        media_stems = list_media_stems_for_posts(folder, gallery.media_extensions, POST_COUNT)
        text_key = _post_text_key(device, brand_key)
        posts = []
        for row in list_post_texts(text_key, brand=brand_key):
            post_num = int(row["post"])
            stem = post_media_stem(media_stems, post_num)
            posts.append({
                **row,
                "media_file": stem,
                "placeholder": stem,
                "food_name": stem_to_food_name(stem),
            })
        return {"posts": posts, "media_files": media_stems, "brand": brand_key}

    @app.put("/api/devices/{device_id:path}/post-texts/{post_num}/onscreen")
    async def set_device_onscreen_text(
        device_id: str,
        post_num: int,
        body: PostTextFieldBody,
        brand: str | None = None,
    ) -> dict[str, str]:
        device = app_instance.device_manager.get_device(device_id)
        if not device:
            raise HTTPException(404, "Device not found")
        if post_num < 1 or post_num > POST_COUNT:
            raise HTTPException(400, f"post_num must be 1..{POST_COUNT}")
        brand_key = _normalize_brand(brand)
        text_key = _post_text_key(device, brand_key)
        set_onscreen_text(text_key, post_num, body.text, brand=brand_key)
        return {"text": get_onscreen_text(text_key, post_num, brand=brand_key)}

    @app.put("/api/devices/{device_id:path}/post-texts/{post_num}/final")
    async def set_device_final_caption(
        device_id: str,
        post_num: int,
        body: PostTextFieldBody,
        brand: str | None = None,
    ) -> dict[str, str]:
        device = app_instance.device_manager.get_device(device_id)
        if not device:
            raise HTTPException(404, "Device not found")
        if post_num < 1 or post_num > POST_COUNT:
            raise HTTPException(400, f"post_num must be 1..{POST_COUNT}")
        brand_key = _normalize_brand(brand)
        text_key = _post_text_key(device, brand_key)
        set_final_caption(text_key, post_num, body.text, brand=brand_key)
        return {"text": get_final_caption(text_key, post_num, brand=brand_key)}

    @app.post("/api/devices/{device_id:path}/post-texts/clear")
    async def clear_device_post_texts(
        device_id: str,
        brand: str | None = None,
    ) -> dict[str, bool]:
        device = app_instance.device_manager.get_device(device_id)
        if not device:
            raise HTTPException(404, "Device not found")
        clear_all_post_texts(_post_text_key(device, brand), brand=_normalize_brand(brand))
        return {"success": True}

    @app.get("/api/caption-ai/settings")
    async def get_caption_ai_settings(brand: str | None = None) -> dict[str, str]:
        return get_ai_settings(_normalize_brand(brand))

    @app.put("/api/caption-ai/settings")
    async def update_caption_ai_settings(body: CaptionAISettingsBody) -> dict[str, str]:
        brand_key = _normalize_brand(body.brand)
        set_ai_prompt(body.prompt, brand=brand_key)
        set_ai_hashtags(body.hashtags, brand=brand_key)
        return get_ai_settings(brand_key)

    @app.post("/api/devices/{device_id:path}/onscreen-template/apply")
    async def apply_device_onscreen_template(
        device_id: str, body: OnscreenTemplateApplyBody
    ) -> dict[str, Any]:
        from imouse_farm.captions.onscreen_templates import ONSCREEN_TEMPLATES

        device = app_instance.device_manager.get_device(device_id)
        if not device:
            raise HTTPException(404, "Device not found")
        brand_key = _normalize_brand(body.brand)
        openai_cfg = app_instance.config.openai
        if not openai_cfg.enabled:
            raise HTTPException(400, "OpenAI caption generation is disabled in config")

        template_key = body.template_key.strip()
        if template_key not in ONSCREEN_TEMPLATES:
            raise HTTPException(400, f"Unknown onscreen template: {template_key}")

        gallery = app_instance.config.gallery
        folder = phone_gallery_folder(
            gallery.base_directory,
            device.user_name,
            device.phone_name,
            brand=brand_key,
        )
        media_stems = list_media_stems_for_posts(folder, gallery.media_extensions, POST_COUNT)
        if not any(media_stems):
            raise HTTPException(
                400,
                f"No media files in gallery folder: {folder}",
            )

        text_key = _post_text_key(device, brand_key)
        try:
            if brand_key == "labely":
                onscreen_lines = await generate_labely_onscreen_texts(
                    media_stems,
                    template_key=template_key,
                    config=openai_cfg,
                )
                foods = await extract_food_names_from_stems(media_stems, config=openai_cfg)
                applied = 0
                for post_num, line in enumerate(onscreen_lines, start=1):
                    if not line.strip():
                        continue
                    set_onscreen_text(text_key, post_num, line, brand=brand_key)
                    applied += 1
            else:
                foods = await extract_food_names_from_stems(media_stems, config=openai_cfg)
                from imouse_farm.post.post_caption_store import foods_post_order_to_file_order

                applied = apply_onscreen_for_stems(
                    template_key,
                    media_stems,
                    text_key,
                    set_onscreen_text=set_onscreen_text,
                    food_names=foods_post_order_to_file_order(foods),
                )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            logger.error("onscreen_template_apply_failed", device_id=device_id, error=str(exc))
            raise HTTPException(502, f"OpenAI request failed: {exc}") from exc

        if not applied:
            raise HTTPException(400, "Could not build onscreen text from gallery filenames")

        posts: list[dict[str, Any]] = []
        for row in list_post_texts(text_key, brand=brand_key):
            post_num = int(row["post"])
            stem = post_media_stem(media_stems, post_num)
            food = (
                foods[post_num - 1]
                if post_num - 1 < len(foods)
                else stem_to_food_name(stem)
            )
            posts.append({
                **row,
                "onscreen": get_onscreen_text(text_key, post_num, brand=brand_key),
                "media_file": stem,
                "food_name": food,
            })
        return {"posts": posts, "media_files": media_stems, "applied": applied, "brand": brand_key}

    @app.post("/api/devices/{device_id:path}/caption-ai/generate")
    async def generate_device_captions(
        device_id: str, body: CaptionAIGenerateBody | None = None
    ) -> dict[str, Any]:
        if body and body.all_phones:
            return await generate_all_captions(body)

        device = app_instance.device_manager.get_device(device_id)
        if not device:
            raise HTTPException(404, "Device not found")
        brand_key = _normalize_brand(body.brand if body else None)
        try:
            result = await generate_captions_for_device(
                app_instance.config,
                device,
                prompt=body.prompt if body else None,
                hashtags=body.hashtags if body else None,
                onscreen_template=body.onscreen_template if body else None,
                brand=brand_key,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            logger.error("caption_ai_generate_failed", device_id=device_id, error=str(exc))
            raise HTTPException(502, f"OpenAI request failed: {exc}") from exc

        await app_instance.db.log_activity(
            "info",
            "caption",
            f"AI captions generated for {device.display_label}",
            device_id,
            {"posts": len(result.get("posts", []))},
        )
        return result

    async def generate_all_captions(body: CaptionAIGenerateBody | None) -> dict[str, Any]:
        devices = farm_devices_sorted(app_instance.device_manager)
        if not devices:
            raise HTTPException(400, "No farm phones registered")

        brand_key = _normalize_brand(body.brand if body else None)
        result = await generate_captions_for_devices(
            app_instance.config,
            devices,
            prompt=body.prompt if body else None,
            hashtags=body.hashtags if body else None,
            onscreen_template=body.onscreen_template if body else None,
            brand=brand_key,
        )

        await app_instance.db.log_activity(
            "info",
            "caption",
            f"AI captions generated for {result['generated']} phone(s)",
            None,
            {"ok": result["generated"], "failed": result["failed"]},
        )
        if result["generated"] == 0:
            detail = result["errors"][0]["error"] if result["errors"] else "No captions generated"
            raise HTTPException(400, detail)
        return result

    @app.post("/api/caption-ai/generate-all")
    async def generate_all_captions_route(
        body: CaptionAIGenerateBody | None = None,
    ) -> dict[str, Any]:
        return await generate_all_captions(body)

    @app.post("/api/devices/{device_id:path}/debug/{test_id}")
    async def run_device_debug_test(
        device_id: str,
        test_id: str,
        brand: str | None = None,
        skip_media: bool = False,
    ) -> dict[str, Any]:
        b = str(brand or "labely").strip().lower()
        return await run_debug_test(
            app_instance, device_id, test_id, brand=b, skip_media=skip_media
        )

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
        """Stop pipeline, workflows, queued actions, and duplicate server PIDs."""
        return await stop_device_automation(app_instance, device_id)

    @app.get("/api/devices/{device_id:path}")
    async def get_device(device_id: str) -> dict[str, Any]:
        device = app_instance.device_manager.get_device(device_id)
        if not device:
            raise HTTPException(404, "Device not found")
        data = app_instance.device_manager.to_dict(device)
        data["debug_skip_post"] = get_debug_skip_post(device_id)
        data["pipeline"] = app_instance.workflow_pipeline.get_status(device_id)
        return data

    @app.get("/api/workflows")
    async def list_workflows() -> list[dict[str, Any]]:
        return app_instance.workflow_engine.list_workflows()

    @app.get("/api/workflows/running")
    async def list_running_workflows() -> list[dict[str, str]]:
        return app_instance.workflow_engine.list_running()

    @app.post("/api/workflows/start")
    async def start_workflow(body: WorkflowStartBody) -> dict[str, Any]:
        success = await app_instance.workflow_engine.start_workflow(
            body.workflow_name,
            body.device_id,
            start_post_index=body.start_post_index,
        )
        if not success:
            raise HTTPException(400, "Failed to start workflow")
        await app_instance.db.log_activity(
            "info",
            "workflow",
            f"Start requested: {body.workflow_name}",
            body.device_id,
            {
                "workflow_name": body.workflow_name,
                "start_post_index": body.start_post_index,
                "source": "dashboard",
            },
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

    @app.get("/api/run/status")
    async def get_run_status(job_id: str | None = None) -> dict[str, Any]:
        await app_instance.slideshow_orchestrator.resume_orphan_jobs()
        batch = app_instance.farm_batch.get_status()
        orch_busy = app_instance.slideshow_orchestrator.orchestrator_busy()

        job_data: dict[str, Any] | None = None
        resolved_job_id = str(job_id or "").strip()
        if resolved_job_id:
            job = await app_instance.slideshow_jobs.get(resolved_job_id)
            if job:
                job_data = job.to_dict()

        if not job_data:
            for row in await app_instance.slideshow_jobs.list_jobs(limit=20):
                if str(row.get("status") or "").lower() == "running":
                    job_data = row
                    resolved_job_id = str(row.get("id") or "")
                    break

        progress = compute_run_progress(slideshow_job=job_data, batch=batch)
        if orch_busy and not progress.get("active"):
            progress = {
                **progress,
                "active": True,
                "phase": progress.get("phase") or "slideshow",
                "phase_label": progress.get("phase_label") or "Slideshow in progress",
                "progress": max(int(progress.get("progress") or 0), 12),
                "message": progress.get("message")
                or "Slideshow automation is still running — click Stop to cancel.",
            }

        return {
            "batch": batch,
            "slideshow_job": job_data,
            "slideshow_job_id": resolved_job_id or None,
            "slideshow_orchestrator_busy": orch_busy,
            "progress": progress,
        }

    register_slideshow_routes(
        app,
        config=config,
        get_app=lambda: app_instance,
    )

    return app
