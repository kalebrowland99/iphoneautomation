"""Unified daily-run progress for the dashboard."""

from __future__ import annotations

from typing import Any

_ACTIVE_BATCH_STATUSES = frozenset({"connecting", "running", "disconnecting"})
_ACTIVE_JOB_PHASES = frozenset({"automation", "ingesting", "captions", "batch"})


def _run_is_active(batch_status: str, job_status: str, job_phase: str) -> bool:
    if batch_status in _ACTIVE_BATCH_STATUSES:
        return True
    return job_status == "running" and job_phase in _ACTIVE_JOB_PHASES


def compute_run_progress(
    *,
    slideshow_job: dict[str, Any] | None,
    batch: dict[str, Any],
) -> dict[str, Any]:
    """Map slideshow job + batch state to a single progress bar + phase label."""
    batch_status = str(batch.get("status") or "idle").lower()
    job = slideshow_job or {}
    job_status = str(job.get("status") or "").lower()
    job_phase = str(job.get("phase") or "").lower()
    message = str(job.get("message") or batch.get("message") or "").strip()

    if job_status == "failed":
        return {
            "phase": "failed",
            "phase_label": "Failed",
            "progress": 0,
            "message": str(job.get("error") or message or "Run failed"),
            "active": False,
        }

    if job_status == "running":
        if job_phase == "automation":
            return {
                "phase": "slideshow",
                "phase_label": "Generating slideshows",
                "progress": 22,
                "message": message or "Chrome automation running…",
                "active": True,
            }
        if job_phase == "ingesting":
            ingested = job.get("ingested") or {}
            slots = len(ingested) if isinstance(ingested, dict) else 0
            pct = min(52, 38 + slots * 2)
            return {
                "phase": "ingest",
                "phase_label": "Uploading videos",
                "progress": pct,
                "message": message or "Ingesting MP4s to gallery…",
                "active": True,
            }
        if job_phase == "captions":
            return {
                "phase": "captions",
                "phase_label": "Writing captions",
                "progress": 58,
                "message": message or "Generating AI captions…",
                "active": True,
            }
        if job_phase in ("batch", "done"):
            pass  # fall through to batch metrics

    if batch_status in ("connecting", "running", "disconnecting"):
        idx = int(batch.get("batch_index") or 0)
        total = max(1, int(batch.get("batch_total") or 1))
        completed = len(batch.get("completed") or [])
        frac = min(1.0, (idx + completed * 0.25) / total)
        pct = 62 + int(frac * 36)
        return {
            "phase": "batch",
            "phase_label": "Posting on phones",
            "progress": min(98, pct),
            "message": message or f"Batch {idx}/{total}",
            "active": True,
        }

    if batch_status == "completed":
        return {
            "phase": "complete",
            "phase_label": "Complete",
            "progress": 100,
            "message": message or "Daily run finished",
            "active": False,
        }

    if batch_status == "stopped":
        return {
            "phase": "idle",
            "phase_label": "Stopped",
            "progress": 0,
            "message": message or "Run stopped",
            "active": False,
        }

    if job_status == "completed" and batch_status == "idle":
        # Ingest-only runs never start a batch; slideshow-only jobs finish here.
        if job.get("run_batch") is False:
            return {
                "phase": "complete",
                "phase_label": "Complete",
                "progress": 100,
                "message": message or "Ingest finished",
                "active": False,
            }
        return {
            "phase": "idle",
            "phase_label": "Interrupted",
            "progress": 0,
            "message": message or "Batch did not finish — start a fresh run",
            "active": False,
        }

    if batch_status == "idle" and not job:
        return {
            "phase": "idle",
            "phase_label": "Ready",
            "progress": 0,
            "message": "Select phones and click Generate & Run",
            "active": False,
        }

    return {
        "phase": job_phase or batch_status or "idle",
        "phase_label": job_phase.title() if job_phase else "Running",
        "progress": 12,
        "message": message or "Working…",
        "active": _run_is_active(batch_status, job_status, job_phase),
    }
