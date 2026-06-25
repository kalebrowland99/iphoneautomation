"""Chain prep → post → end workflows for full production runs."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from imouse_farm.database.repository import DatabaseRepository
from imouse_farm.devices.manager import DeviceManager
from imouse_farm.post.post_caption_store import POST_COUNT
from imouse_farm.utils.logging import get_logger
from imouse_farm.workflows.engine import WorkflowEngine

logger = get_logger(__name__)

TIKTOK_FULL_PIPELINE = ("tiktok_prep", "tiktok_post", "tiktok_end")
TIKTOK_POST_END_PIPELINE = ("tiktok_post", "tiktok_end")

EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class WorkflowPipeline:
    """Run tiktok_prep → tiktok_post → tiktok_end sequentially on one device."""

    def __init__(
        self,
        workflow_engine: WorkflowEngine,
        device_manager: DeviceManager,
        db: DatabaseRepository,
    ) -> None:
        self._engine = workflow_engine
        self._dm = device_manager
        self._db = db
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
        workflows = pipe["workflows"]
        index = pipe["index"]
        return {
            "status": pipe["status"],
            "current_workflow": workflows[index] if index < len(workflows) else None,
            "step": index + 1,
            "total_steps": len(workflows),
            "workflows": list(workflows),
        }

    def is_active(self, device_id: str) -> bool:
        pipe = self._pipelines.get(device_id)
        return bool(pipe and pipe["status"] in ("running", "paused"))

    async def start(self, device_id: str, *, from_post: int | None = None) -> bool:
        if self.is_active(device_id):
            return False
        if self._engine.list_running():
            for entry in self._engine.list_running():
                if entry["device_id"] == device_id:
                    return False

        start_post_index: int | None = None
        if from_post is not None:
            if not (2 <= from_post <= POST_COUNT):
                return False
            workflows = list(TIKTOK_POST_END_PIPELINE)
            start_post_index = from_post
        else:
            workflows = list(TIKTOK_FULL_PIPELINE)

        self._pipelines[device_id] = {
            "workflows": workflows,
            "index": 0,
            "status": "running",
            "from_post": from_post,
        }
        first = workflows[0]
        started = await self._engine.start_workflow(
            first, device_id, start_post_index=start_post_index
        )
        if not started:
            self._pipelines.pop(device_id, None)
            return False

        if from_post is not None:
            label = f"Posts {from_post}→{POST_COUNT} + end ({first})"
            pipe_meta = {
                "pipeline": workflows,
                "from_post": from_post,
                "source": "dashboard",
            }
        else:
            label = f"Full run started ({first})"
            pipe_meta = {"pipeline": workflows, "source": "dashboard"}

        await self._db.log_activity(
            "info",
            "pipeline",
            label,
            device_id,
            pipe_meta,
        )
        await self._emit(
            "pipeline_started",
            {
                "device_id": device_id,
                "workflows": workflows,
                "from_post": from_post,
            },
        )
        return True

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
        workflows = pipe["workflows"]
        current = workflows[pipe["index"]] if pipe["index"] < len(workflows) else None

        if event == "workflow_completed":
            if workflow != current:
                return
            pipe["index"] += 1
            if pipe["index"] >= len(workflows):
                pipe["status"] = "completed"
                self._pipelines.pop(device_id, None)
                await self._db.log_activity(
                    "info",
                    "pipeline",
                    "Full run completed",
                    device_id,
                    {"workflows": list(workflows), "source": "pipeline"},
                )
                await self._emit(
                    "pipeline_completed",
                    {"device_id": device_id, "workflows": list(workflows)},
                )
                return

            next_wf = workflows[pipe["index"]]
            await self._db.log_activity(
                "info",
                "pipeline",
                f"Advancing to {next_wf} ({pipe['index'] + 1}/{len(workflows)})",
                device_id,
                {"next_workflow": next_wf, "source": "pipeline"},
            )
            started = await self._engine.start_workflow(next_wf, device_id)
            if not started:
                pipe["status"] = "failed"
                await self._db.log_activity(
                    "error",
                    "pipeline",
                    f"Failed to start {next_wf}",
                    device_id,
                    {"workflow": next_wf, "source": "pipeline"},
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
