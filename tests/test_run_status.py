"""Tests for unified daily-run progress."""

from __future__ import annotations

from imouse_farm.dashboard.run_status import compute_run_progress


def test_stopped_batch_is_not_active() -> None:
    progress = compute_run_progress(
        slideshow_job=None,
        batch={"status": "stopped", "message": "Batch run stopped"},
    )
    assert progress["active"] is False
    assert progress["phase"] == "idle"


def test_idle_batch_with_no_job_is_not_active() -> None:
    progress = compute_run_progress(
        slideshow_job=None,
        batch={"status": "idle"},
    )
    assert progress["active"] is False
    assert progress["phase"] == "idle"


def test_running_batch_is_active() -> None:
    progress = compute_run_progress(
        slideshow_job=None,
        batch={"status": "running", "batch_index": 1, "batch_total": 2},
    )
    assert progress["active"] is True
    assert progress["phase"] == "batch"


def test_running_slideshow_automation_is_active() -> None:
    progress = compute_run_progress(
        slideshow_job={"status": "running", "phase": "automation"},
        batch={"status": "idle"},
    )
    assert progress["active"] is True
    assert progress["phase"] == "slideshow"


def test_failed_slideshow_job_is_not_active() -> None:
    progress = compute_run_progress(
        slideshow_job={"status": "failed", "phase": "automation", "error": "boom"},
        batch={"status": "idle"},
    )
    assert progress["active"] is False
    assert progress["phase"] == "failed"


def test_completed_batch_shows_one_hundred_percent() -> None:
    progress = compute_run_progress(
        slideshow_job={"status": "completed", "phase": "done", "run_batch": True},
        batch={"status": "completed", "message": "Batch run finished — 1 ok, 0 failed"},
    )
    assert progress["progress"] == 100
    assert progress["phase"] == "complete"


def test_completed_job_with_idle_batch_is_interrupted_not_complete() -> None:
    progress = compute_run_progress(
        slideshow_job={"status": "completed", "phase": "done", "run_batch": True},
        batch={"status": "idle", "message": "Batch run stopped"},
    )
    assert progress["phase"] == "idle"
    assert progress["phase_label"] == "Interrupted"
    assert progress["progress"] == 0


def test_completed_ingest_only_job_with_idle_batch_is_complete() -> None:
    progress = compute_run_progress(
        slideshow_job={
            "status": "completed",
            "phase": "done",
            "run_batch": False,
            "message": "Ingest complete (batch run skipped).",
        },
        batch={"status": "idle"},
    )
    assert progress["progress"] == 100
    assert progress["phase"] == "complete"
