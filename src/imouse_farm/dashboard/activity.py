"""Activity log helpers for dashboard feed."""

from __future__ import annotations

from typing import Any


def enrich_activity(entry: dict[str, Any], device_labels: dict[str, str]) -> dict[str, Any]:
    """Attach human-readable device label to an activity row."""
    device_id = entry.get("device_id")
    if device_id and device_id in device_labels:
        entry = dict(entry)
        entry["device_label"] = device_labels[device_id]
    return entry


def activity_from_event(event: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """Map legacy WebSocket events to activity entries (when not already logged)."""
    device_id = data.get("device_id")
    match event:
        case "workflow_started":
            return {
                "level": "info",
                "category": "workflow",
                "message": f"Workflow started: {data.get('workflow_name', '?')}",
                "device_id": device_id,
                "details": data,
            }
        case "workflow_completed":
            return {
                "level": "info",
                "category": "workflow",
                "message": f"Workflow completed: {data.get('workflow', '?')}",
                "device_id": device_id,
                "details": data,
            }
        case "workflow_failed":
            return {
                "level": "error",
                "category": "workflow",
                "message": f"Workflow failed: {data.get('workflow', '?')} — {data.get('message', '')}",
                "device_id": device_id,
                "details": data,
            }
        case "workflow_stopped":
            return {
                "level": "warn",
                "category": "workflow",
                "message": f"Workflow stopped: {data.get('workflow', '?')}",
                "device_id": device_id,
                "details": data,
            }
        case "state_changed":
            reason = data.get("reason", "")
            if reason.startswith("workflow:"):
                return None
            return {
                "level": "info",
                "category": "state",
                "message": f"State → {data.get('state', '?')}",
                "device_id": device_id,
                "details": data,
            }
        case "device_connected":
            return {
                "level": "info",
                "category": "device",
                "message": "Device connected",
                "device_id": device_id,
                "details": data,
            }
        case "device_disconnected":
            return {
                "level": "warn",
                "category": "device",
                "message": "Device disconnected",
                "device_id": device_id,
                "details": data,
            }
        case "frozen_device":
            return {
                "level": "error",
                "category": "device",
                "message": "Device appears frozen",
                "device_id": device_id,
                "details": data,
            }
        case "popup_detected":
            return {
                "level": "warn",
                "category": "popup",
                "message": data.get("message", "Popup detected"),
                "device_id": device_id,
                "details": data,
            }
    return None
