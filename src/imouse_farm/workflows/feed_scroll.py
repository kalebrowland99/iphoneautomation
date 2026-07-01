"""Random TikTok feed swipe / double-tap coordinates for warmup and LIVE dismissal."""

from __future__ import annotations

import random
from typing import Any

DEFAULT_SCREEN_WIDTH = 406
DEFAULT_SCREEN_HEIGHT = 720


def screen_dimensions(device: Any | None) -> tuple[int, int]:
    sw = DEFAULT_SCREEN_WIDTH
    sh = DEFAULT_SCREEN_HEIGHT
    if device is not None:
        dw = int(getattr(device, "screen_width", 0) or 0)
        dh = int(getattr(device, "screen_height", 0) or 0)
        if dw > 0 and dh > 0:
            sw, sh = dw, dh
    return sw, sh


def random_feed_swipe_coords(sw: int, sh: int) -> tuple[int, int, int, int]:
    """Return (sx, sy, ex, ey) for a random upward swipe on the feed."""
    sx = random.randint(max(5, int(sw * 0.25)), max(6, int(sw * 0.75)))
    sy = random.randint(max(5, int(sh * 0.55)), max(6, int(sh * 0.85)))
    swipe_len = random.randint(max(80, int(sh * 0.25)), max(120, int(sh * 0.45)))
    ey = max(5, sy - swipe_len)
    ex = max(5, min(sw - 5, sx + random.randint(-15, 15)))
    return sx, sy, ex, ey


def random_center_double_tap_coords(sw: int, sh: int) -> tuple[int, int]:
    """Random point in the center band of the screen (for like double-tap)."""
    x = random.randint(max(5, int(sw * 0.30)), max(6, int(sw * 0.70)))
    y = random.randint(max(5, int(sh * 0.30)), max(6, int(sh * 0.70)))
    return x, y


async def swipe_feed_up(
    controller: Any,
    device_id: str,
    sw: int,
    sh: int,
) -> dict[str, Any] | None:
    sx, sy, ex, ey = random_feed_swipe_coords(sw, sh)
    ok = await controller.swipe(
        device_id,
        direction="up",
        sx=sx,
        sy=sy,
        ex=ex,
        ey=ey,
    )
    if not ok:
        return None
    return {"sx": sx, "sy": sy, "ex": ex, "ey": ey}
