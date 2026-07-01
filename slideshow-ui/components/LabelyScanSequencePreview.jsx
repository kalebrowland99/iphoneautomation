"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { getFontEmbedCSS, toCanvas } from "html-to-image";
import { buildLabelyScanFrameSequence } from "@/lib/labelyScanExport";
import { getSlideInfo, isLabelyScanTourFormat } from "@/lib/slideLayout";
import { DISPLAY_SCALE } from "./VideoPreview";
import { waitForPreviewPaint } from "@/lib/waitForPreviewPaint";

const EXPORT_CAPTURE_PIXEL_RATIO = 1080 / Math.round(1080 * DISPLAY_SCALE);

/** Fallback pack shot when the slot has no image (matches export placeholder behavior). */
const SAMPLE_SCAN_PRODUCT_IMAGE = "/labely/references/IMG_0076.jpg";

async function waitForFonts() {
  if (!document.fonts?.ready) return;
  try {
    await document.fonts.ready;
  } catch {
    /* ignore */
  }
}

async function waitForImagesDecoded(root) {
  if (!root) return;
  const imgs = [...root.querySelectorAll("img")];
  await Promise.all(
    imgs.map(
      (img) =>
        new Promise((resolve) => {
          if (img.complete && img.naturalWidth > 0) {
            resolve();
            return;
          }
          const done = () => resolve();
          img.addEventListener("load", done, { once: true });
          img.addEventListener("error", done, { once: true });
        }),
    ),
  );
  await Promise.all(imgs.map((img) => (img.decode ? img.decode().catch(() => {}) : Promise.resolve())));
}

function getCaptureNode() {
  return document.getElementById("video-preview-root");
}

function scanTourSlideShowsAppComposite(info, config) {
  if (info?.type === "labely") return true;
  if ((config?.appId ?? "thrifty") === "valcoin" && info?.type === "thrifty") return true;
  return false;
}

export default function LabelyScanSequencePreview({ config, currentSlide, setCurrentSlide, totalSlides }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const canvasRef = useRef(null);
  const playTimerRef = useRef(null);

  const canPreview =
    isLabelyScanTourFormat(config) &&
    ["labely", "valcoin"].includes(config?.appId ?? "thrifty") &&
    totalSlides >= 2;

  const stopPlayback = useCallback(() => {
    if (playTimerRef.current != null) {
      clearInterval(playTimerRef.current);
      playTimerRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPlayback(), [stopPlayback]);

  const handleClose = useCallback(() => {
    stopPlayback();
    setOpen(false);
    setLoading(false);
  }, [stopPlayback]);

  const handlePlay = useCallback(async () => {
    if (!canPreview || open || loading) return;
    const root = getCaptureNode();
    if (!root) return;

    const prevSlide = currentSlide;
    let targetIdx = currentSlide;
    const curInfo = getSlideInfo(config, currentSlide);
    if (!scanTourSlideShowsAppComposite(curInfo, config)) {
      targetIdx = 1;
    }
    if (targetIdx < 1) targetIdx = 1;
    if (targetIdx > totalSlides - 1) targetIdx = 1;

    const info = getSlideInfo(config, targetIdx);
    if (!scanTourSlideShowsAppComposite(info, config)) {
      return;
    }

    setLoading(true);
    setOpen(true);

    try {
      flushSync(() => setCurrentSlide(targetIdx));
      await waitForPreviewPaint();
      await new Promise((r) => setTimeout(r, 100));
      await waitForFonts();
      await waitForImagesDecoded(root);

      const fontEmbedCSS = await getFontEmbedCSS(root).catch(() => undefined);
      const canvasBg = (config?.appId ?? "thrifty") === "valcoin" ? "#000000" : "#ffffff";
      const labelyCanvas = await toCanvas(root, {
        backgroundColor: canvasBg,
        pixelRatio: EXPORT_CAPTURE_PIXEL_RATIO,
        cacheBust: false,
        includeQueryParams: false,
        ...(fontEmbedCSS ? { fontEmbedCSS } : {}),
      });

      const slot = info.slot ?? config.slots?.[targetIdx - 1] ?? config.slots?.[0];
      let productDataUrl = typeof slot?.imageUrl === "string" ? slot.imageUrl.trim() : "";
      const isValcoinApp = (config?.appId ?? "thrifty") === "valcoin";
      if (!productDataUrl) {
        if (isValcoinApp) {
          setLoading(false);
          setOpen(false);
          flushSync(() => setCurrentSlide(prevSlide));
          return;
        }
        productDataUrl = SAMPLE_SCAN_PRODUCT_IMAGE;
      }

      const seq = await buildLabelyScanFrameSequence({
        productDataUrl,
        labelyCanvas,
        scanSec: 1.35,
        revealSec: 0.52,
        holdSec: config.slideDuration,
        fps: 30,
        imageVariationSeed: (config.jitterSeed ?? 0) + (info.itemIndex ?? targetIdx) * 9973,
      });

      flushSync(() => setCurrentSlide(prevSlide));
      await waitForPreviewPaint();

      const canvas = canvasRef.current;
      if (!canvas || seq.length === 0) {
        setLoading(false);
        return;
      }

      canvas.width = 1080;
      canvas.height = 1920;
      const ctx = canvas.getContext("2d");
      let i = 0;
      const fps = 30;
      stopPlayback();
      playTimerRef.current = window.setInterval(() => {
        if (i >= seq.length) {
          stopPlayback();
          return;
        }
        ctx.drawImage(seq[i], 0, 0, 1080, 1920);
        i++;
      }, 1000 / fps);

      setLoading(false);
    } catch (e) {
      console.error("[LabelyScanSequencePreview]", e);
      flushSync(() => setCurrentSlide(prevSlide));
      setLoading(false);
      setOpen(false);
    }
  }, [canPreview, config, currentSlide, loading, open, setCurrentSlide, stopPlayback, totalSlides]);

  return (
    <>
      <button
        type="button"
        onClick={handlePlay}
        disabled={!canPreview || loading || open}
        title={
          canPreview
            ? "Play scan → slide-up → hold (matches Labely / Valcoin scan export)"
            : "Switch to Labely or Valcoin scan tour with at least 2 slides"
        }
        className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-border bg-background text-foreground transition-colors hover:bg-muted/50 disabled:cursor-not-allowed disabled:opacity-35"
        aria-label="Play scan tour export preview"
      >
        {loading ? (
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-foreground" />
        ) : (
          <span className="text-lg leading-none pl-0.5">▶</span>
        )}
      </button>

      {open ? (
        <div
          className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label="Scan tour export preview"
        >
          <div className="relative flex flex-col items-center gap-3 max-w-[min(96vw,520px)]">
            <div className="flex items-center justify-between gap-3 w-full text-white/80 text-xs">
              <span className="font-semibold uppercase tracking-wider text-white/50">
                Scan → slide-up → hold
              </span>
              <button
                type="button"
                onClick={handleClose}
                className="rounded-lg px-3 py-1.5 bg-white/10 hover:bg-white/20 border border-white/15 text-white text-xs font-semibold"
              >
                Close
              </button>
            </div>
            <div className="relative w-full">
              <canvas
                ref={canvasRef}
                width={1080}
                height={1920}
                className="w-full max-h-[min(78vh,820px)] h-auto rounded-2xl shadow-2xl border border-white/10 bg-black"
              />
              {loading ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-2xl bg-black/55 text-white/70 text-sm font-medium">
                  <span className="w-8 h-8 border-2 border-white/25 border-t-white rounded-full animate-spin" />
                  Building preview…
                </div>
              ) : null}
            </div>
            <p className="text-white/35 text-[10px] text-center leading-relaxed max-w-sm">
              Same sequence as video export — static app frame for the hold segment.
            </p>
          </div>
        </div>
      ) : null}
    </>
  );
}
