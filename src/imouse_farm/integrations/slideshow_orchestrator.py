"""Launch autoslideshow automation and run farm batch when ingest completes."""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from imouse_farm.captions.service import (
    default_onscreen_template_for_brand,
    farm_devices_sorted,
    generate_captions_for_devices,
)
from imouse_farm.config.models import AppConfig, SlideshowConfig
from imouse_farm.integrations.slideshow_jobs import SlideshowJobStore
from imouse_farm.integrations.slideshow_ingest import (
    clear_slot_media,
    slot_gallery_status,
)
from imouse_farm.post.account_profile_store import get_profile_for_device
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _farm_public_host(host: str) -> str:
    cleaned = str(host or "").strip()
    if cleaned in ("0.0.0.0", "::", ""):
        return "localhost"
    return cleaned


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
        host = _farm_public_host(dashboard_host)
        self._farm_base = f"http://{host}:{dashboard_port}"
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._procs: dict[str, asyncio.subprocess.Process] = {}

    def _farm_secret(self) -> str:
        return os.environ.get("FARM_SECRET", "").strip() or str(
            self._config.farm_secret or ""
        ).strip()

    def _videos_per_slot(self, job: Any) -> int:
        override = int(getattr(job, "videos_per_slot", 0) or 0)
        if override > 0:
            return override
        return max(1, int(self._config.slideshows_per_slot))

    def automation_url(
        self,
        job_id: str,
        brand: str,
        slots: list[str],
        *,
        videos_per_slot: int | None = None,
    ) -> str:
        brand_key = str(brand or "labely").strip().lower()
        vps = max(1, int(videos_per_slot or self._config.slideshows_per_slot))
        params = {
            "jobId": job_id,
            "brand": brand_key,
            "farmUrl": self._farm_base,
            "slots": ",".join(slots),
        }
        if secret := self._farm_secret():
            params["secret"] = secret
        if brand_key == "labely":
            # Labely: slideshowsPerSlot = MP4 count; labelyScanSlotCount = Brave photos per MP4
            params["slideshowsPerSlot"] = str(vps)
            params["labelyScanSlotCount"] = "3"
        elif brand_key == "valcoin":
            # ValCoin: slidesPerSlideshow = separate MP4s; keep slideshowsPerSlot at 1
            params["slideshowsPerSlot"] = "1"
            params["slidesPerSlideshow"] = str(vps)
        else:
            params["slideshowsPerSlot"] = str(vps)
        base = str(self._config.app_base_url or "").rstrip("/")
        return f"{base}/automation?{urlencode(params)}"

    def _active_task_ids(self) -> set[str]:
        return {job_id for job_id, task in self._tasks.items() if not task.done()}

    def orchestrator_busy(self) -> bool:
        """True while an asyncio slideshow job task is still in flight."""
        return bool(self._active_task_ids())

    async def _clear_stale_jobs(self) -> None:
        """Re-spawn asyncio tasks for running jobs whose task died (e.g. server reload)."""
        await self.resume_orphan_jobs()

    def _ensure_job_task(self, job_id: str) -> bool:
        key = str(job_id or "").strip()
        if not key or key in self._active_task_ids():
            return False
        self._tasks[key] = asyncio.create_task(self._run_job(key))
        return True

    async def resume_orphan_jobs(self) -> None:
        """Restart pipeline tasks for parent jobs stuck in 'running' with no live task."""
        active = self._active_task_ids()
        for row in await self._jobs.list_jobs(limit=100):
            if str(row.get("status") or "").lower() != "running":
                continue
            if not row.get("run_batch", True):
                continue
            job_id = str(row.get("id") or "").strip()
            if not job_id or job_id in active:
                continue
            logger.info("slideshow_job_resuming", job_id=job_id)
            await self._jobs.update(
                job_id,
                message=str(row.get("message") or "Resuming slideshow pipeline…"),
            )
            self._ensure_job_task(job_id)

    async def start_job(
        self,
        *,
        brand: str,
        slots: list[str] | None = None,
        run_batch: bool = True,
        videos_per_slot: int | None = None,
    ) -> dict[str, Any]:
        if not self._config.enabled:
            raise RuntimeError("Slideshow integration is disabled in config.yaml")

        await self._clear_stale_jobs()

        brand_key = str(brand or "labely").strip().lower()
        slot_list = [str(s).strip() for s in (slots or []) if str(s).strip()]
        if not slot_list:
            devices = farm_devices_sorted(self._device_manager)
            slot_list = [str(d.user_name).strip() for d in devices if str(d.user_name).strip()]
        if not slot_list:
            raise RuntimeError("No farm slots found — register phones in iMouse first")

        if self._active_task_ids():
            raise RuntimeError("A slideshow automation job is already running")

        job = await self._jobs.create(
            brand=brand_key,
            slots=slot_list,
            run_batch=run_batch,
            videos_per_slot=int(videos_per_slot or 0),
        )

        if run_batch:
            # Per-slot pipeline: each slot encodes its own video then immediately
            # runs the batch for that phone. No all-slots URL is opened upfront.
            await self._jobs.update(
                job.id,
                status="running",
                phase="automation",
                message=f"Starting per-slot pipeline for {len(slot_list)} phone(s)…",
            )
            self._tasks[job.id] = asyncio.create_task(self._run_job(job.id))
            return {"job": (await self._jobs.get(job.id)).to_dict(), "automation_url": ""}

        # Video-only job (run_batch=False): open all slots at once in slideshow UI.
        vps = self._videos_per_slot(job)
        url = self.automation_url(job.id, brand_key, slot_list, videos_per_slot=vps)
        await self._jobs.update(
            job.id,
            status="running",
            phase="automation",
            message="Opening slideshow automation…",
            automation_url=url,
        )
        self._tasks[job.id] = asyncio.create_task(self._run_job(job.id))
        return {"job": (await self._jobs.get(job.id)).to_dict(), "automation_url": url}

    async def on_automation_done(self, job_id: str) -> dict[str, Any]:
        """Called by the slideshow UI browser when a video-generation job completes."""
        job = await self._jobs.get(job_id)
        if not job:
            raise RuntimeError(
                f"Unknown job {job_id} — the farm server may have restarted. "
                "Click Stop, then start a fresh run from the dashboard."
            )

        status = str(job.status).lower()
        if status == "completed":
            return job.to_dict()

        bad = self._slots_missing_valid_video(job)
        if bad:
            required = max(1, self._videos_per_slot(job))
            raise RuntimeError(
                f"Missing valid slideshow for slot(s): {', '.join(bad)} "
                f"(need {required} MP4(s) per slot) — remake required"
            )

        # Sub-jobs (run_batch=False) are created by _run_per_slot_pipeline.
        # Just mark them complete — the pipeline handles the batch itself.
        await self._jobs.update(
            job_id,
            status="completed",
            phase="done",
            message="Video ingested.",
        )
        updated = (await self._jobs.get(job_id)).to_dict()
        parent_id = str(updated.get("parent_job_id") or "").strip()
        if parent_id:
            parent = await self._jobs.get(parent_id)
            if parent and str(parent.status).lower() == "running":
                self._ensure_job_task(parent_id)
        return updated

    async def cancel_running_jobs(self) -> None:
        """Stop in-flight slideshow automation (Playwright) and mark jobs cancelled."""
        running = [
            job
            for job in await self._jobs.list_jobs(limit=50)
            if str(job.get("status") or "").lower() == "running"
        ]
        for job in running:
            await self.cancel_job(str(job.get("id") or ""))

    async def cancel_job(self, job_id: str) -> None:
        key = str(job_id or "").strip()
        if not key:
            return

        proc = self._procs.pop(key, None)
        if proc is not None and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

        task = self._tasks.get(key)
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.pop(key, None)

        job = await self._jobs.get(key)
        if job and str(job.status).lower() == "running":
            await self._jobs.update(
                key,
                status="failed",
                phase="automation",
                message="Stopped by user",
                error="Cancelled",
            )

    async def _finish_automation_if_needed(self, job_id: str) -> None:
        """Start ingest→batch if the browser finished but Vercel did not call automation-done."""
        job = await self._jobs.get(job_id)
        if not job:
            return
        if str(job.status).lower() in ("completed", "failed"):
            return
        if str(job.phase).lower() not in ("automation", "ingesting"):
            return
        bad = self._slots_missing_valid_video(job)
        if bad:
            await self._jobs.update(
                job_id,
                status="failed",
                phase="ingesting",
                error=f"Missing valid slideshow for slot(s): {', '.join(bad)}",
                message="Slideshow ingest incomplete after retries",
            )
            return
        try:
            await self.on_automation_done(job_id)
        except RuntimeError as exc:
            logger.warning("automation_done_fallback_skipped", job_id=job_id, error=str(exc))
        except Exception:
            logger.exception("automation_done_fallback_failed", job_id=job_id)

    def _expected_slides_for_brand(self, brand: str) -> int:
        """Labely scan MP4s contain shelf intro + product scans — not a single slide."""
        brand_key = str(brand or "labely").strip().lower()
        if brand_key == "labely":
            return 4
        return max(1, int(self._config.slides_per_slideshow))

    def _is_warmup_slot(self, slot: str, brand: str) -> bool:
        """Return True if this slot has warmup enabled for the given brand (no video needed)."""
        try:
            profile = get_profile_for_device("", slot, brand=brand)
            return bool(profile.get("warmup_enabled", False))
        except Exception:  # noqa: BLE001
            return False

    def _slot_has_valid_videos(self, slot: str, brand: str, *, job: Any | None = None) -> bool:
        """True when gallery already holds enough valid MP4s for this slot."""
        slot_key = str(slot).strip()
        brand_key = str(brand or "labely").strip().lower()
        if self._is_warmup_slot(slot_key, brand_key):
            return True
        min_count = max(1, self._videos_per_slot(job) if job else self._config.slideshows_per_slot)
        expected_slides = self._expected_slides_for_brand(brand_key)
        ok, _ = slot_gallery_status(
            self._app_config.gallery.base_directory,
            slot_key,
            list(self._app_config.gallery.media_extensions),
            min_count=min_count,
            expected_slides=expected_slides,
            brand=brand_key,
            prune_invalid=True,
        )
        return ok

    def _slots_missing_valid_video(self, job: Any) -> list[str]:
        extensions = list(self._app_config.gallery.media_extensions)
        min_count = max(1, self._videos_per_slot(job))
        expected_slides = self._expected_slides_for_brand(str(job.brand or "labely"))
        job_brand = str(job.brand or "labely")
        bad: list[str] = []
        for slot in job.slots:
            slot_key = str(slot)
            # Warmup-only slots don't post, so they don't need videos.
            if self._is_warmup_slot(slot_key, job_brand):
                continue
            ingested = len(job.ingested.get(slot_key, []))
            if ingested > 0 and ingested < min_count:
                bad.append(slot_key)
                continue
            ok, _ = slot_gallery_status(
                self._app_config.gallery.base_directory,
                slot,
                extensions,
                min_count=min_count,
                expected_slides=expected_slides,
                brand=job_brand,
                prune_invalid=True,
            )
            if not ok:
                bad.append(str(slot))
        return bad

    async def _run_playwright(self, job_id: str, url: str) -> tuple[int, str]:
        script = PROJECT_ROOT / "scripts" / "run_slideshow_automation.py"
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
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
            env=env,
        )
        self._procs[job_id] = proc
        try:
            stdout, stderr = await proc.communicate()
        finally:
            self._procs.pop(job_id, None)
        err = (stderr or stdout or b"").decode("utf-8", errors="replace")[:800]
        return int(proc.returncode or 0), err

    async def _wait_for_automation_phase(self, job_id: str) -> bool:
        """Wait until browser automation calls automation-done (phase leaves ingest)."""
        timeout = max(60.0, float(self._config.automation_timeout_seconds))
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            job = await self._jobs.get(job_id)
            if not job:
                return False
            status = str(job.status).lower()
            phase = str(job.phase).lower()
            if status == "failed":
                return False
            if phase in ("captions", "batch", "done") or status == "completed":
                return True
            await asyncio.sleep(2.0)
        await self._jobs.update(
            job_id,
            status="failed",
            phase="automation",
            error="Automation timed out",
            message="Slideshow automation timed out",
        )
        return False

    async def _wait_for_job_terminal(self, job_id: str) -> bool:
        """Wait until a slideshow job finishes (nested valcoin ingest job)."""
        timeout = max(60.0, float(self._config.automation_timeout_seconds))
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            job = await self._jobs.get(job_id)
            if not job:
                return False
            status = str(job.status).lower()
            if status == "failed":
                return False
            if status == "completed":
                return True
            await asyncio.sleep(2.0)
        await self._jobs.update(
            job_id,
            status="failed",
            phase="automation",
            error="Automation timed out",
            message="Slideshow automation timed out",
        )
        return False

    async def _run_embedded_automation(
        self,
        job_id: str,
        url: str,
        *,
        parent_job_id: str | None = None,
        attempt_message: str,
    ) -> bool:
        await self._jobs.update(
            job_id,
            automation_url=url,
            message=attempt_message,
        )
        if parent_job_id and parent_job_id != job_id:
            await self._jobs.update(
                parent_job_id,
                automation_url=url,
                message=attempt_message,
            )
        if parent_job_id and parent_job_id != job_id:
            return await self._wait_for_job_terminal(job_id)
        return await self._wait_for_automation_phase(job_id)

    async def _generate_brand_slideshows(
        self,
        brand: str,
        slots: list[str],
        *,
        parent_job_id: str | None = None,
    ) -> None:
        brand_key = str(brand or "labely").strip().lower()
        extra_job = await self._jobs.create(
            brand=brand_key,
            slots=[str(s).strip() for s in slots if str(s).strip()],
            run_batch=False,
            videos_per_slot=max(1, int(self._config.slideshows_per_slot)),
            parent_job_id=str(parent_job_id or "").strip(),
        )
        await self._jobs.update(
            extra_job.id,
            status="running",
            phase="automation",
            message=f"Generating {brand_key} slideshows…",
        )
        ok = await self._execute_slideshow_generation(extra_job.id, parent_job_id=parent_job_id)
        if not ok:
            raise RuntimeError(f"{brand_key} slideshow generation failed")

    async def _execute_slideshow_generation(
        self,
        job_id: str,
        *,
        parent_job_id: str | None = None,
    ) -> bool:
        job = await self._jobs.get(job_id)
        if not job:
            return False
        script = PROJECT_ROOT / "scripts" / "run_slideshow_automation.py"
        use_embedded = bool(self._config.use_embedded_runner)
        use_playwright = bool(self._config.use_playwright_runner and script.is_file())
        if not use_embedded and not use_playwright:
            url = self.automation_url(
                job.id,
                job.brand,
                list(job.slots),
                videos_per_slot=self._videos_per_slot(job),
            )
            await self._jobs.update(
                job_id,
                automation_url=url,
                message="Open automation URL in browser (no runner enabled).",
            )
            return False

        slots_to_run = list(job.slots)
        max_retries = max(0, int(self._config.blank_video_max_retries))
        for attempt in range(max_retries + 1):
            vps = self._videos_per_slot(job)
            url = self.automation_url(job.id, job.brand, slots_to_run, videos_per_slot=vps)
            if attempt == 0:
                attempt_message = (
                    f"Generating {job.brand} slideshows in dashboard…"
                    if use_embedded
                    else f"Playwright automation runner started ({job.brand})…"
                )
            else:
                attempt_message = (
                    f"Remaking {job.brand} slideshow for slot(s) {', '.join(slots_to_run)} "
                    f"(attempt {attempt + 1}/{max_retries + 1})…"
                )

            if use_embedded:
                ok = await self._run_embedded_automation(
                    job_id,
                    url,
                    parent_job_id=parent_job_id,
                    attempt_message=attempt_message,
                )
            else:
                await self._jobs.update(job_id, message=attempt_message)
                returncode, err = await self._run_playwright(job_id, url)
                if returncode != 0:
                    current = await self._jobs.get(job_id)
                    if current and str(current.error or "").lower() == "cancelled":
                        return False
                    await self._jobs.update(
                        job_id,
                        status="failed",
                        phase="automation",
                        error=err or f"Automation exited {returncode}",
                    )
                    return False
                ok = True

            if not ok:
                current = await self._jobs.get(job_id)
                if current and str(current.error or "").lower() in ("cancelled",):
                    return False
                return False

            current = await self._jobs.get(job_id)
            if not current:
                return False
            if use_embedded and str(current.status).lower() == "completed":
                return True
            if use_embedded and str(current.phase).lower() in ("captions", "batch", "done"):
                return True

            await asyncio.sleep(3)
            current = await self._jobs.get(job_id)
            if not current:
                return False
            bad = self._slots_missing_valid_video(current)
            if not bad:
                return True
            if attempt >= max_retries:
                await self._jobs.update(
                    job_id,
                    status="failed",
                    phase="ingesting",
                    error=f"Missing valid slideshow for slot(s): {', '.join(bad)}",
                    message="Blank or missing videos after all remake attempts",
                )
                return False

            extensions = list(self._app_config.gallery.media_extensions)
            for slot in bad:
                clear_slot_media(
                    self._app_config.gallery.base_directory,
                    slot,
                    extensions,
                    brand=str(job.brand or "labely"),
                )
                await self._jobs.clear_slot_ingest(job_id, slot)
            slots_to_run = bad
            if use_embedded:
                await self._jobs.update(
                    job_id,
                    status="running",
                    phase="automation",
                    error="",
                )
                if parent_job_id:
                    await self._jobs.update(
                        parent_job_id,
                        status="running",
                        phase="automation",
                        error="",
                    )
        return False

    async def _generate_captions_for_slot(
        self,
        job_id: str,
        device: Any,
        *,
        brand: str,
        slot_index: int,
        slot_total: int,
    ) -> bool:
        """Generate AI captions for one phone after its gallery video exists."""
        if not self._config.auto_generate_captions:
            return True

        slot = str(device.user_name)
        brand_key = str(brand or "labely").strip().lower()
        await self._jobs.update(
            job_id,
            phase="captions",
            message=(
                f"Phone {slot_index}/{slot_total}: generating {brand_key} captions for {slot}…"
            ),
        )
        caption_result = await generate_captions_for_devices(
            self._app_config,
            [device],
            onscreen_template=default_onscreen_template_for_brand(
                brand_key, self._config.default_onscreen_template
            ),
            brand=brand_key,
        )
        if caption_result["generated"] > 0:
            return True

        detail = (
            caption_result["errors"][0]["error"]
            if caption_result["errors"]
            else "No captions generated"
        )
        logger.warning(
            "per_slot_caption_failed",
            slot=slot,
            brand=brand_key,
            error=detail,
        )
        await self._jobs.update(
            job_id,
            message=(
                f"Phone {slot_index}/{slot_total}: caption generation failed for {slot} — {detail}"
            ),
        )
        return False

    async def _run_per_slot_pipeline(self, job_id: str) -> None:
        """
        Per-slot pipeline: for each phone, encode one video → run batch → next phone.
        Keeps WebCodecs encoder from being overwhelmed by parallel encoding jobs.
        """
        job = await self._jobs.get(job_id)
        if not job:
            return

        devices = farm_devices_sorted(self._device_manager)
        wanted = {str(s) for s in job.slots}
        selected = [d for d in devices if str(d.user_name) in wanted]

        if not selected:
            await self._jobs.update(
                job_id, status="failed", error="No online farm phones matched job slots"
            )
            return

        if self._farm_batch.is_running():
            await self._jobs.update(
                job_id, status="failed", error="Farm batch already running"
            )
            return

        chain_valcoin = (
            job.brand == "labely"
            and self._app_config.batch.chain_valcoin_after_labely
        )
        completed = 0
        total = len(selected)

        for idx, device in enumerate(selected, 1):
            slot = str(device.user_name)

            # Step 1 — encode video for this slot only (skip if gallery already ready).
            if self._slot_has_valid_videos(slot, job.brand, job=job):
                await self._jobs.update(
                    job_id,
                    phase="automation",
                    message=f"Phone {idx}/{total}: videos ready for {slot}, skipping encode…",
                )
                ok = True
            else:
                await self._jobs.update(
                    job_id,
                    phase="automation",
                    message=f"Phone {idx}/{total}: encoding video for {slot}…",
                )
                sub_job = await self._jobs.create(
                    brand=job.brand,
                    slots=[slot],
                    run_batch=False,
                    videos_per_slot=int(job.videos_per_slot or 0),
                    parent_job_id=job_id,
                )
                await self._jobs.update(sub_job.id, status="running", phase="automation", message=f"Encoding {slot}…")

                ok = await self._execute_slideshow_generation(sub_job.id, parent_job_id=job_id)

                # Clear the iframe so the WebCodecs encoder is fully released before the
                # next slot loads. Give the browser ~4 s to GC the previous encoding session.
                await self._jobs.update(job_id, automation_url="")
                await asyncio.sleep(4.0)

            if not ok:
                logger.warning("per_slot_video_failed", slot=slot)
                await self._jobs.update(job_id, message=f"Phone {idx}/{total}: video failed for {slot}, skipping…")
                continue

            # Step 2 — captions need gallery MP4s from step 1.
            run_valcoin_encode = (
                chain_valcoin and not self._is_warmup_slot(slot, "valcoin")
            )
            valcoin_encode_task: asyncio.Task[None] | None = None
            if run_valcoin_encode:
                await self._jobs.update(
                    job_id,
                    message=f"Phone {idx}/{total}: generating ValCoin video for {slot}…",
                )
                valcoin_encode_task = asyncio.create_task(
                    self._generate_brand_slideshows(
                        "valcoin", [slot], parent_job_id=job_id
                    )
                )

            if not await self._generate_captions_for_slot(
                job_id,
                device,
                brand=job.brand,
                slot_index=idx,
                slot_total=total,
            ):
                if valcoin_encode_task is not None:
                    valcoin_encode_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await valcoin_encode_task
                continue

            if valcoin_encode_task is not None:
                try:
                    await valcoin_encode_task
                except RuntimeError as exc:
                    logger.warning("valcoin_slideshow_failed", slot=slot, error=str(exc))
                    continue
                if not await self._generate_captions_for_slot(
                    job_id,
                    device,
                    brand="valcoin",
                    slot_index=idx,
                    slot_total=total,
                ):
                    continue

            # Step 3 — run batch for this slot.
            await self._jobs.update(
                job_id,
                phase="batch",
                message=f"Phone {idx}/{total}: posting for {slot}…",
            )
            started = await self._farm_batch.start([device], brand=job.brand)
            if started:
                await self._farm_batch.wait_done()
            else:
                logger.warning("per_slot_batch_not_started", slot=slot)
            completed += 1

        await self._jobs.update(
            job_id,
            status="completed",
            phase="done",
            message=f"Done — {completed}/{total} phone(s) processed.",
        )

    async def _run_job(self, job_id: str) -> None:
        job = await self._jobs.get(job_id)
        if not job:
            return

        try:
            if job.run_batch:
                # Per-slot: encode video → batch → next phone.
                await self._run_per_slot_pipeline(job_id)
            else:
                # Video-only: generate all slots at once (no batch to run).
                ok = await self._execute_slideshow_generation(job_id)
                if not ok:
                    return
                await self._finish_automation_if_needed(job_id)
        except Exception as exc:
            logger.exception("slideshow_job_failed", job_id=job_id)
            await self._jobs.update(
                job_id,
                status="failed",
                phase="automation",
                error=str(exc),
            )
        finally:
            self._tasks.pop(job_id, None)
