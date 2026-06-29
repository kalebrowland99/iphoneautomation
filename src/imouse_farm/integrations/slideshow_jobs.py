"""In-memory slideshow → farm pipeline job tracking."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SlideshowJob:
    id: str
    brand: str
    slots: list[str]
    status: str = "pending"
    phase: str = "queued"
    message: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    ingested: dict[str, list[str]] = field(default_factory=dict)
    run_batch: bool = True
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "brand": self.brand,
            "slots": self.slots,
            "status": self.status,
            "phase": self.phase,
            "message": self.message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ingested": self.ingested,
            "run_batch": self.run_batch,
            "error": self.error,
        }


class SlideshowJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, SlideshowJob] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        *,
        brand: str,
        slots: list[str],
        run_batch: bool = True,
    ) -> SlideshowJob:
        job = SlideshowJob(
            id=uuid.uuid4().hex[:12],
            brand=str(brand or "labely").strip().lower(),
            slots=[str(s).strip() for s in slots if str(s).strip()],
            run_batch=bool(run_batch),
        )
        async with self._lock:
            self._jobs[job.id] = job
        return job

    async def get(self, job_id: str) -> SlideshowJob | None:
        async with self._lock:
            job = self._jobs.get(str(job_id or "").strip())
            return job

    async def update(self, job_id: str, **fields: Any) -> SlideshowJob | None:
        async with self._lock:
            job = self._jobs.get(str(job_id or "").strip())
            if not job:
                return None
            for key, value in fields.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            job.updated_at = _now_iso()
            return job

    async def record_ingest(
        self,
        job_id: str,
        slot: str,
        filename: str,
    ) -> SlideshowJob | None:
        async with self._lock:
            job = self._jobs.get(str(job_id or "").strip())
            if not job:
                return None
            slot_key = str(slot).strip()
            files = list(job.ingested.get(slot_key, []))
            files.append(str(filename))
            job.ingested[slot_key] = files
            job.phase = "ingesting"
            job.status = "running"
            job.message = f"Ingested {filename} → slot {slot_key}"
            job.updated_at = _now_iso()
            return job

    async def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        async with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda j: j.updated_at,
                reverse=True,
            )
            return [j.to_dict() for j in jobs[: max(1, limit)]]
