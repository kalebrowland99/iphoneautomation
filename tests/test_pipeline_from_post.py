"""Tests for pipeline start-from-post selection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.workflows.pipeline import (
    TIKTOK_FULL_PIPELINE,
    TIKTOK_LABELY_THEN_VALCOIN_STEPS,
    TIKTOK_POST_END_PIPELINE,
    WorkflowPipeline,
    _build_steps,
)


@pytest.mark.asyncio
async def test_start_without_from_post_runs_full_pipeline() -> None:
    engine = MagicMock()
    engine.list_running.return_value = []
    engine.start_workflow = AsyncMock(return_value=True)
    db = MagicMock()
    db.log_activity = AsyncMock()
    pipe = WorkflowPipeline(engine, MagicMock(), db)

    assert await pipe.start("dev-1") is True

    engine.start_workflow.assert_awaited_once_with("tiktok_prep", "dev-1", brand="labely")
    assert pipe._pipelines["dev-1"]["workflows"] == list(TIKTOK_FULL_PIPELINE)
    assert len(pipe._pipelines["dev-1"]["workflows"]) == 4
    assert pipe._pipelines["dev-1"]["from_post"] is None


@pytest.mark.asyncio
async def test_start_labely_chains_valcoin_after_three_posts() -> None:
    engine = MagicMock()
    engine.list_running.return_value = []
    engine.start_workflow = AsyncMock(return_value=True)
    db = MagicMock()
    db.log_activity = AsyncMock()
    pipe = WorkflowPipeline(engine, MagicMock(), db)

    assert await pipe.start("dev-1", brand="labely", chain_valcoin_after_labely=True) is True

    engine.start_workflow.assert_awaited_once_with("tiktok_prep", "dev-1", brand="labely")
    assert len(pipe._pipelines["dev-1"]["steps"]) == len(TIKTOK_LABELY_THEN_VALCOIN_STEPS)
    assert pipe._pipelines["dev-1"]["steps"][4]["brand"] == "valcoin"
    assert pipe._pipelines["dev-1"]["steps"][4]["workflow"] == "tiktok_account_switch"
    assert pipe._pipelines["dev-1"]["steps"][3]["workflow"] == "tiktok_valcoin_prep"


@pytest.mark.asyncio
async def test_start_from_post_1_skips_prep() -> None:
    engine = MagicMock()
    engine.list_running.return_value = []
    engine.start_workflow = AsyncMock(return_value=True)
    db = MagicMock()
    db.log_activity = AsyncMock()
    pipe = WorkflowPipeline(engine, MagicMock(), db)

    assert await pipe.start("dev-1", from_post=1) is True

    engine.start_workflow.assert_awaited_once_with("tiktok_account_switch", "dev-1", brand="labely")
    assert pipe._pipelines["dev-1"]["workflows"] == list(TIKTOK_POST_END_PIPELINE)
    assert len(pipe._pipelines["dev-1"]["workflows"]) == 3
    assert pipe._pipelines["dev-1"]["from_post"] == 1


@pytest.mark.asyncio
async def test_start_from_post_3_skips_prep() -> None:
    engine = MagicMock()
    engine.list_running.return_value = []
    engine.start_workflow = AsyncMock(return_value=True)
    db = MagicMock()
    db.log_activity = AsyncMock()
    pipe = WorkflowPipeline(engine, MagicMock(), db)

    assert await pipe.start("dev-1", from_post=3) is True

    engine.start_workflow.assert_awaited_once_with("tiktok_account_switch", "dev-1", brand="labely")
    assert pipe._pipelines["dev-1"]["workflows"] == list(TIKTOK_POST_END_PIPELINE)
    assert len(pipe._pipelines["dev-1"]["workflows"]) == 3
    assert pipe._pipelines["dev-1"]["from_post"] == 3


def test_build_steps_skips_labely_prep_when_flagged() -> None:
    steps = _build_steps(
        from_post=None,
        brand="labely",
        chain_valcoin_after_labely=False,
        skip_prep_brands=frozenset({"labely"}),
    )
    assert steps[0]["workflow"] == "tiktok_account_switch"
    assert all(s["workflow"] != "tiktok_prep" for s in steps)


def test_build_steps_omits_labely_end_before_valcoin_warmup() -> None:
    steps = _build_steps(
        from_post=None,
        brand="labely",
        chain_valcoin_after_labely=False,
        skip_labely_end_for_valcoin_warmup=True,
    )
    workflows = [s["workflow"] for s in steps]
    assert workflows == [
        "tiktok_prep",
        "tiktok_account_switch",
        "tiktok_post",
    ]
    assert "tiktok_end" not in workflows


@pytest.mark.asyncio
async def test_start_skips_prep_when_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = MagicMock()
    engine.list_running.return_value = []
    engine.start_workflow = AsyncMock(return_value=True)
    db = MagicMock()
    db.log_activity = AsyncMock()
    dm = MagicMock()
    dm.get_device.return_value = MagicMock(user_name="2")
    monkeypatch.setattr(
        "imouse_farm.workflows.pipeline.is_prep_valid",
        lambda _key, *, brand: brand == "labely",
    )
    pipe = WorkflowPipeline(engine, dm, db)

    assert await pipe.start("dev-1", skip_prep_when_valid=True) is True

    engine.start_workflow.assert_awaited_once_with(
        "tiktok_account_switch", "dev-1", brand="labely"
    )
    assert pipe._pipelines["dev-1"]["workflows"][0] == "tiktok_account_switch"
    assert "tiktok_prep" not in pipe._pipelines["dev-1"]["workflows"]
