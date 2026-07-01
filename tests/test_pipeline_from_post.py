"""Tests for pipeline start-from-post selection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from imouse_farm.workflows.pipeline import (
    TIKTOK_FULL_PIPELINE,
    TIKTOK_LABELY_THEN_VALCOIN_STEPS,
    TIKTOK_POST_END_PIPELINE,
    WorkflowPipeline,
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
