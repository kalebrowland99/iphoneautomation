"""Chain prep → post → end workflows for full production runs."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from imouse_farm.database.repository import DatabaseRepository
from imouse_farm.devices.manager import DeviceManager
from imouse_farm.permissions.watcher import PermissionWatcherManager
from imouse_farm.post.account_profile_store import is_prep_valid, mark_prep_completed
from imouse_farm.post.brand_keys import device_storage_key
from imouse_farm.post.post_caption_store import POST_COUNT
from imouse_farm.settings.run_settings import get_use_supplied_videos
from imouse_farm.utils.logging import get_logger
from imouse_farm.workflows.engine import WorkflowEngine

logger = get_logger(__name__)

PipelineStep = dict[str, str]


def _step(workflow: str, brand: str) -> PipelineStep:
    return {"workflow": workflow, "brand": brand}


def _workflow_names(steps: list[PipelineStep]) -> tuple[str, ...]:
    return tuple(s["workflow"] for s in steps)


TIKTOK_FULL_PIPELINE_STEPS: list[PipelineStep] = [
    _step("tiktok_prep", "labely"),
    _step("tiktok_account_switch", "labely"),
    _step("tiktok_post", "labely"),
    _step("tiktok_end", "labely"),
]

TIKTOK_LABELY_THEN_VALCOIN_STEPS: list[PipelineStep] = [
    _step("tiktok_prep", "labely"),
    _step("tiktok_account_switch", "labely"),
    _step("tiktok_post", "labely"),
    _step("tiktok_valcoin_prep", "valcoin"),
    _step("tiktok_account_switch", "valcoin"),
    _step("tiktok_post", "valcoin"),
    _step("tiktok_end", "valcoin"),
]

TIKTOK_FULL_PIPELINE = _workflow_names(TIKTOK_FULL_PIPELINE_STEPS)
TIKTOK_POST_END_PIPELINE = _workflow_names(
    [
        _step("tiktok_account_switch", "labely"),
        _step("tiktok_post", "labely"),
        _step("tiktok_end", "labely"),
    ]
)

EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


_PREP_WORKFLOWS = frozenset({"tiktok_prep", "tiktok_valcoin_prep"})


def _build_steps(
    *,
    from_post: int | None,
    brand: str,
    chain_valcoin_after_labely: bool,
    skip_prep_brands: frozenset[str] = frozenset(),
    skip_labely_end_for_valcoin_warmup: bool = False,
) -> list[PipelineStep]:
    run_brand = str(brand or "labely").strip().lower()
    if from_post is not None:
        steps = [
            _step("tiktok_account_switch", run_brand),
            _step("tiktok_post", run_brand),
            _step("tiktok_end", run_brand),
        ]
    elif run_brand == "labely" and chain_valcoin_after_labely:
        steps = list(TIKTOK_LABELY_THEN_VALCOIN_STEPS)
    else:
        steps = [
            _step("tiktok_prep", run_brand),
            _step("tiktok_account_switch", run_brand),
            _step("tiktok_post", run_brand),
        ]
        if not (run_brand == "labely" and skip_labely_end_for_valcoin_warmup):
            steps.append(_step("tiktok_end", run_brand))
    if skip_prep_brands:
        steps = [
            s
            for s in steps
            if not (
                s["workflow"] in _PREP_WORKFLOWS and s["brand"] in skip_prep_brands
            )
        ]
    if not steps:
        raise ValueError("pipeline has no steps after prep skip")
    return steps


def _post_start_for_step(pipe: dict[str, Any], step_index: int) -> int | None:
    step = pipe["steps"][step_index]
    if step["workflow"] != "tiktok_post":
        return None
    from_post = pipe.get("from_post")
    if from_post is None:
        return 1
    for i in range(step_index):
        if pipe["steps"][i]["workflow"] == "tiktok_post":
            return 1
    return from_post


class WorkflowPipeline:
    """Run tiktok_prep → tiktok_post → tiktok_end sequentially on one device."""

    def __init__(
        self,
        workflow_engine: WorkflowEngine,
        device_manager: DeviceManager,
        db: DatabaseRepository,
        *,
        permission_watchers: PermissionWatcherManager | None = None,
    ) -> None:
        self._engine = workflow_engine
        self._dm = device_manager
        self._db = db
        self._permission_watchers = permission_watchers
        self._pipelines: dict[str, dict[str, Any]] = {}
        self._event_callbacks: list[EventCallback] = []
        self._engine.on_event(self._on_workflow_event)

    def on_event(self, callback: EventCallback) -> None:
        self._event_callbacks.append(callback)

    async def _emit(self, event: str, data: dict[str, Any]) -> None:
        for cb in self._event_callbacks:
            try:
                await cb(event, data)
            except Exception as exc:
                logger.error("pipeline_event_failed", error=str(exc))

    def get_status(self, device_id: str) -> dict[str, Any] | None:
        pipe = self._pipelines.get(device_id)
        if not pipe:
            return None
        steps = pipe["steps"]
        index = pipe["index"]
        current = steps[index] if index < len(steps) else None
        workflow_names = [s["workflow"] for s in steps]
        return {
            "status": pipe["status"],
            "current_workflow": current["workflow"] if current else None,
            "step": index + 1,
            "total_steps": len(steps),
            "workflows": workflow_names,
            "brand": current["brand"] if current else pipe.get("brand", "labely"),
        }

    def is_active(self, device_id: str) -> bool:
        pipe = self._pipelines.get(device_id)
        return bool(pipe and pipe["status"] in ("running", "paused"))

    async def start(
        self,
        device_id: str,
        *,
        from_post: int | None = None,
        brand: str = "labely",
        chain_valcoin_after_labely: bool = False,
        skip_prep_when_valid: bool = True,
        skip_labely_end_for_valcoin_warmup: bool = False,
    ) -> bool:
        if self.is_active(device_id):
            return False
        if self._engine.list_running():
            for entry in self._engine.list_running():
                if entry["device_id"] == device_id:
                    return False

        if from_post is not None and not (1 <= from_post <= POST_COUNT):
            return False

        if self._permission_watchers:
            await self._permission_watchers.ensure_watching(device_id)

        run_brand = str(brand or "labely").strip().lower()
        skip_prep_brands: frozenset[str] = frozenset()
        # Use my videos still needs clear+upload (+ VPN off inside clear_album).
        # Never skip prep when that toggle is on, even if prep looked valid.
        if (
            from_post is None
            and skip_prep_when_valid
            and not get_use_supplied_videos(run_brand)
        ):
            device = self._dm.get_device(device_id)
            if device:
                storage_key = device_storage_key(device_id, device.user_name)
                if is_prep_valid(storage_key, brand=run_brand):
                    skip_prep_brands = frozenset({run_brand})
        steps = _build_steps(
            from_post=from_post,
            brand=run_brand,
            chain_valcoin_after_labely=chain_valcoin_after_labely,
            skip_prep_brands=skip_prep_brands,
            skip_labely_end_for_valcoin_warmup=skip_labely_end_for_valcoin_warmup,
        )
        first = steps[0]
        self._pipelines[device_id] = {
            "steps": steps,
            "workflows": [s["workflow"] for s in steps],
            "index": 0,
            "status": "running",
            "from_post": from_post,
            "brand": run_brand,
            "chain_valcoin": chain_valcoin_after_labely,
        }
        started = await self._start_step(device_id, 0)
        if not started:
            self._pipelines.pop(device_id, None)
            return False

        workflow_names = [s["workflow"] for s in steps]
        if from_post is None:
            if skip_prep_brands:
                label = (
                    f"Full run ({' → '.join(workflow_names)}) — "
                    f"skipped {run_brand} prep (gallery still on device)"
                )
            elif chain_valcoin_after_labely and run_brand == "labely":
                label = "Labely + ValCoin run (prep → Labely posts → clear → ValCoin upload → ValCoin posts → end)"
            else:
                label = f"Full run ({' → '.join(workflow_names)})"
        else:
            label = f"Posts {from_post}→{POST_COUNT} + end ({first['workflow']})"
        await self._db.log_activity(
            "info",
            "pipeline",
            label,
            device_id,
            {
                "pipeline": workflow_names,
                "from_post": from_post,
                "chain_valcoin": chain_valcoin_after_labely,
                "source": "dashboard",
            },
        )
        await self._emit(
            "pipeline_started",
            {
                "device_id": device_id,
                "workflows": workflow_names,
                "from_post": from_post,
                "brand": run_brand,
                "chain_valcoin": chain_valcoin_after_labely,
            },
        )
        return True

    async def _start_step(self, device_id: str, step_index: int) -> bool:
        pipe = self._pipelines.get(device_id)
        if not pipe:
            return False
        step = pipe["steps"][step_index]
        workflow = step["workflow"]
        step_brand = step["brand"]
        start_post_index = _post_start_for_step(pipe, step_index)
        if workflow == "tiktok_post":
            return await self._engine.start_workflow(
                workflow,
                device_id,
                start_post_index=start_post_index,
                brand=step_brand,
            )
        return await self._engine.start_workflow(workflow, device_id, brand=step_brand)

    async def pause(self, device_id: str) -> bool:
        pipe = self._pipelines.get(device_id)
        if not pipe or pipe["status"] != "running":
            return False
        await self._dm.pause_workflow(device_id)
        pipe["status"] = "paused"
        await self._db.log_activity(
            "warn", "pipeline", "Full run paused", device_id, {"source": "dashboard"}
        )
        await self._emit("pipeline_paused", {"device_id": device_id})
        return True

    async def resume(self, device_id: str) -> bool:
        pipe = self._pipelines.get(device_id)
        if not pipe or pipe["status"] != "paused":
            return False
        await self._dm.resume_workflow(device_id)
        pipe["status"] = "running"
        await self._db.log_activity(
            "info", "pipeline", "Full run resumed", device_id, {"source": "dashboard"}
        )
        await self._emit("pipeline_resumed", {"device_id": device_id})
        return True

    async def stop(self, device_id: str) -> bool:
        pipe = self._pipelines.get(device_id)
        stopped = await self._engine.stop_device(device_id)
        if pipe:
            self._pipelines.pop(device_id, None)
            await self._db.log_activity(
                "warn", "pipeline", "Full run stopped", device_id, {"source": "dashboard"}
            )
            await self._emit("pipeline_stopped", {"device_id": device_id})
            return True
        return stopped

    async def stop_all(self) -> None:
        for device_id in list(self._pipelines.keys()):
            await self.stop(device_id)

    async def _on_workflow_event(self, event: str, data: dict[str, Any]) -> None:
        device_id = data.get("device_id")
        if not device_id:
            return
        pipe = self._pipelines.get(device_id)
        if not pipe or pipe["status"] not in ("running", "paused"):
            return

        workflow = data.get("workflow")
        steps = pipe["steps"]
        current_step = steps[pipe["index"]] if pipe["index"] < len(steps) else None
        current = current_step["workflow"] if current_step else None

        if event == "workflow_completed":
            if workflow != current:
                return

            if current_step and workflow in _PREP_WORKFLOWS:
                device = self._dm.get_device(device_id)
                if device:
                    storage_key = device_storage_key(device_id, device.user_name)
                    mark_prep_completed(storage_key, brand=current_step["brand"])

            pipe["index"] += 1
            if pipe["index"] >= len(steps):
                pipe["status"] = "completed"
                workflow_names = [s["workflow"] for s in steps]
                self._pipelines.pop(device_id, None)
                await self._db.log_activity(
                    "info",
                    "pipeline",
                    "Full run completed",
                    device_id,
                    {"workflows": workflow_names, "source": "pipeline"},
                )
                await self._emit(
                    "pipeline_completed",
                    {"device_id": device_id, "workflows": workflow_names},
                )
                return

            next_step = steps[pipe["index"]]
            next_wf = next_step["workflow"]
            next_brand = next_step["brand"]
            await self._db.log_activity(
                "info",
                "pipeline",
                f"Advancing to {next_wf} ({pipe['index'] + 1}/{len(steps)}) · {next_brand}",
                device_id,
                {"next_workflow": next_wf, "brand": next_brand, "source": "pipeline"},
            )
            started = await self._start_step(device_id, pipe["index"])
            if not started:
                pipe["status"] = "failed"
                await self._db.log_activity(
                    "error",
                    "pipeline",
                    f"Failed to start {next_wf}",
                    device_id,
                    {"workflow": next_wf, "brand": next_brand, "source": "pipeline"},
                )
                await self._emit(
                    "pipeline_failed",
                    {"device_id": device_id, "workflow": next_wf, "message": "start failed"},
                )

        elif event == "workflow_failed":
            if workflow != current:
                return
            pipe["status"] = "failed"
            self._pipelines.pop(device_id, None)
            await self._db.log_activity(
                "error",
                "pipeline",
                f"Full run failed at {workflow}",
                device_id,
                {"workflow": workflow, "message": data.get("message"), "source": "pipeline"},
            )
            await self._emit(
                "pipeline_failed",
                {
                    "device_id": device_id,
                    "workflow": workflow,
                    "message": data.get("message", ""),
                },
            )
