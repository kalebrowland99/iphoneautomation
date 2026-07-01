"use client";

import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { BAD_LABELY_SCORE, BAD_LABELY_VERDICT, MAX_BAD_LABELY_SCORE, MIN_BAD_LABELY_SCORE, clampLabelyScore } from "@/lib/labelyRating";

const IPHONE_SCALE = 1080 / 390;

/**
 * Colors sampled 1:1 from the Figma export (JPEG in repo assets).
 * Page bg / neutrals / pantry / share / mint card edge taken from pixel averages.
 */
const C = {
  pageBg: "#F4F0E6",
  cardBg: "#FFFFFF",
  title: "#1A1A1A",
  textMuted: "#8E8E93",
  textBody: "#3C3C43",
  /** Share pill — cool light gray */
  shareBg: "#EFEFEF",
  shareBorder: "#DCDCE0",
  shareIcon: "#5C5C5C",
  /** Add to Pantry — sage green */
  pantryBorderSage: "#6B9080",
  pantryBgSage: "#EEF4F0",
  pantryTextSage: "#3D5C4E",
  /** Lawsuits badge — warm brown (pairs with wordmark) */
  lawsuitBorder: "#8B5A2B",
  lawsuitBg: "#FAF4EF",
  lawsuitText: "#5C3D1E",
  /** Analysis card — white + pale mint edge / glow */
  cardBorderMint: "#C9E8DE",
  cardShadowMint: "0 4px 28px rgba(122, 195, 170, 0.28)",
  /** Thrifty / Valcoin app wordmark — ThriftySlide `brand.appLower` */
  wordmarkFont: `Georgia, "Times New Roman", serif`,
  wordmarkColor: "#7B4F2E",
  /** Onboarding-ish green button */
  ctaBg: "#2F5A41",
  ctaText: "#F6F2E9",
};

/** Full-frame slide bg — `public/labely/bg.png`. */
const LABELY_PAGE_BG_URL = "/labely/bg.png";
const LABELY_ICON_SEED_OILS = "/labely/seedoils.png";
const LABELY_ICON_ADDITIVES = "/labely/additives.png";
const LABELY_ICON_HERB = "/labely/herb.png";
function LabelyRowLeadingIcon({ src, size }) {
  return (
    <img
      src={src}
      alt=""
      draggable={false}
      style={{
        width: size,
        height: size,
        flexShrink: 0,
        objectFit: "contain",
        display: "block",
      }}
    />
  );
}

/** Chevron for metric rows (reads as dropdown affordance; decorative only). */
function LabelyMetricDropdownChevron({ size }) {
  const s = Math.max(12, Math.round(size));
  return (
    <svg
      width={s}
      height={s}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
      style={{ flexShrink: 0, display: "block" }}
    >
      <path
        d="M7 10l5 5 5-5"
        stroke="#8E8E93"
        strokeWidth="2.25"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Visible summary lines (clip + measure target). */
const LABELY_SUMMARY_VISIBLE_LINES = 2;

const READ_MORE_SUFFIX = " Read more..";

function LawsuitBubbleInner({ px }) {
  const hereStyle = {
    textDecoration: "underline",
    textUnderlineOffset: px(2),
    textDecorationThickness: Math.max(1, px(1)),
  };
  return (
    <>
      ⚠️ Lawsuits found. Tap <span style={hereStyle}>here</span> to view full report.
    </>
  );
}

/** Renders **bold** in analysis as strong (plain text otherwise). */
function AnalysisBody({ text, px }) {
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
    <span
      style={{
        fontSize: px(13),
        lineHeight: 1.15,
        color: C.textBody,
        whiteSpace: "pre-line",
      }}
    >
      {parts.map((p, i) => {
        if (!p.bold) {
          return <span key={i}>{p.s.replace(/\*\*/g, "")}</span>;
        }
        return (
          <strong key={i} style={{ color: C.title, fontWeight: 700, lineHeight: 1.15 }}>
            {p.s}
          </strong>
        );
      })}
    </span>
  );
}

/**
 * Measure rendered height off-screen. Must not use flushSync during React layout — defer read after commit.
 */
function measureLabelyAnalysisBlockHeight({ markdown, widthPx, pxFn, withReadMore }) {
  if (typeof document === "undefined") return Promise.resolve(0);
  const w = Math.max(0, Math.floor(widthPx));
  const host = document.createElement("div");
  host.style.cssText = [
    "position:fixed",
    "left:-10000px",
    "top:0",
    `width:${w}px`,
    "visibility:hidden",
    "pointer-events:none",
    "font-family:Arial, Helvetica, sans-serif",
  ].join(";");
  document.body.appendChild(host);
  const root = createRoot(host);
  root.render(
    <span style={{ display: "block", wordBreak: "break-word" }}>
      <AnalysisBody text={markdown} px={pxFn} />
      {withReadMore ? (
        <strong style={{ fontWeight: 700, color: C.textBody, fontSize: pxFn(13), lineHeight: 1.15 }}>
          {READ_MORE_SUFFIX}
        </strong>
      ) : null}
    </span>
  );

  const cleanupAndResolve = (resolve, heightRead) => {
    try {
      root.unmount();
    } catch {
      /* ignore */
    }
    host.remove();
    resolve(heightRead);
  };

  return new Promise((resolve) => {
    queueMicrotask(() => {
      let h = host.scrollHeight;
      if (h > 0) {
        cleanupAndResolve(resolve, h);
        return;
      }
      requestAnimationFrame(() => {
        h = host.scrollHeight;
        cleanupAndResolve(resolve, h);
      });
    });
  });
}

function hashUnit(seed, id) {
  const h = (Math.imul((seed | 0) ^ 0x9e3779b9, 2654435761) ^ Math.imul((id + 1) * 40503, 2246822519)) >>> 0;
  return h / 0xffffffff;
}

function productImageStyle(config, itemIndex) {
  const seed = (config?.jitterSeed ?? 0) + itemIndex * 9973;
  const scale = 1.012 + hashUnit(seed, 1) * 0.022;
  const tx = (hashUnit(seed, 2) - 0.5) * 2.4;
  const ty = (hashUnit(seed, 3) - 0.5) * 2.4;
  const brightness = 0.975 + hashUnit(seed, 4) * 0.05;
  const contrast = 0.975 + hashUnit(seed, 5) * 0.05;
  const saturation = 0.965 + hashUnit(seed, 6) * 0.08;
  const hue = (hashUnit(seed, 7) - 0.5) * 4;
  return {
    transform: `translate(${tx.toFixed(2)}%, ${ty.toFixed(2)}%) scale(${scale.toFixed(4)})`,
    filter: `brightness(${brightness.toFixed(3)}) contrast(${contrast.toFixed(3)}) saturate(${saturation.toFixed(3)}) hue-rotate(${hue.toFixed(2)}deg)`,
  };
}

/** Keyed by `analysisRaw` so truncation state resets per slide; inline bold Read more always shown. */
function LabelyAnalysisBlurb({ analysisRaw, px, S }) {
  const summaryLineHeightPx = Math.ceil(px(13) * 1.15);
  const summaryBodyMaxHeight = summaryLineHeightPx * LABELY_SUMMARY_VISIBLE_LINES;
  const analysisWidthRef = useRef(null);
  const [displayAnalysis, setDisplayAnalysis] = useState(analysisRaw);
  const [readMore, setReadMore] = useState(true);

  useLayoutEffect(() => {
    const wrap = analysisWidthRef.current;
    if (!wrap) return;
    let cancelled = false;
    let generation = 0;

    const run = async () => {
      const g = ++generation;
      const pxFn = (n) => Math.round(n * IPHONE_SCALE * S);
      const lineH = Math.ceil(pxFn(13) * 1.15);
      const maxH = lineH * LABELY_SUMMARY_VISIBLE_LINES;
      const widthPx = wrap.clientWidth;
      if (widthPx <= 0) return;

      const stale = () => cancelled || g !== generation;

      const tol = 2;
      const hFullWithReadMore = await measureLabelyAnalysisBlockHeight({
        markdown: analysisRaw,
        widthPx,
        pxFn,
        withReadMore: true,
      });
      if (stale()) return;
      if (hFullWithReadMore <= maxH + tol) {
        setDisplayAnalysis(analysisRaw);
        setReadMore(true);
        return;
      }

      const tokens = analysisRaw.split(/(\s+)/u).filter((x) => x.length > 0);
      let lo = 1;
      let hi = tokens.length;
      let best = "";
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        const cand = tokens.slice(0, mid).join("").trimEnd();
        const h = await measureLabelyAnalysisBlockHeight({
          markdown: cand,
          widthPx,
          pxFn,
          withReadMore: true,
        });
        if (stale()) return;
        if (h <= maxH + tol) {
          best = cand;
          lo = mid + 1;
        } else {
          hi = mid - 1;
        }
      }

      if (!best.trim()) {
        let fallback = analysisRaw.trimEnd();
        while (fallback.length > 1) {
          fallback = fallback.slice(0, Math.max(0, fallback.length - 1)).trimEnd();
          const h = await measureLabelyAnalysisBlockHeight({
            markdown: fallback,
            widthPx,
            pxFn,
            withReadMore: true,
          });
          if (stale()) return;
          if (h <= maxH + tol) break;
        }
        best = fallback;
      }

      if (stale()) return;
      setDisplayAnalysis(best.trimEnd() || analysisRaw.slice(0, 24));
      setReadMore(true);
    };

    void run();
    const ro = new ResizeObserver(() => {
      void run();
    });
    ro.observe(wrap);
    document.fonts?.ready?.then(() => {
      void run();
    })?.catch(() => {});
    return () => {
      cancelled = true;
      ro.disconnect();
    };
  }, [analysisRaw, S]);

  return (
    <div
      ref={analysisWidthRef}
      style={{
        flexShrink: 0,
        marginTop: px(4),
        maxHeight: summaryBodyMaxHeight,
        overflow: "hidden",
        wordBreak: "break-word",
      }}
    >
      <AnalysisBody text={displayAnalysis} px={px} />
      {readMore ? (
        <strong style={{ fontWeight: 700, color: C.textBody, fontSize: px(13), lineHeight: 1.15 }}>
          {READ_MORE_SUFFIX}
        </strong>
      ) : null}
    </div>
  );
}

export default function LabelySlide({ slot, S, config, itemIndex = 0 }) {
  const W = Math.round(1080 * S);
  const H = Math.round(1920 * S);
  const px = (n) => Math.round(n * IPHONE_SCALE * S);
  const gutter = px(22);

  const name = (slot.itemName || "").trim() || "Product";
  const brand = (slot.labelyBrand || "").trim();
  const storedScore = clampLabelyScore(slot.labelyScore);
  const score = storedScore >= MIN_BAD_LABELY_SCORE && storedScore <= MAX_BAD_LABELY_SCORE ? storedScore : BAD_LABELY_SCORE;
  const verdict = BAD_LABELY_VERDICT;
  const analysisRaw =
    (slot.labelyAnalysis || "").trim()
    || "Generate this slide from the sidebar to add a clean-ingredient analysis.";
  const seedOils = "Dangerous";
  const additives = "Dangerous";
  const productThumb = px(100);
  const productStyle = productImageStyle(config, itemIndex);
  const lawsuitBubbleStyle = {
    alignSelf: "center",
    display: "block",
    width: "fit-content",
    maxWidth: "100%",
    textAlign: "center",
    flexShrink: 0,
    borderRadius: px(999),
    padding: `${px(8)}px ${px(16)}px`,
    background: "#FFF9E6",
    border: `${Math.max(1, px(1))}px solid #F2D26B`,
    fontSize: px(11),
    fontWeight: 700,
    color: "#5C4A12",
    lineHeight: 1.25,
    whiteSpace: "normal",
    boxShadow: `0 ${px(2)}px ${px(6)}px rgba(0,0,0,0.06)`,
  };

  return (
    <div
      style={{
        width: W,
        height: H,
        backgroundColor: C.pageBg,
        backgroundImage: `url(${LABELY_PAGE_BG_URL})`,
        backgroundSize: "cover",
        backgroundPosition: "center center",
        backgroundRepeat: "no-repeat",
        overflow: "hidden",
        position: "relative",
        fontFamily: "Arial, Helvetica, sans-serif",
        display: "flex",
        flexDirection: "column",
        color: C.title,
      }}
    >
      <div style={{ flexShrink: 0, paddingLeft: gutter, paddingRight: gutter, paddingTop: px(104) }}>
        <div style={{ paddingLeft: px(10), paddingRight: px(10) }}>
          <div style={{ display: "flex", alignItems: "center", gap: px(14) }}>
            <div
              style={{
                width: productThumb,
                height: productThumb,
                borderRadius: px(22),
                overflow: "hidden",
                background: "#ffffff",
                boxShadow: `0 ${px(6)}px ${px(18)}px rgba(0,0,0,0.10)`,
                flexShrink: 0,
              }}
            >
              {slot.imageUrl ? (
                <img
                  src={slot.imageUrl}
                  alt=""
                  style={{
                    width: "100%",
                    height: "100%",
                    objectFit: "cover",
                    objectPosition: "center",
                    display: "block",
                    transformOrigin: "center",
                    ...productStyle,
                  }}
                />
              ) : (
                <div style={{ width: "100%", height: "100%", background: "linear-gradient(145deg,#e8e3d8,#f8f5ee)" }} />
              )}
            </div>

            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: px(20), fontWeight: 700, color: C.title, lineHeight: 1.15, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
                {name}
              </div>
              {brand ? (
                <div style={{ marginTop: px(4), fontSize: px(14), color: C.textMuted, lineHeight: 1.1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {brand}
                </div>
              ) : null}

              <div style={{ marginTop: px(10), display: "flex", alignItems: "center", gap: px(8) }}>
                <div style={{ fontSize: px(16), fontWeight: 800, color: "#2F5A41", fontVariantNumeric: "tabular-nums" }}>
                  {score}/100
                </div>
                <div style={{ fontSize: px(14), color: "#2F5A41", fontWeight: 600 }}>
                  {verdict === "Great" ? "Excellent" : verdict}
                </div>
                <span style={{ width: px(10), height: px(10), borderRadius: "50%", background: "#E54D42", display: "inline-block", flexShrink: 0 }} />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
          paddingLeft: gutter,
          paddingRight: gutter,
          paddingBottom: px(28),
        }}
      >
        <div style={{ flexShrink: 0, marginTop: px(16), paddingLeft: px(10), paddingRight: px(10), display: "flex", flexDirection: "column" }}>
          <div
            style={{
              flexShrink: 0,
              background: "#ffffff",
              borderRadius: px(18),
              paddingTop: px(8),
              paddingLeft: px(16),
              paddingRight: px(16),
              paddingBottom: px(10),
              boxShadow: "0 8px 22px rgba(0,0,0,0.06)",
              border: "1px solid rgba(0,0,0,0.04)",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            }}
          >
            {/* Logo: explicit px box — avoids flex/inline-img quirks so resize reliably affects exports */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                lineHeight: 0,
                height: px(56),
              }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/labely/labely-logo2.png"
                alt="Labely"
                draggable={false}
                style={{
                  height: px(56),
                  width: "auto",
                  maxHeight: px(56),
                  maxWidth: "92%",
                  display: "block",
                  flexShrink: 0,
                  objectFit: "contain",
                }}
              />
            </div>
            <LabelyAnalysisBlurb key={analysisRaw} analysisRaw={analysisRaw} px={px} S={S} />
          </div>
        </div>

        <div style={{ flexShrink: 0, marginTop: px(18), paddingLeft: px(10), paddingRight: px(10), display: "flex", flexDirection: "column", gap: px(12) }}>
          <span style={lawsuitBubbleStyle}>
            <LawsuitBubbleInner px={px} />
          </span>
          {/* Healthier alternatives reveal */}
          <div style={{ background: "#ffffff", borderRadius: px(14), padding: `${px(12)}px ${px(14)}px`, display: "flex", alignItems: "center", justifyContent: "space-between", border: "1px solid rgba(0,0,0,0.04)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: px(10), minWidth: 0 }}>
              <LabelyRowLeadingIcon src={LABELY_ICON_HERB} size={px(36)} />
              <div style={{ fontSize: px(14), fontWeight: 700, color: "#274B36", lineHeight: 1.2 }}>
                Reveal Healthier Alternatives
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
              <LabelyMetricDropdownChevron size={px(20)} />
            </div>
          </div>

          {/* Seed oils */}
          <div style={{ background: "#ffffff", borderRadius: px(14), padding: `${px(12)}px ${px(14)}px`, display: "flex", alignItems: "center", justifyContent: "space-between", border: "1px solid rgba(0,0,0,0.04)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: px(10), minWidth: 0 }}>
              <LabelyRowLeadingIcon src={LABELY_ICON_SEED_OILS} size={px(36)} />
              <div style={{ fontSize: px(15), fontWeight: 700, color: "#274B36" }}>
                Seed Oils
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: px(10), flexShrink: 0 }}>
              <div style={{ padding: `${px(6)}px ${px(12)}px`, borderRadius: px(999), background: "#FFE9E2", color: "#B23A2D", fontSize: px(12), fontWeight: 700, display: "inline-flex", alignItems: "center", gap: px(4) }}>
                <span>{seedOils}</span>
                <span aria-hidden>⚠️</span>
              </div>
              <LabelyMetricDropdownChevron size={px(20)} />
            </div>
          </div>

          {/* Additives */}
          <div style={{ background: "#ffffff", borderRadius: px(14), padding: `${px(12)}px ${px(14)}px`, display: "flex", alignItems: "center", justifyContent: "space-between", border: "1px solid rgba(0,0,0,0.04)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: px(10), minWidth: 0 }}>
              <LabelyRowLeadingIcon src={LABELY_ICON_ADDITIVES} size={px(36)} />
              <div style={{ fontSize: px(15), fontWeight: 700, color: "#274B36" }}>
                Additives
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: px(10), flexShrink: 0 }}>
              <div style={{ padding: `${px(6)}px ${px(12)}px`, borderRadius: px(999), background: "#FFE9E2", color: "#B23A2D", fontSize: px(12), fontWeight: 700, display: "inline-flex", alignItems: "center", gap: px(4) }}>
                <span>{additives}</span>
                <span aria-hidden>⚠️</span>
              </div>
              <LabelyMetricDropdownChevron size={px(20)} />
            </div>
          </div>
        </div>
      </div>

    </div>
  );
}
