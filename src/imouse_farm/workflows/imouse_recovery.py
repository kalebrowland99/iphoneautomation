"""Detect iMouseXP infrastructure failures and batch kernel-recovery helpers."""

from __future__ import annotations

# Reasons / substrings that indicate iMouse cast, SDK, or screenshot infrastructure failed.
_IMOUSE_FAILURE_EXACT = frozenset({
    "cast_connect_failed",
    "batch_device_timeout",
    "pipeline_start_failed",
})

_IMOUSE_FAILURE_SUBSTRINGS = (
    "imouse",
    "airplay",
    "cast connect",
    "cast failed",
    "screenshot",
    "调用超时",
    "call timeout",
    "connection refused",
    "not connected",
    "kernel",
)

# VPN URL shortcuts time out on a stuck phone — recover with phone reset, not kernel restart.
_VPN_SHORTCUT_MARKERS = (
    "shortcut_exec_url",
    "shadowrocket://",
    "vpn shortcut",
)


def is_imouse_failure(reason: str) -> bool:
    """Return True when a batch failure likely stems from iMouseXP, not content/config."""
    text = str(reason or "").strip().lower()
    if not text:
        return False
    if any(token in text for token in _VPN_SHORTCUT_MARKERS):
        return False
    if text in _IMOUSE_FAILURE_EXACT:
        return True
    if text.startswith("warmup_failed:") or text.startswith("pipeline_"):
        return any(token in text for token in _IMOUSE_FAILURE_SUBSTRINGS)
    return any(token in text for token in _IMOUSE_FAILURE_SUBSTRINGS)
