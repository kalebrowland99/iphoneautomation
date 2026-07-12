"""Step goals and error context for OpenAI vision recovery."""

from __future__ import annotations

# Hard cap: vision dismiss calls per polling wait (wait_for_plus, plus ready, etc.).
MAX_VISION_DISMISS_PER_WAIT = 5

# How many recent workflow errors to include in vision prompts.
MAX_RECENT_ERRORS = 8

# Per inline recovery site (profile tab, switcher, etc.) — one attempt each is enough.
MAX_VISION_DISMISS_INLINE = 1

# Maps ensure_tiktok_account vision context → prompt goal (when/where vision applies).
_VISION_INLINE_CONTEXT_GOALS: dict[str, str] = {
    "profile tab tap failed": (
        "TikTok home feed is visible. Dismiss any overlay blocking the bottom "
        "navigation bar (especially the profile tab on the right)."
    ),
    "profile tab did not open": (
        "TikTok home feed is still visible — the profile tab tap did not open the "
        "profile screen. Dismiss any popup or overlay blocking the profile tab."
    ),
    "account switcher did not open": (
        "TikTok profile tab is open but the account switcher dropdown did not appear. "
        "Dismiss any overlay blocking the display name / account switcher opener."
    ),
    "account dropdown handle not found": (
        "TikTok account switcher dropdown is open. Dismiss any overlay blocking the "
        "target @ account row in the list."
    ),
}

_STEP_GOALS: dict[str, str] = {
    "wait_for_plus": (
        "TikTok home feed has finished loading and the + create button at the "
        "bottom center is visible."
    ),
    "ensure_tiktok_account": (
        "TikTok profile tab shows the configured @ account. Dismiss any popup "
        "blocking the profile tab, account name row, or account switcher."
    ),
    "tap_plus": "TikTok create/upload flow opened after tapping +.",
    "tap_gallery": "Photo gallery picker is open so media can be selected.",
    "wait_for_recents": "Gallery Recents tab is visible with uploaded photos.",
    "tap_gallery_item": "A gallery photo/video is selected for the post.",
    "tap_post": "TikTok post was submitted successfully.",
    "open_tiktok": "TikTok app is open on the home feed.",
    "kill_apps": "All apps are closed; phone is on the home screen.",
}

_WORKFLOW_STEP_GOALS: dict[tuple[str, str], str] = {
    (
        "tiktok_account_switch",
        "ensure_tiktok_account",
    ): (
        "On TikTok profile tab: verify the correct @ account is active. Dismiss "
        "any overlay blocking the profile tab, display name, or account switcher "
        "dropdown."
    ),
    (
        "tiktok_post",
        "wait_for_plus",
    ): (
        "TikTok home feed is ready — the + button must be visible at the bottom. "
        "Dismiss any popup, tutorial, or overlay hiding the + button."
    ),
}


def vision_inline_context_goal(context: str) -> str | None:
    """Goal text for a specific ensure_tiktok_account vision recovery site."""
    return _VISION_INLINE_CONTEXT_GOALS.get(str(context or "").strip())


def vision_step_goal(workflow_name: str, step_name: str) -> str:
    """Human goal for what this step is trying to achieve."""
    wf = str(workflow_name or "").strip()
    step = str(step_name or "").strip()
    keyed = _WORKFLOW_STEP_GOALS.get((wf, step))
    if keyed:
        return keyed
    if step in _STEP_GOALS:
        return _STEP_GOALS[step]
    if wf:
        return f"Complete step '{step}' in workflow '{wf}'."
    return f"Complete step '{step}'."


def build_vision_error_msg(
    *,
    workflow_name: str,
    step_name: str,
    error_msg: str,
    recent_errors: list[str] | None = None,
    extra_context: str = "",
) -> str:
    """Build the user prompt sent with the screenshot to OpenAI vision."""
    goal = vision_step_goal(workflow_name, step_name)
    lines = [
        f"Workflow: {workflow_name or 'unknown'}",
        f"Step: {step_name or 'unknown'}",
        f"Goal: {goal}",
        f"Current error: {error_msg}",
    ]
    if extra_context:
        lines.append(f"Context: {extra_context}")
    if recent_errors:
        lines.append("Recent errors in this workflow run:")
        for entry in recent_errors[-MAX_RECENT_ERRORS:]:
            lines.append(f"  - {entry}")
    lines.append(
        "If a popup, alert, tutorial, or overlay blocks progress toward the goal, "
        "return its dismiss tap coordinate. Otherwise return popup=false."
    )
    return "\n".join(lines)
