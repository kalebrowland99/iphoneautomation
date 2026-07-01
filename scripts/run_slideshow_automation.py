#!/usr/bin/env python3
"""Open autoslideshow /automation in Chromium and wait for farm job completion."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHROME_PROFILE_DIR = PROJECT_ROOT / "data" / "chrome_slideshow_profile"

_FARM_STATE_JS = """() => ({
    done: !!window.__FARM_JOB_DONE__,
    error: String(window.__FARM_JOB_ERROR__ || ''),
    status: String(window.__FARM_JOB_STATUS__ || ''),
    href: String(location.href || ''),
    title: String(document.title || ''),
    bodyText: String(document.body?.innerText || '').slice(0, 200),
})"""


def _configure_stdio() -> None:
    """Windows consoles often use cp1252; autoslideshow status uses Unicode arrows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _safe_print(message: str, *, stream: TextIO | None = None) -> None:
    stream = stream or sys.stdout
    text = str(message or "")
    try:
        stream.write(f"{text}\n")
        stream.flush()
    except UnicodeEncodeError:
        enc = getattr(stream, "encoding", None) or "utf-8"
        safe = text.encode(enc, errors="replace").decode(enc, errors="replace")
        stream.write(f"{safe}\n")
        stream.flush()


def _launch_browser_context(playwright: object, url: str) -> tuple[object, object]:
    """Persistent Chrome profile + local-network-access so localhost ingest is not blocked."""
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else ""
    CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    base_kwargs: dict[str, Any] = {
        "headless": False,
        "permissions": ["local-network-access"],
    }
    try:
        context = playwright.chromium.launch_persistent_context(  # type: ignore[attr-defined]
            str(CHROME_PROFILE_DIR),
            channel="chrome",
            **base_kwargs,
        )
    except Exception:
        context = playwright.chromium.launch_persistent_context(  # type: ignore[attr-defined]
            str(CHROME_PROFILE_DIR),
            **base_kwargs,
        )
    if origin:
        try:
            context.grant_permissions(["local-network-access"], origin=origin)  # type: ignore[attr-defined]
        except Exception as exc:
            _safe_print(f"local-network-access pre-grant skipped: {exc}")
    page = context.pages[0] if context.pages else context.new_page()  # type: ignore[attr-defined]
    return context, page


def _clear_cookies_and_cache(context: object, page: object, url: str) -> None:
    """Fresh session: wipe cookies, cache, and site storage before automation."""
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    context.clear_cookies()  # type: ignore[attr-defined]

    try:
        cdp = context.new_cdp_session(page)  # type: ignore[attr-defined]
        cdp.send("Network.clearBrowserCache")
        cdp.send("Network.clearBrowserCookies")
        if origin and parsed.netloc:
            cdp.send(
                "Storage.clearDataForOrigin",
                {
                    "origin": origin,
                    "storageTypes": (
                        "cookies,local_storage,session_storage,"
                        "indexeddb,cache_storage,service_workers"
                    ),
                },
            )
    except Exception as exc:
        _safe_print(f"CDP cache clear skipped: {exc}")

    context.clear_cookies()  # type: ignore[attr-defined]


def _read_farm_state(page: object) -> dict[str, Any] | None:
    """Read autoslideshow farm globals; return None if the page is not ready yet."""
    if page.is_closed():  # type: ignore[attr-defined]
        return None
    try:
        state = page.evaluate(_FARM_STATE_JS)  # type: ignore[attr-defined]
        if isinstance(state, dict):
            return state
    except Exception as exc:
        err = str(exc).lower()
        if "destroyed" in err or "navigation" in err or "context" in err:
            try:
                page.wait_for_load_state("domcontentloaded", timeout=30_000)  # type: ignore[attr-defined]
            except Exception:
                pass
            return None
        raise
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run autoslideshow farm automation in a browser")
    parser.add_argument("--url", required=True, help="Full /automation URL with query params")
    parser.add_argument("--timeout", type=int, default=3600, help="Max seconds to wait")
    parser.add_argument(
        "--no-clear-storage",
        action="store_true",
        help="Keep cookies/cache (default clears before each run)",
    )
    args = parser.parse_args()
    _configure_stdio()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _safe_print(
            "playwright is not installed — pip install playwright && playwright install chromium",
            stream=sys.stderr,
        )
        return 1

    deadline = time.time() + max(60, int(args.timeout))
    last_status = ""
    idle_polls = 0
    max_idle_polls = 90  # ~3 minutes with no status before failing

    with sync_playwright() as playwright:
        context, page = _launch_browser_context(playwright, args.url)
        page.set_default_timeout(120_000)

        if not args.no_clear_storage:
            _safe_print("Clearing Playwright cookies and cache...")
            _clear_cookies_and_cache(context, page, args.url)

        _safe_print(f"Opening {args.url}")
        page.goto(args.url, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=90_000)
        except Exception:
            pass

        while time.time() < deadline:
            if page.is_closed():
                _safe_print("Browser window closed before automation finished.", stream=sys.stderr)
                context.close()
                return 1

            try:
                state = _read_farm_state(page)
            except Exception as exc:
                _safe_print(f"Playwright error: {exc}", stream=sys.stderr)
                context.close()
                return 1

            if state is None:
                time.sleep(1)
                continue

            if state.get("done"):
                _safe_print("Farm automation finished.")
                context.close()
                return 0

            err = str(state.get("error") or "").strip()
            if err:
                _safe_print(err, stream=sys.stderr)
                context.close()
                return 1

            status = str(state.get("status") or "").strip()
            if status and status != last_status:
                _safe_print(status)
                last_status = status
                idle_polls = 0
            elif not status:
                idle_polls += 1
                if idle_polls == 1 or idle_polls % 15 == 0:
                    title = str(state.get("title") or "")
                    snippet = str(state.get("bodyText") or "").replace("\n", " ").strip()
                    _safe_print(
                        f"Waiting for automation to start... ({title or 'no title'}) {snippet}".strip(),
                    )
                if idle_polls >= max_idle_polls:
                    _safe_print(
                        "Timed out: autoslideshow never set __FARM_JOB_STATUS__. "
                        "The /automation page may be stuck loading or out of date on Vercel.",
                        stream=sys.stderr,
                    )
                    context.close()
                    return 3

            time.sleep(2)

        context.close()
        _safe_print("Timed out waiting for farm automation.", stream=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
