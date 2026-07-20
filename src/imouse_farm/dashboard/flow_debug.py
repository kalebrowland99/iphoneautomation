"""Production-order debug pipeline (Labely prep → posts → ValCoin prep → posts → end)."""

from __future__ import annotations

FlowStep = tuple[str, str]


def _post_steps(
    post_num: int,
    *,
    phase: str,
    include_post_button: bool = True,
    go_home_after: bool | None = None,
    gallery_item_id: str | None = None,
    skip_onscreen_editor: bool = False,
) -> list[FlowStep]:
    """One full tiktok_post iteration — matches config/workflows/tiktok_post.yaml."""
    label = f"{phase} post {post_num}"
    item = gallery_item_id or (
        "post-tap-gallery-item" if post_num == 1 else f"post-tap-gallery-item-{post_num}"
    )
    onscreen = f"post-type-caption-{post_num}"
    final = f"post-type-final-caption-{post_num}"

    steps: list[FlowStep] = [
        (f"{label}: tap + (×2)", "tap-plus"),
        (f"{label}: tap gallery (58,1035) ×2", "post-tap-gallery-only"),
        (f"{label}: wait for Recents", "post-wait-recents"),
        (f"{label}: select gallery video", item),
        (f"{label}: tap Next (optional)", "post-tap-next-only"),
        (f"{label}: tap music (310,62)", "post-tap-music"),
    ]
    if skip_onscreen_editor:
        steps.append(
            (f"{label}: deselect recommended song (291,696)", "post-deselect-recommended-song")
        )
    else:
        steps.extend(
            [
                (f"{label}: tap Favorites ×2", "post-tap-favorites"),
                (f"{label}: tap Hvitserk's choice", "post-tap-hvitserk"),
            ]
        )
    steps.append((f"{label}: dismiss music picker", "post-dismiss-music"))
    if not skip_onscreen_editor:
        steps.extend(
            [
                (f"{label}: tap Aa (vision)", "tap-aa"),
                (f"{label}: type onscreen text", onscreen),
            ]
        )
        if post_num == 1:
            steps.append((f"{label}: white background (303,63) ×2", "post-tap-border2-coord"))
        steps.extend(
            [
                (f"{label}: tap Done", "post-tap-done"),
                (f"{label}: tap editor (saved vision)", "tap-editor"),
                (f"{label}: swipe left ×2", "post-swipe-left"),
                (f"{label}: tap text scrub", "post-tap-text-scrub"),
                (f"{label}: drag trim", "post-drag-trim"),
                (f"{label}: tap continue arrow", "tap-continuearrow"),
            ]
        )
    else:
        steps.append(
            (f"{label}: tap Next after music (466,1028)", "post-tap-next-after-music-supplied")
        )
    steps.extend(
        [
            (f"{label}: tap caption field", "post-tap-final-caption-field"),
            (f"{label}: type final caption", final),
        ]
    )
    if include_post_button:
        steps.append((f"{label}: tap Post", "tap-post"))
    if go_home_after is None:
        go_home_after = bool(include_post_button and post_num == 3)
    if go_home_after:
        steps.append((f"{label}: go home (after upload)", "post-go-home"))
    return steps


def draft_gallery_test_id(post: int, total: int) -> str:
    return f"draft-gallery-{total}-p{post}"


def build_post_draft_debug_steps(
    *,
    video_count: int = 1,
    use_supplied_videos: bool = False,
) -> list[FlowStep]:
    """Download localhost/supplied videos → open TikTok → draft posts 1..N (no Post on last).

    When ``use_supplied_videos`` is on, skip Aa / onscreen text / timeline editor
    (text is already in the video), deselect the recommended song instead of
    Favorites/Hvitserk, tap Next (466,1028) instead of continue arrow, then
    caption → Post.
    """
    from imouse_farm.post.post_caption_store import POST_COUNT

    n = max(1, min(POST_COUNT, int(video_count or 1)))
    steps: list[FlowStep] = [
        ("Draft: download localhost videos to phone", "draft-download-videos"),
        ("Draft: open TikTok", "tap-tiktok"),
    ]
    for post in range(1, n + 1):
        batch = _post_steps(
            post,
            phase="Draft",
            include_post_button=(post < n),
            go_home_after=False,
            gallery_item_id=draft_gallery_test_id(post, n),
            skip_onscreen_editor=bool(use_supplied_videos),
        )
        steps.extend(batch)
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
        ("Labely prep: turn VPN on (icon + vision)", "prep-vpn-vision-ensure-on"),
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
        ("ValCoin prep: turn VPN on (icon + vision)", "prep-vpn-vision-ensure-on"),
        ("ValCoin prep: open TikTok", "tap-tiktok"),
    ]


def _end_steps() -> list[FlowStep]:
    """config/workflows/tiktok_end.yaml execute_action steps."""
    return [
        ("End: home before kill", "prep-home"),
        ("End: kill apps", "end-kill-apps"),
        ("End: home after kill", "prep-home"),
        ("End: turn VPN off (icon + vision)", "prep-vpn-vision-ensure-off"),
    ]


def _warmup_steps() -> list[FlowStep]:
    """ValCoin warmup from cold start: VPN on → open TikTok → switch account → scroll → exit → VPN off."""
    return [
        ("Warmup: turn VPN on (icon + vision)", "prep-vpn-vision-ensure-on"),
        ("Warmup: open TikTok", "tap-tiktok"),
        ("Warmup: switch to ValCoin @", "account-ensure-full"),
        ("Warmup: run 2min scroll", "warmup-run"),
        ("Warmup: home after scroll", "prep-home"),
        ("Warmup: turn VPN off (icon + vision)", "prep-vpn-vision-ensure-off"),
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
        ("Warmup: turn VPN off (icon + vision)", "prep-vpn-vision-ensure-off"),
        ("Warmup: home", "prep-home"),
    ]


def _vpn_steps() -> list[FlowStep]:
    """Shadowrocket VPN: home icon → gpt-4o status → fixed toggle."""
    return [
        ("VPN: open Shadowrocket (home → 373,1003)", "prep-open-shadowrocket"),
        ("VPN: vision status (gpt-4o STATUS only)", "prep-vpn-vision-analyze"),
        ("VPN: turn ON (icon + vision + toggle 515,171)", "prep-vpn-vision-ensure-on"),
        ("VPN: turn OFF (icon + vision + toggle 515,171)", "prep-vpn-vision-ensure-off"),
        ("VPN: OFF before album (production clear path)", "prep-vpn-off-before-album"),
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


def build_vpn_flow_debug_steps() -> list[FlowStep]:
    """Standalone Shadowrocket VPN debug pipeline."""
    return _vpn_steps()


FLOW_DEBUG_STEPS: list[FlowStep] = build_flow_debug_steps()
FLOW_DEBUG_WARMUP_STEPS: list[FlowStep] = build_flow_debug_warmup_steps()
FLOW_DEBUG_VPN_STEPS: list[FlowStep] = build_vpn_flow_debug_steps()

# Backward-compatible alias.
FULL_FLOW_DEBUG_STEPS = FLOW_DEBUG_STEPS


def flow_step_letter(index: int) -> str:
    if index < 26:
        return chr(ord("A") + index)
    return str(index + 1)


def resolve_flow_debug_test_id(step_id: str) -> str:
    """Map dropdown id ``flow:042:tap-plus`` / ``warmup:…`` / ``vpn:…`` / ``draft:…`` → test id."""
    for prefix in ("flow:", "warmup:", "vpn:", "draft:"):
        if step_id.startswith(prefix):
            parts = step_id.split(":", 2)
            if len(parts) == 3 and parts[2]:
                return parts[2]
            break
    return step_id
