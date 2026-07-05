"""API routes for autoslideshow → gallery ingest → farm batch."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from imouse_farm.config.models import AppConfig
from imouse_farm.integrations.slideshow_ingest import (
    SlideshowVideoRejected,
    clear_slot_media,
    list_slot_media,
    normalize_slot,
    save_bytes_to_slot,
)
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


class SlideshowGenerateBody(BaseModel):
    brand: str = "labely"
    slots: list[int] | None = None
    run_batch: bool = True
    # Labely runs: farm slots also selected on the ValCoin brand batch picker.
    valcoin_slots: list[int] | None = None


class SlideshowAutomationFailedBody(BaseModel):
    error: str = "Automation failed"


def slideshow_farm_secret(config: AppConfig) -> str:
    return os.environ.get("FARM_SECRET", "").strip() or str(
        config.slideshow.farm_secret or ""
    ).strip()


def check_slideshow_secret(request: Request, config: AppConfig) -> None:
    expected = slideshow_farm_secret(config)
    if not expected:
        return
    got = str(request.headers.get("X-Farm-Secret") or "").strip()
    if got != expected:
        raise HTTPException(403, "Invalid farm secret")


def farm_public_host(host: str) -> str:
    cleaned = str(host or "").strip()
    if cleaned in ("0.0.0.0", "::", ""):
        return "localhost"
    return cleaned


def register_slideshow_routes(
    router: APIRouter,
    *,
    config: AppConfig,
    get_app: Any,
) -> None:
    @router.get("/api/slideshow/config")
    async def slideshow_config() -> dict[str, Any]:
        ss = config.slideshow
        return {
            "enabled": bool(ss.enabled),
            "app_base_url": str(ss.app_base_url or "").rstrip("/"),
            "app_port": int(ss.app_port),
            "use_embedded_runner": bool(ss.use_embedded_runner),
            "use_playwright_runner": bool(ss.use_playwright_runner),
            "slideshows_per_slot": int(ss.slideshows_per_slot),
            "slides_per_slideshow": int(ss.slides_per_slideshow),
        }

    @router.get("/api/slideshow/jobs")
    async def list_slideshow_jobs(limit: int = 20) -> list[dict[str, Any]]:
        app = get_app()
        return await app.slideshow_jobs.list_jobs(limit=limit)

    @router.get("/api/slideshow/jobs/{job_id}")
    async def get_slideshow_job(job_id: str) -> dict[str, Any]:
        app = get_app()
        job = await app.slideshow_jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        return job.to_dict()

    @router.post("/api/slideshow/ingest")
    async def ingest_slideshow(
        request: Request,
        slot: str = Form(...),
        job_id: str = Form(""),
        clear: str = Form(""),
        file: UploadFile = File(...),
    ) -> dict[str, Any]:
        check_slideshow_secret(request, config)
        if not config.slideshow.enabled:
            raise HTTPException(503, "Slideshow integration is disabled")

        try:
            app = get_app()
            slot_label = normalize_slot(slot)
            extensions = list(config.gallery.media_extensions)
            should_clear = str(clear or "").strip().lower() in ("1", "true", "yes")

            job_key = str(job_id or "").strip()
            ingested = await app.slideshow_jobs.get(job_key) if job_key else None
            job_brand = str(ingested.brand if ingested else "labely").strip().lower()
            slot_files = (ingested.ingested.get(slot_label, []) if ingested else []) or []
            if should_clear or (config.slideshow.clear_slot_before_ingest and not slot_files):
                clear_slot_media(
                    config.gallery.base_directory,
                    slot_label,
                    extensions,
                    brand=job_brand,
                )

            max_videos = max(1, int(ingested.videos_per_slot if ingested and ingested.videos_per_slot else config.slideshow.slideshows_per_slot))
            expected_slides = 4 if job_brand == "labely" else max(1, int(config.slideshow.slides_per_slideshow))
            on_disk = list_slot_media(
                config.gallery.base_directory,
                slot_label,
                extensions,
                brand=job_brand,
            )
            if len(on_disk) >= max_videos:
                raise HTTPException(
                    409,
                    f"Slot {slot_label} already has {max_videos} video(s) — extra upload skipped",
                )

            data = await file.read()
            if not data:
                raise HTTPException(400, "Empty upload")
            filename = str(file.filename or "slideshow.mp4").strip() or "slideshow.mp4"
            try:
                dest = save_bytes_to_slot(
                    data,
                    base_directory=config.gallery.base_directory,
                    slot=slot_label,
                    filename=filename,
                    expected_slides=expected_slides,
                    brand=job_brand,
                )
            except SlideshowVideoRejected as exc:
                if job_key:
                    await app.slideshow_jobs.record_reject(job_key, slot_label, str(exc))
                reason_code = "blank_video"
                lowered = str(exc).lower()
                if "blank slide" in lowered:
                    reason_code = "blank_slide"
                raise HTTPException(
                    422,
                    {
                        "success": False,
                        "retry": bool(exc.retry),
                        "reason": reason_code,
                        "slot": slot_label,
                        "message": str(exc),
                    },
                ) from exc
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc

            if job_key:
                await app.slideshow_jobs.record_ingest(job_key, slot_label, dest.name)

            return {
                "success": True,
                "slot": slot_label,
                "path": str(dest),
                "filename": dest.name,
                "bytes": len(data),
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(
                "slideshow_ingest_failed",
                slot=str(slot),
                job_id=str(job_id or ""),
            )
            raise HTTPException(500, f"Ingest failed: {exc}") from exc

    @router.post("/api/slideshow/jobs/{job_id}/automation-done")
    async def slideshow_automation_done(job_id: str, request: Request) -> dict[str, Any]:
        check_slideshow_secret(request, config)
        app = get_app()
        try:
            job = await app.slideshow_orchestrator.on_automation_done(job_id)
        except RuntimeError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"success": True, "job": job}

    @router.post("/api/slideshow/jobs/{job_id}/automation-failed")
    async def slideshow_automation_failed(
        job_id: str,
        request: Request,
        body: SlideshowAutomationFailedBody | None = None,
    ) -> dict[str, Any]:
        check_slideshow_secret(request, config)
        app = get_app()
        message = str((body.error if body else None) or "Automation failed").strip()
        job = await app.slideshow_orchestrator.on_automation_failed(job_id, message)
        return {"success": True, "job": job}

    @router.post("/api/slideshow/generate-and-run")
    async def slideshow_generate_and_run(
        body: SlideshowGenerateBody | None = None,
    ) -> dict[str, Any]:
        app = get_app()
        brand = str((body.brand if body else None) or "labely").strip().lower()
        slots = body.slots if body else None
        run_batch = body.run_batch if body else True
        try:
            valcoin_slots = (
                [str(s) for s in body.valcoin_slots]
                if body and body.valcoin_slots is not None
                else None
            )
            result = await app.slideshow_orchestrator.start_job(
                brand=brand,
                slots=[str(s) for s in slots] if slots else None,
                run_batch=bool(run_batch),
                valcoin_slots=valcoin_slots,
            )
        except RuntimeError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"success": True, **result}
