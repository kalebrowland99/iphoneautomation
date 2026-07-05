"""Slideshow → farm pipeline job tracking (persisted under data/)."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
JOBS_FILE = PROJECT_ROOT / "data" / "slideshow_jobs.json"


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
    rejected: dict[str, int] = field(default_factory=dict)
    run_batch: bool = True
    videos_per_slot: int = 0  # 0 = use slideshow.slideshows_per_slot from config
    automation_url: str = ""
    error: str = ""
    parent_job_id: str = ""
    # Labely jobs: slots also ticked on the ValCoin brand batch picker (full post after Labely).
    valcoin_slots: list[str] = field(default_factory=list)

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
            "rejected": self.rejected,
            "run_batch": self.run_batch,
            "videos_per_slot": self.videos_per_slot,
            "automation_url": self.automation_url,
            "error": self.error,
            "parent_job_id": self.parent_job_id,
            "valcoin_slots": list(self.valcoin_slots),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SlideshowJob:
        return cls(
            id=str(data.get("id") or ""),
            brand=str(data.get("brand") or "labely"),
            slots=[str(s).strip() for s in (data.get("slots") or []) if str(s).strip()],
            status=str(data.get("status") or "pending"),
            phase=str(data.get("phase") or "queued"),
            message=str(data.get("message") or ""),
            created_at=str(data.get("created_at") or _now_iso()),
            updated_at=str(data.get("updated_at") or _now_iso()),
            ingested={
                str(k): [str(f) for f in (v or [])]
                for k, v in (data.get("ingested") or {}).items()
            },
            rejected={
                str(k): int(v or 0)
                for k, v in (data.get("rejected") or {}).items()
            },
            run_batch=bool(data.get("run_batch", True)),
            videos_per_slot=max(0, int(data.get("videos_per_slot") or 0)),
            automation_url=str(data.get("automation_url") or ""),
            error=str(data.get("error") or ""),
            parent_job_id=str(data.get("parent_job_id") or ""),
            valcoin_slots=[
                str(s).strip()
                for s in (data.get("valcoin_slots") or [])
                if str(s).strip()
            ],
        )


class SlideshowJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, SlideshowJob] = {}
        self._lock = asyncio.Lock()
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        try:
            raw = JOBS_FILE.read_text(encoding="utf-8")
            payload = json.loads(raw)
            rows = payload.get("jobs") if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                return
            for row in rows:
                if not isinstance(row, dict) or not row.get("id"):
                    continue
                job = SlideshowJob.from_dict(row)
                if job.id:
                    self._jobs[job.id] = job
        except FileNotFoundError:
            return
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return

    async def _persist_unlocked(self) -> None:
        JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {"jobs": [job.to_dict() for job in self._jobs.values()]}
        JOBS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    async def _persist(self) -> None:
        async with self._lock:
            await self._persist_unlocked()

    async def create(
        self,
        *,
        brand: str,
        slots: list[str],
        run_batch: bool = True,
        videos_per_slot: int = 0,
        parent_job_id: str = "",
        valcoin_slots: list[str] | None = None,
    ) -> SlideshowJob:
        job = SlideshowJob(
            id=uuid.uuid4().hex[:12],
            brand=str(brand or "labely").strip().lower(),
            slots=[str(s).strip() for s in slots if str(s).strip()],
            run_batch=bool(run_batch),
            videos_per_slot=max(0, int(videos_per_slot)),
            parent_job_id=str(parent_job_id or "").strip(),
            valcoin_slots=[
                str(s).strip()
                for s in (valcoin_slots or [])
                if str(s).strip()
            ],
        )
        async with self._lock:
            self._jobs[job.id] = job
            await self._persist_unlocked()
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
            await self._persist_unlocked()
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
            await self._persist_unlocked()
            return job

    async def record_reject(
        self,
        job_id: str,
        slot: str,
        reason: str,
    ) -> SlideshowJob | None:
        async with self._lock:
            job = self._jobs.get(str(job_id or "").strip())
            if not job:
                return None
            slot_key = str(slot).strip()
            job.rejected[slot_key] = int(job.rejected.get(slot_key, 0)) + 1
            job.phase = "ingesting"
            job.status = "running"
            job.message = f"Rejected bad video for slot {slot_key} — remake requested ({reason})"
            job.updated_at = _now_iso()
            await self._persist_unlocked()
            return job

    async def clear_slot_ingest(self, job_id: str, slot: str) -> SlideshowJob | None:
        async with self._lock:
            job = self._jobs.get(str(job_id or "").strip())
            if not job:
                return None
            slot_key = str(slot).strip()
            job.ingested.pop(slot_key, None)
            job.updated_at = _now_iso()
            await self._persist_unlocked()
            return job

    async def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        async with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda j: j.updated_at,
                reverse=True,
            )
            return [j.to_dict() for j in jobs[: max(1, limit)]]
