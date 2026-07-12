"""Production-order debug pipeline (Labely prep → posts → ValCoin prep → posts → end)."""

from __future__ import annotations

FlowStep = tuple[str, str]


def _post_steps(post_num: int, *, phase: str) -> list[FlowStep]:
    """One full tiktok_post iteration — matches config/workflows/tiktok_post.yaml."""
    label = f"{phase} post {post_num}"
    item = "post-tap-gallery-item" if post_num == 1 else f"post-tap-gallery-item-{post_num}"
    onscreen = f"post-type-caption-{post_num}"
    final = f"post-type-final-caption-{post_num}"

    steps: list[FlowStep] = [
        (f"{label}: tap + (×2)", "tap-plus"),
        (f"{label}: tap gallery (58,1035) ×2", "post-tap-gallery-only"),
        (f"{label}: wait for Recents", "post-wait-recents"),
        (f"{label}: select gallery video", item),
        (f"{label}: tap Next (optional)", "post-tap-next-only"),
        (f"{label}: tap music (310,62)", "post-tap-music"),
        (f"{label}: tap Favorites ×2", "post-tap-favorites"),
        (f"{label}: tap Hvitserk's choice", "post-tap-hvitserk"),
        (f"{label}: dismiss music picker", "post-dismiss-music"),
        (f"{label}: tap Aa", "tap-aa"),
        (f"{label}: type onscreen text", onscreen),
    ]
    if post_num == 1:
        steps.append((f"{label}: white background (303,63) ×2", "post-tap-border2-coord"))
    steps.extend(
        [
            (f"{label}: tap Done", "post-tap-done"),
            (f"{label}: tap editor", "tap-editor"),
            (f"{label}: swipe left ×2", "post-swipe-left"),
            (f"{label}: tap text scrub", "post-tap-text-scrub"),
            (f"{label}: drag trim", "post-drag-trim"),
            (f"{label}: tap continue arrow", "tap-continuearrow"),
            (f"{label}: tap caption field", "post-tap-final-caption-field"),
            (f"{label}: type final caption", final),
            (f"{label}: tap Post", "tap-post"),
        ]
    )
    if post_num == 3:
        steps.append((f"{label}: go home (after upload)", "post-go-home"))
    return steps


def _labely_prep_steps() -> list[FlowStep]:
    """config/workflows/tiktok_prep.yaml execute_action steps."""
    return [
        ("Labely prep: tap lock screen (if locked)", "tap-lock_screen"),
        ("Labely prep: swipe unlock (if locked)", "prep-swipe-unlock"),
        ("Labely prep: home before kill", "prep-home"),
        ("Labely prep: kill apps", "prep-kill-apps"),
        ("Labely prep: home after kill", "prep-home"),
        ("Labely prep: VPN OFF before album (production)", "prep-vpn-off-before-album"),
        ("Labely prep: clear gallery", "clear-album"),
        ("Labely prep: upload Labely videos", "upload-gallery"),
        ("Labely prep: turn VPN on (shortcut)", "prep-vpn-shortcut-on"),
        ("Labely prep: open TikTok", "tap-tiktok"),
    ]


def _valcoin_prep_steps() -> list[FlowStep]:
    """config/workflows/tiktok_valcoin_prep.yaml execute_action steps."""
    return [
        # Reset TikTok after Labely posts (especially when skip-media skips post-go-home).
        ("ValCoin prep: kill apps", "end-kill-apps"),
        ("ValCoin prep: home", "prep-home"),
        ("ValCoin prep: VPN OFF before album (production)", "prep-vpn-off-before-album"),
        ("ValCoin prep: clear gallery", "valcoin-prep-clear-album"),
        ("ValCoin prep: upload ValCoin videos", "valcoin-prep-upload-gallery"),
        ("ValCoin prep: turn VPN on (shortcut)", "prep-vpn-shortcut-on"),
        ("ValCoin prep: open TikTok", "tap-tiktok"),
    ]


def _end_steps() -> list[FlowStep]:
    """config/workflows/tiktok_end.yaml execute_action steps."""
    return [
        ("End: home before kill", "prep-home"),
        ("End: kill apps", "end-kill-apps"),
        ("End: home after kill", "prep-home"),
        ("End: turn VPN off (shortcut)", "prep-vpn-shortcut-off"),
    ]


def _warmup_steps() -> list[FlowStep]:
    """ValCoin warmup from cold start: VPN on → open TikTok → switch account → scroll → exit → VPN off."""
    return [
        ("Warmup: turn VPN on (shortcut)", "prep-vpn-shortcut-on"),
        ("Warmup: open TikTok", "tap-tiktok"),
        ("Warmup: switch to ValCoin @", "account-ensure-full"),
        ("Warmup: run 2min scroll", "warmup-run"),
        ("Warmup: home after scroll", "prep-home"),
        ("Warmup: turn VPN off (shortcut)", "prep-vpn-shortcut-off"),
        ("Warmup: home", "prep-home"),
    ]


def _warmup_steps_post_labely() -> list[FlowStep]:
    """ValCoin warmup coming directly after Labely posts — VPN already on, skip setup.

    kill-apps is needed because in skip-media A-Z mode tap-post/post-go-home are skipped,
    leaving TikTok on the post editor screen where the + button is not visible.
    """
    return [
        ("Warmup: kill apps", "end-kill-apps"),
        ("Warmup: home", "prep-home"),
        ("Warmup: open TikTok", "tap-tiktok"),
        ("Warmup: switch to ValCoin @", "account-ensure-full"),
        ("Warmup: run 2min scroll", "warmup-run"),
        ("Warmup: home after scroll", "prep-home"),
        ("Warmup: turn VPN off (shortcut)", "prep-vpn-shortcut-off"),
        ("Warmup: home", "prep-home"),
    ]


def build_flow_debug_steps() -> list[FlowStep]:
    """Full Labely + ValCoin production pipeline in execution order."""
    steps: list[FlowStep] = []
    steps.extend(_labely_prep_steps())
    steps.append(("Labely: ensure TikTok @", "account-ensure-current"))
    for n in (1, 2, 3):
        steps.extend(_post_steps(n, phase="Labely"))
    steps.extend(_valcoin_prep_steps())
    steps.append(("ValCoin: switch TikTok @", "account-ensure-full"))
    for n in (1, 2, 3):
        steps.extend(_post_steps(n, phase="ValCoin"))
    steps.extend(_end_steps())
    return steps


def build_flow_debug_warmup_steps() -> list[FlowStep]:
    """Labely posts → ValCoin warmup (VPN stays on — no wasteful off→on cycle)."""
    steps: list[FlowStep] = []
    steps.extend(_labely_prep_steps())
    steps.append(("Labely: ensure TikTok @", "account-ensure-current"))
    for n in (1, 2, 3):
        steps.extend(_post_steps(n, phase="Labely"))
    steps.extend(_warmup_steps_post_labely())
    return steps


FLOW_DEBUG_STEPS: list[FlowStep] = build_flow_debug_steps()
FLOW_DEBUG_WARMUP_STEPS: list[FlowStep] = build_flow_debug_warmup_steps()

# Backward-compatible alias.
FULL_FLOW_DEBUG_STEPS = FLOW_DEBUG_STEPS


def flow_step_letter(index: int) -> str:
    if index < 26:
        return chr(ord("A") + index)
    return str(index + 1)


def resolve_flow_debug_test_id(step_id: str) -> str:
    """Map dropdown id ``flow:042:tap-plus`` or ``warmup:006:warmup-run`` → the test id."""
    if step_id.startswith("flow:") or step_id.startswith("warmup:"):
        parts = step_id.split(":", 2)
        if len(parts) == 3 and parts[2]:
            return parts[2]
    return step_id
