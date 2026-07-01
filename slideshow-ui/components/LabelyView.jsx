"use client";

import { useCallback, useMemo, useState, Fragment } from "react";
import { getLabelyLawsuitBadgeLabel } from "@/lib/labelyLawsuitBadge";
import {
  fileToDisplayableDataUrl,
  isLikelyRasterImageFile,
  IMAGE_FILE_ACCEPT,
} from "@/lib/fileToDisplayableDataUrl";
import { BAD_LABELY_SCORE, BAD_LABELY_VERDICT, MAX_BAD_LABELY_SCORE, MIN_BAD_LABELY_SCORE, clampLabelyScore, ratingLabelFromScore } from "@/lib/labelyRating";

/** Score dot + default verdict label */
function scoreTheme(score) {
  const s = clampLabelyScore(score);
  if (s <= 30) return { dot: "bg-[#E54D42]", verdict: ratingLabelFromScore(s) };
  if (s <= 45) return { dot: "bg-[#FF6B35]", verdict: ratingLabelFromScore(s) };
  if (s <= 60) return { dot: "bg-[#FFB01A]", verdict: ratingLabelFromScore(s) };
  if (s <= 80) return { dot: "bg-[#9CCC65]", verdict: ratingLabelFromScore(s) };
  return { dot: "bg-[#34C759]", verdict: ratingLabelFromScore(s) };
}

function ShareIcon({ className }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M12 3v10"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M8.5 6.5 12 3l3.5 3.5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function SaveBookmarkIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M7 3h10a2 2 0 012 2v16l-7-4-7 4V5a2 2 0 012-2z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Renders `**bold**` in analysis text (same convention as LabelySlide). */
function AnalysisSummary({ text, className }) {
  const parts = useMemo(() => {
    const t = text || "";
    const out = [];
    const re = /\*\*([^*]+)\*\*/g;
    let last = 0;
    let m;
    while ((m = re.exec(t)) !== null) {
      if (m.index > last) out.push({ bold: false, s: t.slice(last, m.index) });
      out.push({ bold: true, s: m[1] });
      last = m.index + m[0].length;
    }
    if (last < t.length) out.push({ bold: false, s: t.slice(last) });
    return out.length ? out : [{ bold: false, s: t }];
  }, [text]);

  return (
    <p className={className}>
      {parts.map((p, i) =>
        p.bold ? (
          <strong key={i} className="font-bold text-[#1A1A1A]">
            {p.s}
          </strong>
        ) : (
          <Fragment key={i}>{p.s}</Fragment>
        )
      )}
    </p>
  );
}

const emptyLabely = {
  name: "",
  brand: "",
  score: BAD_LABELY_SCORE,
  verdict: BAD_LABELY_VERDICT,
  analysis: "",
  imageDataUrl: null,
};

/**
 * @param {{ fillViewport?: boolean }} props
 * fillViewport: true for standalone /labely (full viewport height); false when embedded in the main app layout.
 */
export default function LabelyView({ fillViewport = true }) {
  const [data, setData] = useState(emptyLabely);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const displayScore = useMemo(() => {
    const s = clampLabelyScore(data?.score);
    return s >= MIN_BAD_LABELY_SCORE && s <= MAX_BAD_LABELY_SCORE ? s : BAD_LABELY_SCORE;
  }, [data?.score]);
  const theme = useMemo(() => scoreTheme(displayScore), [displayScore]);

  const lawsuitBadgeLabel = useMemo(
    () =>
      getLabelyLawsuitBadgeLabel(
        `${data?.name ?? ""}|${data?.brand ?? ""}|${data?.score ?? 0}`
      ),
    [data?.name, data?.brand, data?.score]
  );

  const analyzeDataUrl = useCallback(async (imageDataUrl, uploadHint) => {
    setBusy(true);
    setError("");
    try {
      const hint =
        typeof uploadHint === "string" && uploadHint.trim()
          ? uploadHint.trim().slice(0, 160)
          : "";
      const res = await fetch("/api/labely", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          imageDataUrl,
          ...(hint ? { uploadHint: hint } : {}),
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json?.error || "Analysis failed");
      setData((prev) => ({
        ...prev,
        ...json,
        imageDataUrl: imageDataUrl || prev.imageDataUrl,
      }));
    } catch (e) {
      console.error("[labely] analyze failed", e);
      setError(e?.message || "Could not analyze image.");
    } finally {
      setBusy(false);
    }
  }, []);

  const onPickFile = useCallback(
    (e) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!isLikelyRasterImageFile(file)) return;
      void (async () => {
        try {
          const url = await fileToDisplayableDataUrl(file);
          await analyzeDataUrl(url, file.name);
        } catch (err) {
          console.error("[labely] file read failed", err);
          setError(err?.message || "Could not read this photo (try JPEG or HEIC).");
        }
      })();
    },
    [analyzeDataUrl]
  );

  const shell = fillViewport
    ? "min-h-screen flex items-center justify-center bg-[#F9F9F9] px-[22px] py-10 text-[#1A1A1A]"
    : "flex min-h-full w-full items-center justify-center bg-[#F9F9F9] px-[22px] py-10 text-[#1A1A1A]";

  return (
    <div className={shell}>
      <div className="w-full max-w-[420px]">
        <div className="mb-14 rounded-xl border border-dashed border-[#C9E8DE] bg-white/80 px-4 py-3">
          <label className="block text-[11px] font-semibold text-[#3D5C4E] mb-2">
            Upload a product photo
          </label>
          <input
            type="file"
            accept={IMAGE_FILE_ACCEPT}
            disabled={busy}
            onChange={onPickFile}
            className="w-full text-[11px] text-[#5C5C5C] file:mr-2 file:rounded-lg file:border-0 file:bg-[#EEF4F0] file:px-3 file:py-2 file:text-[12px] file:font-semibold file:text-[#3D5C4E]"
          />
          <p className="mt-2 text-[10px] leading-relaxed text-[#8E8E93]">
            Full slideshow editing lives in the main app: choose <strong className="text-[#5C5C5C]">Labely</strong> in the
            top-left menu, then upload photos or use AI-generated products in the sidebar.
          </p>
          {busy ? <p className="mt-2 text-[11px] text-[#6B9080]">Analyzing packaging…</p> : null}
          {error ? <p className="mt-2 text-[11px] status-error">{error}</p> : null}
        </div>

        <div className="flex items-start gap-4">
          <div className="relative h-[118px] w-[118px] shrink-0 overflow-hidden rounded-2xl bg-black shadow-[0_6px_16px_rgba(0,0,0,0.12)]">
            {data?.imageDataUrl ? (
              <img
                src={data.imageDataUrl}
                alt=""
                className="pointer-events-none block h-full w-full object-cover object-center"
              />
            ) : (
              <div className="h-full w-full bg-gradient-to-br from-zinc-800 to-black" />
            )}
          </div>

          <div className="relative min-w-0 flex-1 pt-0.5">
            <button
              type="button"
              className="absolute bottom-0 right-0 top-auto flex h-9 shrink-0 items-center gap-1.5 rounded-full border border-[#DCDCE0] bg-[#EFEFEF] px-3.5"
              aria-label="Share"
            >
              <span className="whitespace-nowrap text-[12px] font-semibold tracking-[0.08em] text-[#5C5C5C]">
                SHARE
              </span>
              <ShareIcon className="h-5 w-5 text-[#5C5C5C]" />
            </button>
            <h1 className="line-clamp-2 break-words text-[22px] font-bold leading-snug tracking-tight text-[#1A1A1A]">
              {data?.name || "Product name"}
            </h1>
            {(data?.brand ?? "").trim() ? (
              <p className="mt-1.5 line-clamp-2 break-words text-[16px] font-normal tracking-wide text-[#8E8E93]">
                {data?.brand}
              </p>
            ) : null}

            <div className="mt-4 flex max-w-full items-start gap-1 pr-[6.5rem]">
              <span
                className={`mt-[0.28em] h-3 w-3 shrink-0 rounded-full ${theme.dot}`}
                aria-hidden="true"
              />
              <div className="flex min-w-0 flex-col gap-px leading-none">
                <span className="text-[20px] font-semibold tabular-nums tracking-tight text-[#1A1A1A]">
                  {displayScore}/100
                </span>
                <span className="text-[12px] font-normal leading-none text-[#8E8E93]">
                  {BAD_LABELY_VERDICT}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-[22px] flex w-full items-center gap-2.5">
          <button
            type="button"
            disabled
            className="flex h-11 shrink-0 cursor-default items-center justify-center gap-2 rounded-full border-2 border-[#6B9080] bg-[#EEF4F0] px-5 text-[15px] font-bold tracking-wide text-[#3D5C4E] opacity-90"
          >
            <span>Add to Pantry</span>
            <SaveBookmarkIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
          </button>
          <div className="flex h-11 min-w-0 flex-1 cursor-default items-center justify-center rounded-full border-2 border-[#8B5A2B] bg-[#FAF4EF] px-4 text-[13px] font-bold tracking-wide text-[#5C3D1E]">
            <span className="min-w-0 truncate">{lawsuitBadgeLabel}</span>
          </div>
        </div>

        <div className="mt-6 rounded-[20px] border border-[#C9E8DE] bg-white p-[22px] shadow-[0_4px_28px_rgba(122,195,170,0.28)]">
          <div className="flex justify-center">
            <div
              className="text-center text-[32px] font-black leading-[0.95] tracking-tight text-[#7B4F2E]"
              style={{ fontFamily: 'Georgia, "Times New Roman", serif' }}
            >
              labely
            </div>
          </div>

          {data?.analysis?.trim() ? (
            <AnalysisSummary
              text={data.analysis}
              className="mt-4 text-[16px] leading-[1.5] text-[#3C3C43]"
            />
          ) : (
            <p className="mt-4 text-[16px] leading-[1.5] text-[#3C3C43]">
              Upload a clear photo of the front label of a packaged food or drink. Labely reads the name and brand, then
              writes a short label analysis of your product highlighting real concerning ingredients in bold.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
