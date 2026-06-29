"""Launch autoslideshow automation and run farm batch when ingest completes."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from imouse_farm.captions.service import farm_devices_sorted, generate_captions_for_devices
from imouse_farm.config.models import AppConfig, SlideshowConfig
from imouse_farm.integrations.slideshow_jobs import SlideshowJobStore
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class SlideshowOrchestrator:
    def __init__(
        self,
        config: SlideshowConfig,
        app_config: AppConfig,
        job_store: SlideshowJobStore,
        farm_batch: Any,
        device_manager: Any,
        dashboard_host: str,
        dashboard_port: int,
    ) -> None:
        self._config = config
        self._app_config = app_config
        self._jobs = job_store
        self._farm_batch = farm_batch
        self._device_manager = device_manager
        self._farm_base = f"http://{dashboard_host}:{dashboard_port}"
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def automation_url(self, job_id: str, brand: str, slots: list[str]) -> str:
        params = {
            "jobId": job_id,
            "brand": brand,
            "farmUrl": self._farm_base,
            "slots": ",".join(slots),
        }
        if self._config.farm_secret:
            params["secret"] = self._config.farm_secret
        params["slideshowsPerSlot"] = str(max(1, int(self._config.slideshows_per_slot)))
        base = str(self._config.app_base_url or "").rstrip("/")
        return f"{base}/automation?{urlencode(params)}"

    async def start_job(
        self,
        *,
        brand: str,
        slots: list[str] | None = None,
        run_batch: bool = True,
    ) -> dict[str, Any]:
        if not self._config.enabled:
            raise RuntimeError("Slideshow integration is disabled in config.yaml")

        brand_key = str(brand or "labely").strip().lower()
        slot_list = [str(s).strip() for s in (slots or []) if str(s).strip()]
        if not slot_list:
            devices = farm_devices_sorted(self._device_manager)
            slot_list = [str(d.user_name).strip() for d in devices if str(d.user_name).strip()]
        if not slot_list:
            raise RuntimeError("No farm slots found — register phones in iMouse first")

        job = await self._jobs.create(brand=brand_key, slots=slot_list, run_batch=run_batch)
        await self._jobs.update(
            job.id,
            status="running",
            phase="automation",
            message="Opening slideshow automation…",
        )

        if job.id in self._tasks and not self._tasks[job.id].done():
            raise RuntimeError(f"Job {job.id} is already running")

        self._tasks[job.id] = asyncio.create_task(self._run_job(job.id))
        url = self.automation_url(job.id, brand_key, slot_list)
        return {"job": (await self._jobs.get(job.id)).to_dict(), "automation_url": url}

    async def on_automation_done(self, job_id: str) -> dict[str, Any]:
        job = await self._jobs.get(job_id)
        if not job:
            raise RuntimeError(f"Unknown job {job_id}")

        await self._jobs.update(
            job_id,
            phase="batch",
            message="Slideshow ingest complete — starting farm batch…",
        )

        if not job.run_batch:
            await self._jobs.update(
                job_id,
                status="completed",
                phase="done",
                message="Ingest complete (batch run skipped).",
            )
            return (await self._jobs.get(job_id)).to_dict()

        devices = farm_devices_sorted(self._device_manager)
        wanted = {str(s) for s in job.slots}
        selected = [d for d in devices if str(d.user_name) in wanted]
        if not selected:
            await self._jobs.update(
                job_id,
                status="failed",
                error="No online farm phones matched job slots",
            )
            raise RuntimeError("No farm phones found for batch run")

        if self._farm_batch.is_running():
            await self._jobs.update(
                job_id,
                status="failed",
                error="Farm batch already running",
            )
            raise RuntimeError("A batch run is already in progress")

        if self._config.auto_generate_captions:
            await self._jobs.update(
                job_id,
                phase="captions",
                message="Generating AI captions for selected phones…",
            )
            caption_result = await generate_captions_for_devices(
                self._app_config,
                selected,
                onscreen_template=self._config.default_onscreen_template,
                brand=job.brand,
            )
            if caption_result["generated"] == 0:
                detail = (
                    caption_result["errors"][0]["error"]
                    if caption_result["errors"]
                    else "No captions generated"
                )
                await self._jobs.update(
                    job_id,
                    status="failed",
                    error=f"Caption generation failed: {detail}",
                )
                raise RuntimeError(f"Caption generation failed: {detail}")
            await self._jobs.update(
                job_id,
                message=(
                    f"Captions ready for {caption_result['generated']} phone(s)"
                    + (
                        f" ({caption_result['failed']} failed)"
                        if caption_result["failed"]
                        else ""
                    )
                    + " — starting batch…"
                ),
            )

        started = await self._farm_batch.start(selected, brand=job.brand)
        if not started:
            await self._jobs.update(
                job_id,
                status="failed",
                error="Failed to start farm batch",
            )
            raise RuntimeError("Failed to start farm batch")

        await self._jobs.update(
            job_id,
            status="completed",
            phase="done",
            message=f"Batch started for {len(selected)} phone(s).",
        )
        return (await self._jobs.get(job_id)).to_dict()

    async def _run_job(self, job_id: str) -> None:
        job = await self._jobs.get(job_id)
        if not job:
            return
        url = self.automation_url(job.id, job.brand, job.slots)
        script = PROJECT_ROOT / "scripts" / "run_slideshow_automation.py"
        try:
            if self._config.use_playwright_runner and script.is_file():
                await self._jobs.update(
                    job_id,
                    message="Playwright automation runner started…",
                )
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    str(script),
                    "--url",
                    url,
                    "--timeout",
                    str(int(self._config.automation_timeout_seconds)),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(PROJECT_ROOT),
                    env=os.environ.copy(),
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    err = (stderr or stdout or b"").decode("utf-8", errors="replace")[:500]
                    await self._jobs.update(
                        job_id,
                        status="failed",
                        phase="automation",
                        error=err or f"Automation exited {proc.returncode}",
                    )
                    return
            else:
                await self._jobs.update(
                    job_id,
                    message="Open automation URL in Chrome (Playwright runner disabled).",
                )
        except Exception as exc:
            logger.exception("slideshow_job_failed", job_id=job_id)
            await self._jobs.update(
                job_id,
                status="failed",
                phase="automation",
                error=str(exc),
            )
