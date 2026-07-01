"use client";

import { useEffect, useState } from "react";
import { getGlobalJob, jobControls, readJobHeartbeat, subscribeGlobalJob } from "@/lib/globalJobProgress";

export default function GlobalJobBar() {
  const [, bump] = useState(0);
  const [reloadNotice, setReloadNotice] = useState(null);

  useEffect(() => subscribeGlobalJob(() => bump((n) => n + 1)), []);

  useEffect(() => {
    const hb = readJobHeartbeat();
    if (!hb) return;
    const age = Date.now() - hb.ts;
    if (age > 0 && age < 6 * 60 * 1000 && hb.percent > 2 && hb.percent < 98) {
      setReloadNotice(
        "A job was interrupted when this tab reloaded. Start Export or Generate again from the configuration panel."
      );
    }
  }, []);

  const j = getGlobalJob();

  if (!j && !reloadNotice) return null;

  return (
    <section className="mb-10 flex flex-col items-center space-y-4 text-center">
      {reloadNotice ? (
        <div className="page-banner flex w-full max-w-xl items-start justify-between gap-3 rounded-xl px-4 py-2.5 text-left">
          <p className="text-[11px] leading-snug">{reloadNotice}</p>
          <button type="button" onClick={() => setReloadNotice(null)} className="btn-ghost btn-sm shrink-0">
            Dismiss
          </button>
        </div>
      ) : null}
      {j ? (
        <div className="w-full max-w-xl space-y-3">
          <div className="flex justify-between px-1 text-xs text-muted-foreground">
            <span className="truncate font-medium" title={j.phase}>
              {j.paused ? "Paused" : j.phase}
            </span>
            <span className="shrink-0 tabular-nums">{Math.round(j.percent)}%</span>
          </div>
          <div className="h-2.5 w-full overflow-hidden rounded-full border border-border/50 bg-muted">
            <div
              className="h-full rounded-full bg-foreground transition-all duration-700 ease-out"
              style={{ width: `${Math.min(100, Math.max(0, j.percent))}%` }}
            />
          </div>
          {j.hint ? (
            <p className="text-[10px] leading-snug text-muted-foreground">{j.hint}</p>
          ) : null}
          <div className="flex flex-col justify-center gap-3 sm:flex-row">
            {j.paused ? (
              <button type="button" onClick={() => jobControls.resume()} className="btn-primary px-6 py-2.5 text-sm">
                Continue
              </button>
            ) : (
              <button type="button" onClick={() => jobControls.pause()} className="btn-outline px-6 py-2.5 text-sm">
                Pause
              </button>
            )}
            <button type="button" onClick={() => jobControls.stop()} className="btn-outline px-6 py-2.5 text-sm">
              Stop
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
