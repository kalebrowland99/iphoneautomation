"use client";

import { useMemo, useRef, useState } from "react";
import { galleryThumbUrl } from "@/lib/galleryShow";

/**
 * Saved slideshow gallery — automation-style bordered list (phones table pattern).
 *
 * @param {{ show: object, origIdx: number }[]} entries
 */
export default function GalleryRail({ entries, activeShowIdx, loadShow }) {
  const scrollRef = useRef(null);
  const [jump, setJump] = useState("");

  const counts = useMemo(() => {
    let withThumb = 0;
    for (const { show } of entries) {
      if (galleryThumbUrl(show)) withThumb += 1;
    }
    return { withThumb, total: entries.length };
  }, [entries]);

  const runJump = () => {
    const n = Number.parseInt(String(jump).trim(), 10);
    if (!Number.isFinite(n) || n < 1 || n > entries.length) return;
    const el = document.querySelector(`[data-gallery-idx="${n - 1}"]`);
    el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    setJump("");
  };

  return (
    <div className="dash-card flex min-w-0 flex-col p-4 md:p-5">
      <div className="mb-3 flex shrink-0 items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Slideshows</h2>
        <span className="text-xs tabular-nums text-muted-foreground">
          {counts.total}
          {counts.withThumb < counts.total ? (
            <span className="text-muted-foreground/60"> · {counts.withThumb} thumbs</span>
          ) : null}
        </span>
      </div>

      {entries.length > 12 ? (
        <div className="mb-3 flex shrink-0 items-center gap-1.5">
          <label className="sr-only" htmlFor="gallery-jump">
            Jump to slideshow number
          </label>
          <input
            id="gallery-jump"
            type="number"
            min={1}
            max={entries.length}
            placeholder={`1–${entries.length}`}
            value={jump}
            onChange={(e) => setJump(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                runJump();
              }
            }}
            className="min-w-0 flex-1 rounded-lg border bg-background px-2 py-1.5 text-[11px] text-foreground outline-none placeholder:text-muted-foreground/50 focus:border-ring"
          />
          <button type="button" onClick={runJump} className="btn-ghost shrink-0 font-semibold">
            Go
          </button>
        </div>
      ) : null}

      <div
        ref={scrollRef}
        className="gallery-list-wrap max-h-[min(52vh,480px)] min-h-0 flex-1 overflow-y-auto overscroll-contain"
      >
        {entries.map(({ show, origIdx }, listIdx) => {
          const thumb = galleryThumbUrl(show);
          const caption = show.captionText || `Slideshow ${listIdx + 1}`;
          const active = activeShowIdx === origIdx;
          const batchTag =
            Number.isFinite(show?.batchIndex) && show.batchIndex > 0
              ? `#${show.batchIndex}`
              : null;

          return (
            <button
              key={origIdx}
              type="button"
              data-gallery-idx={listIdx}
              data-active={active ? "true" : "false"}
              onClick={() => loadShow(show, origIdx)}
              className="gallery-row"
            >
              <div className="gallery-thumb">
                {thumb ? (
                  <img src={thumb} alt="" className="h-full w-full object-cover object-center" />
                ) : (
                  <div className="flex h-full w-full items-center justify-center text-[10px] font-semibold tabular-nums text-muted-foreground/50">
                    {listIdx + 1}
                  </div>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span
                    className={`text-[11px] font-semibold tabular-nums ${active ? "text-foreground" : "text-muted-foreground"}`}
                  >
                    {listIdx + 1}
                  </span>
                  {batchTag ? (
                    <span className="rounded-md bg-muted px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground">
                      batch {batchTag}
                    </span>
                  ) : null}
                  {active ? (
                    <span className="text-[9px] font-medium text-foreground">active</span>
                  ) : null}
                </div>
                <p className="truncate text-[11px] leading-snug text-muted-foreground">{caption}</p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
