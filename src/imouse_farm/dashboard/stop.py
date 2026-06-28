"""Full stop: workflows, pipeline, queued actions, permission watcher, in-flight cancel."""

from __future__ import annotations

from typing import Any

from imouse_farm.actions.cancel import mark_cancelled
from imouse_farm.utils.logging import get_logger
from imouse_farm.utils.orphan_processes import cleanup_orphan_imouse_processes

logger = get_logger(__name__)


async def stop_device_automation(app: Any, device_id: str) -> dict[str, Any]:
    """Stop everything running for one device — same hygiene as a clean interrupt."""
    mark_cancelled(device_id)

    if app.permission_watchers:
        await app.permission_watchers.force_stop(device_id)

    pipeline_stopped = await app.workflow_pipeline.stop(device_id)
    workflow_stopped = await app.workflow_engine.stop_device(device_id)
    cancelled_actions = await app.action_engine.abort_device(device_id)

    cleanup = cleanup_orphan_imouse_processes(app.config.dashboard.port)

    details: dict[str, Any] = {
        "pipeline_stopped": pipeline_stopped,
        "workflow_stopped": workflow_stopped,
        "cancelled_actions": cancelled_actions,
        "orphans_killed": cleanup.get("killed_pids", []),
    }
    if cleanup.get("killed_pids"):
        await app.db.log_activity(
            "warn",
            "system",
            f"Killed {len(cleanup['killed_pids'])} duplicate server process(es)",
            device_id,
            {"pids": cleanup["killed_pids"], "source": "stop"},
        )

    await app.db.log_activity(
        "warn",
        "workflow",
        "Killed — workflows, pipeline, actions, and permission watcher cleared",
        device_id,
        {**details, "source": "dashboard"},
    )
    logger.info("device_automation_stopped", device_id=device_id, **details)
    return {"success": True, **details}
