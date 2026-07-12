"use client";

import { flushSync } from "react-dom";
import {
  lastLabelySlideIndex,
  pickLabelyOutroText,
  resolveLabelyOutroText,
} from "@/lib/labelyOutroText";
import { waitForPreviewPaint } from "@/lib/waitForPreviewPaint";

export default function LabelyOutroPreview({
  config,
  setConfig,
  currentSlide,
  setCurrentSlide,
}) {
  const isLabely = (config?.appId ?? "thrifty") === "labely";
  if (!isLabely) return null;

  const outroText = resolveLabelyOutroText(config, currentSlide);
  const lastSlide = lastLabelySlideIndex(config);

  const applyOutro = (text) => {
    flushSync(() => {
      setConfig((prev) => ({ ...prev, labelyOutroText: text }));
      setCurrentSlide(lastSlide);
    });
  };

  const handlePreview = async () => {
    const text = resolveLabelyOutroText(config, `preview:${Date.now()}`);
    applyOutro(text);
    await waitForPreviewPaint();
  };

  const handleShuffle = async () => {
    const text = pickLabelyOutroText(String(Date.now()));
    applyOutro(text);
    await waitForPreviewPaint();
  };

  const onLastSlide = currentSlide === lastSlide;

  return (
    <div className="flex w-full max-w-[390px] flex-col gap-2 rounded-xl border border-border/70 bg-muted/30 p-3 text-left">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium hover:bg-muted"
          onClick={() => void handlePreview()}
        >
          Preview outro (last slide)
        </button>
        <button
          type="button"
          className="rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium hover:bg-muted"
          onClick={() => void handleShuffle()}
        >
          New outro line
        </button>
      </div>
      <p className="text-[11px] leading-snug text-muted-foreground">
        {onLastSlide
          ? "Showing centered white outro on this slide (burned into export hold frames)."
          : `Jumps to slide ${lastSlide + 1} — last scan segment with outro overlay.`}
      </p>
      {outroText ? (
        <p className="rounded-lg bg-white px-2.5 py-1.5 text-center text-[10px] font-semibold lowercase text-foreground shadow-sm">
          {outroText}
        </p>
      ) : null}
    </div>
  );
}
