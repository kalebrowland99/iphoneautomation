/** Root element id used by `VideoPreview` for export capture. */
const DEFAULT_PREVIEW_ROOT_ID = "video-preview-root";

/**
 * Wait until after layout/paint so capture (`html-to-image`, canvas) matches the preview.
 *
 * When the tab is hidden (another tab focused, or window minimized in many setups),
 * Chromium suspends `requestAnimationFrame`, which would otherwise stall exports
 * indefinitely. In that case we use microtasks + nested timeouts and a reflow read
 * on the preview root so work can keep progressing in the background (often slower
 * due to timer throttling, but it completes).
 *
 * @param {{ rootId?: string }} [opts]
 */
export function waitForPreviewPaint(opts = {}) {
  const rootId = opts.rootId ?? DEFAULT_PREVIEW_ROOT_ID;
  return new Promise((resolve) => {
    const nudgeReflow = () => {
      try {
        const el = document.getElementById(rootId);
        if (el && "offsetHeight" in el) void el.offsetHeight;
      } catch {
        /* ignore */
      }
    };

    const done = () => {
      nudgeReflow();
      resolve();
    };

    if (typeof window === "undefined" || typeof document === "undefined") {
      queueMicrotask(done);
      return;
    }

    if (document.visibilityState === "visible") {
      requestAnimationFrame(() => requestAnimationFrame(done));
      return;
    }

    queueMicrotask(() => {
      setTimeout(() => {
        setTimeout(done, 0);
      }, 0);
    });
  });
}
