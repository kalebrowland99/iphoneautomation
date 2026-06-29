#!/usr/bin/env python3
"""Open autoslideshow /automation in Chromium and wait for farm job completion."""

from __future__ import annotations

import argparse
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser(description="Run autoslideshow farm automation in a browser")
    parser.add_argument("--url", required=True, help="Full /automation URL with query params")
    parser.add_argument("--timeout", type=int, default=3600, help="Max seconds to wait")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "playwright is not installed — pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 1

    deadline = time.time() + max(60, int(args.timeout))
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(
                headless=False,
                channel="chrome",
            )
        except Exception:
            browser = playwright.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_default_timeout(120_000)
        print(f"Opening {args.url}", flush=True)
        page.goto(args.url, wait_until="domcontentloaded")
        while time.time() < deadline:
            done = page.evaluate("() => !!window.__FARM_JOB_DONE__")
            if done:
                print("Farm automation finished.", flush=True)
                browser.close()
                return 0
            err = page.evaluate("() => String(window.__FARM_JOB_ERROR__ || '')")
            if err:
                print(err, file=sys.stderr)
                browser.close()
                return 1
            status = page.evaluate("() => String(window.__FARM_JOB_STATUS__ || '')")
            if status:
                print(status, flush=True)
            time.sleep(2)
        browser.close()
        print("Timed out waiting for farm automation.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
