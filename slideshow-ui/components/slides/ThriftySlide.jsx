"use client";

import { useMemo } from "react";
import { makeJitter } from "@/lib/jitter";
import { tiktokCaptionTextStyle, tickerBoxCaptionTextStyle, captionWrapperStyle } from "@/lib/captionStyles";
import { captionFontSize1080 } from "@/lib/captionFontSize";
import { getBrand } from "@/lib/brand";
import { numistaDisplaySrc } from "@/lib/numistaImageClient";

/**
 * ThriftySlide — pixel-faithful recreation of SongEditView.
 * Randomizes status-bar (time, signal, wifi, battery) and sold-listing
 * sources on every mount to dodge TikTok duplicate-content filters.
 *
 * Scaling: IPHONE_SCALE = 1080/390 maps iPhone pts → TikTok pixels.
 */

const IPHONE_SCALE = 1080 / 390;

const SOURCES_RESELL = ["eBay", "Poshmark", "Mercari", "Depop", "Grailed", "StockX", "Vestiaire", "thredUP"];
const SOURCES_COINS = [
  "eBay",
  "Heritage Auctions",
  "Stack's Bowers",
  "GreatCollections",
  "APMEX",
  "SD Bullion",
  "JM Bullion",
  "NGC",
  "PCGS",
];
const PREFIXES = ["Pre-owned ", "Used ", "Vintage ", "Authentic ", "Like-New "];
const SUFFIXES = [" - Great Condition", " - Gently Used", " (Pre-loved)", " - Excellent", " - Good Shape"];

// ── Seeded PRNG (stable per mount) ──────────────────────────────────────────
function rand(seed) {
  const x = Math.sin(seed + 1.7) * 10000;
  return x - Math.floor(x);
}

function randInt(seed, min, max) {
  return Math.floor(rand(seed) * (max - min + 1)) + min;
}

// ── Random time string ───────────────────────────────────────────────────────
function randomTime(seed) {
  const h = randInt(seed,     7, 11);
  const m = randInt(seed + 1, 0, 59);
  return `${h}:${String(m).padStart(2, "0")}`;
}

// ── Random past date (within ~8 months before Apr 4 2026) ────────────────────
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function randomPastDate(seed) {
  // Pick a day between 1–240 days before Apr 4, 2026
  const daysBack = randInt(seed + 10, 1, 240);
  const base = new Date(2026, 3, 4);           // Apr 4 2026
  base.setDate(base.getDate() - daysBack);
  const mon = MONTHS[base.getMonth()];
  return `${mon} ${base.getDate()}, ${base.getFullYear()}`;
}

export default function ThriftySlide({ slot, S, config = {} }) {
  const brand = getBrand(config);
  const captionStyle = config.captionStyle ?? "tiktok";
  const captionBg    = config.captionBg    ?? "#e03030";
  const hideCaption =
    (config.outputFormat ?? "standard") === "imessageMom" || brand.appId === "valcoin";
  const captionColor = config.captionColor ?? "#ffffff";
  const W = Math.round(1080 * S);
  const H = Math.round(1920 * S);
  const px = (n) => Math.round(n * IPHONE_SCALE * S);

  // Stable seed derived from slot content — same layout every render & export
  // (no useEffect/Math.random so the output never changes between preview and video)
  const seed = useMemo(() => {
    const str = (slot.itemName || "") + (slot.spentPrice || "") + (slot.soldPrice || "");
    let h = 5381;
    for (let i = 0; i < str.length; i++) h = ((h << 5) + h) ^ str.charCodeAt(i);
    return Math.abs(h) % 9999;
  }, [slot.itemName, slot.spentPrice, slot.soldPrice]);
  const statusBar = useMemo(() => ({
    time:        randomTime(seed),
    signalBars:  randInt(seed + 2, 2, 4),
    wifiStrength:randInt(seed + 3, 1, 3),
    batteryPct:  randInt(seed + 4, 22, 97),
    date:        randomPastDate(seed),
  }), [seed]);

  const sourcesPool = brand.appId === "valcoin" ? SOURCES_COINS : SOURCES_RESELL;

  // Randomise which two sources appear in the sold rows
  const [src1, src2] = useMemo(() => {
    const pool = [...sourcesPool];
    const a = pool.splice(randInt(seed + 5, 0, pool.length - 1), 1)[0];
    const b = pool.splice(randInt(seed + 6, 0, pool.length - 1), 1)[0];
    return [a, b];
  }, [seed, sourcesPool]);

  const soldPrice  = slot.soldPrice ? `$${slot.soldPrice}` : "$—";
  const itemName   = slot.itemName || "Untitled Item";
  const date       = slot.date || statusBar.date;

  // Varied caption phrasings — picked by seed so each slide gets a different one
  const CAPTION_TEMPLATES = [
    (s, r) => `found for $${s} → resell $${r} 💰`,
    (s, r) => `thrifted $${s} · flip for $${r} 🤑`,
    (s, r) => `paid $${s} · listed at $${r} 💸`,
    (s, r) => `scored for $${s} → asking $${r} 🔥`,
    (s, r) => `grabbed for $${s} · (worth $${r}) 💰`,
    (s, r) => `$${s} find → $${r} resale 🏷️`,
    (s, r) => `cost me $${s} · resell $${r} 💵`,
  ];
  const captionText = (() => {
    const sold  = parseFloat(slot.soldPrice);
    const spent = parseFloat(slot.spentPrice);
    if (!isNaN(sold) && !isNaN(spent) && sold > spent) {
      const template = CAPTION_TEMPLATES[randInt(seed + 40, 0, CAPTION_TEMPLATES.length - 1)];
      return template(slot.spentPrice, slot.soldPrice);
    }
    if (slot.soldPrice) return `resell for $${slot.soldPrice} 💰`;
    return null;
  })();

  const captionFontPx = useMemo(
    () => captionFontSize1080(`${slot.itemName}|${slot.spentPrice}|${slot.soldPrice}|thrifty`),
    [slot.itemName, slot.spentPrice, slot.soldPrice]
  );

  // Per-mount jitter + tilt (stable per render, dodges TikTok pattern detection)
  // makeJitter adds a per-generation layer on top of the content-based jitter
  const J = makeJitter(config.jitterSeed ?? 0);
  const captionJitter = useMemo(() => ({
    x:   Math.round((rand(seed + 20) - 0.5) * 16 * S) + J(70, 3),
    y:   Math.round((rand(seed + 21) - 0.5) * 16 * S) + J(71, 3),
    rot: (((rand(seed + 22) - 0.5) * 4) + J(72, 1) * 0.3).toFixed(2),
  }), [seed, S, config.jitterSeed]);

  // Random safe zones — avoids logo (H×0.05-0.18) and price card (H×0.38-0.54)
  // Max zone capped so caption box never overflows the bottom edge
  const THRIFTY_SAFE_ZONES = [0.22, 0.30, 0.60, 0.68, 0.75];
  const captionBoxHeight = Math.round(10 * S) * 2 + Math.round(captionFontPx * S * 1.2);
  const maxCaptionTop = H - captionBoxHeight - Math.round(H * 0.02);
  const rawCaptionTop = Math.round(H * THRIFTY_SAFE_ZONES[randInt(seed + 50, 0, THRIFTY_SAFE_ZONES.length - 1)]) + captionJitter.y;
  const captionTop = Math.min(rawCaptionTop, maxCaptionTop);

  const soldRows = buildSoldRows(slot, src1, src2);

  // Valcoin scan tour renders the SAME full Valcoin app UI below (price card,
  // sold listings, status bar). The scan animation in lib/labelyScanExport.js
  // shows the coin photo + scan beam first, then slides this captured UI up.

  return (
    <div style={{ width: W, height: H, background: "#ffffff", overflow: "hidden",
      position: "relative", fontFamily: "Arial, Helvetica, sans-serif",
      display: "flex", flexDirection: "column" }}>

      {/* Floating caption — flex-centered wrapper avoids calc() in html2canvas */}
      {captionText && !hideCaption && (
        <div style={{
          position: "absolute",
          left: 0,
          width: W,
          top: captionTop,
          display: "flex",
          justifyContent: "center",
          zIndex: 100,
          pointerEvents: "none",
        }}>
          <div style={{
            marginLeft: captionStyle === "tickerBox" ? 0 : captionJitter.x,
            transform: captionStyle === "tickerBox" ? "none" : `rotate(${captionJitter.rot}deg)`,
            ...captionWrapperStyle(S, { captionStyle, captionBg }),
            padding: `${Math.round(10 * S)}px ${Math.round(20 * S)}px`,
            maxWidth: Math.round(W * 0.85),
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}>
            <span style={captionStyle === "tickerBox"
              ? tickerBoxCaptionTextStyle(S, { fontSize: Math.round(captionFontPx * S), fontWeight: "800", color: captionColor })
              : tiktokCaptionTextStyle(S, { fontSize: Math.round(captionFontPx * S), fontWeight: "800" })
            }>
              {captionText}
            </span>
          </div>
        </div>
      )}

      <StatusBar px={px} values={statusBar} />

      {/* ── HEADER ── */}
      <div style={{ background: "#fff", flexShrink: 0,
        paddingLeft: px(20), paddingRight: px(20),
        paddingTop: px(20), paddingBottom: px(20) }}>

        {/* Nav row */}
        <div style={{ display: "flex", alignItems: "center", marginBottom: px(16) }}>
          {/* Back arrow */}
          <div style={{ width: px(44), height: px(44), display: "flex", alignItems: "center" }}>
            <svg width={px(22)} height={px(22)} viewBox="0 0 24 24" fill="none">
              <path d="M19 12H5M5 12l7-7M5 12l7 7" stroke="#111" strokeWidth="2.5"
                strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>

          {/* Center spacer — logo moved to Thrifty Price card */}
          <div style={{ flex: 1, minHeight: px(44) }} />

          {/* Ellipsis */}
          <svg width={px(22)} height={px(22)} viewBox="0 0 24 24" fill="#111">
            <circle cx="5"  cy="12" r="1.8"/>
            <circle cx="12" cy="12" r="1.8"/>
            <circle cx="19" cy="12" r="1.8"/>
          </svg>
        </div>

        {/* Item row: thumbnail + name/date */}
        <div style={{ display: "flex", gap: px(16), alignItems: "flex-start" }}>
          <div style={{ width: px(120), height: px(120), borderRadius: px(16), overflow: "hidden",
            flexShrink: 0, background: "#e8e8e8",
            boxShadow: `0 ${px(2)}px ${px(4)}px rgba(0,0,0,0.1)` }}>
            {slot.imageUrl ? (
              <img src={numistaDisplaySrc(slot.imageUrl)} alt={itemName}
                style={{ width: "100%", height: "100%", objectFit: "contain", objectPosition: "center", display: "block" }} />
            ) : (
              <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center", gap: px(4) }}>
                <svg width={px(32)} height={px(32)} fill="none" viewBox="0 0 24 24" stroke="#bbb" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                <span style={{ color: "#bbb", fontSize: px(10), fontWeight: "500" }}>No photo</span>
              </div>
            )}
          </div>

          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: px(8) }}>
            <div style={{ position: "relative", background: "rgba(0,0,0,0.05)", borderRadius: px(8),
              minHeight: px(46), display: "flex", alignItems: "center",
              paddingTop: px(10), paddingBottom: px(10), paddingLeft: px(12), paddingRight: px(34) }}>
              <span style={{ fontSize: px(18), fontWeight: "700", color: "#000", lineHeight: 1.1, display: "block" }}>
                {itemName}
              </span>
              <svg style={{ position: "absolute", top: "50%", right: px(8), transform: "translateY(-50%)" }}
                width={px(13)} height={px(13)} fill="none" viewBox="0 0 24 24"
                stroke="rgba(0,0,0,0.3)" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
              </svg>
            </div>
            <span style={{ display: "block", fontSize: px(14), fontWeight: "500", color: "#888", lineHeight: 1.15 }}>{date}</span>
          </div>
        </div>

      </div>

      <div style={{ height: px(1), background: "#f0f0f0", flexShrink: 0 }} />

      {/* ── CONTENT ── */}
      <div style={{ flex: 1, background: "rgba(0,0,0,0.03)", overflow: "hidden",
        display: "flex", flexDirection: "column", gap: px(16),
        paddingTop: px(16), paddingBottom: px(16) }}>

          {/* App Price card */}
        <div style={{ background: "#fff", borderRadius: px(12),
          boxShadow: `0 ${px(2)}px ${px(8)}px rgba(0,0,0,0.05)`,
          marginLeft: px(16), marginRight: px(16),
          paddingTop: px(20), paddingBottom: px(20),
          display: "flex", flexDirection: "column", alignItems: "center", gap: px(6) }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: px(44) }}>
            <span style={{
              display: "block",
              fontSize: px(42),
              fontWeight: "900",
              color: "#7B4F2E",
              fontFamily: "Georgia, 'Times New Roman', serif",
              letterSpacing: "-1px",
              lineHeight: 1.02,
            }}>
              {brand.appLower}
            </span>
          </div>
          <span style={{
            display: "block",
            fontSize: px(38),
            fontWeight: "700",
            letterSpacing: "-0.5px",
            lineHeight: 0.96,
            color: slot.soldPrice ? "#000" : "#aaa",
            marginLeft: px(-12),
          }}>
            {soldPrice}
          </span>
        </div>

        {/* Sold card */}
        <div style={{ background: "#fff", borderRadius: px(16),
          boxShadow: `0 ${px(2)}px ${px(8)}px rgba(0,0,0,0.05)`,
          marginLeft: px(16), marginRight: px(16), padding: px(16) }}>

          <div style={{ display: "flex", alignItems: "center", gap: px(8), marginBottom: px(10) }}>
            <svg width={px(18)} height={px(18)} viewBox="0 0 24 24" fill="#ef4444">
              <path d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/>
            </svg>
            <span style={{ fontSize: px(18), fontWeight: "600", color: "#111" }}>Sold</span>
          </div>

          <p style={{ fontSize: px(14), fontWeight: "500", color: "#888", lineHeight: 1.2, margin: `0 0 ${px(8)}px 0` }}>
            Recently Sold on {src1}, {src2}{" "}&amp; more:
          </p>

          {soldRows.map((row, i) => (
            <SoldRow key={i} row={row}
              last={i === soldRows.length - 1} px={px} />
          ))}

          {soldRows.some((r) => r.price) && (
            <>
              <div style={{ height: px(1), background: "#f0f0f0", margin: `${px(6)}px 0` }} />
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: px(14), fontWeight: "500", color: "#888" }}>
                  Sold Average ({soldRows.filter((r) => r.price).length} items):
                </span>
                <span style={{ fontSize: px(16), fontWeight: "700", color: "#ef4444" }}>
                  {(() => {
                    const prices = soldRows.filter((r) => r.price).map((r) => parseFloat(r.price)).filter((v) => !isNaN(v));
                    if (!prices.length) return "N/A";
                    return `$${(prices.reduce((a, b) => a + b, 0) / prices.length).toFixed(2)}`;
                  })()}
                </span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Build sold rows ──────────────────────────────────────────────────────────
function buildSoldRows(slot, src1, src2) {
  const filled = slot.matchItems?.filter((m) => m.title || m.price) ?? [];
  if (filled.length >= 2) {
    // Override sources with the randomised ones
    return [
      { ...filled[0], source: src1, inStock: false },
      { ...filled[1], source: src2, inStock: false },
    ];
  }
  const base  = slot.itemName || "";
  const price = parseFloat(slot.soldPrice);
  const makeRow = (seed, src) => ({
    title:   base
      ? `${PREFIXES[seed % PREFIXES.length]}${base}${SUFFIXES[(seed + 1) % SUFFIXES.length]}`
      : `Sold listing ${seed + 1}`,
    source:  src,
    price:   isNaN(price) ? "" : String(Math.round(price * (seed % 2 === 0 ? 0.88 : 1.08))),
    inStock: false,
  });
  return [
    filled[0] ? { ...filled[0], source: src1, inStock: false } : makeRow(0, src1),
    filled[1] ? { ...filled[1], source: src2, inStock: false } : makeRow(1, src2),
  ];
}

// ── iOS Status Bar — fully random ────────────────────────────────────────────
function StatusBar({ px, values }) {
  const { time, signalBars, wifiStrength, batteryPct } = values;
  const batteryFill = Math.round((batteryPct / 100) * 15); // 0-15px fill width
  const batteryColor = batteryPct < 25 ? "#ef4444" : "#111";

  return (
    <div style={{ height: px(44), background: "#fff", display: "flex", alignItems: "center",
      justifyContent: "space-between", paddingLeft: px(24), paddingRight: px(24), flexShrink: 0 }}>
      <span style={{ fontSize: px(15), fontWeight: "700", color: "#111" }}>{time}</span>
      <div style={{ display: "flex", alignItems: "center", gap: px(5) }}>

        {/* Signal bars — show signalBars out of 4 */}
        <svg width={px(17)} height={px(12)} viewBox="0 0 18 12" fill="none">
          <rect x="0" y="8" width="3" height="4" rx="0.5" fill={signalBars >= 1 ? "#111" : "rgba(0,0,0,0.2)"}/>
          <rect x="5" y="5" width="3" height="7" rx="0.5" fill={signalBars >= 2 ? "#111" : "rgba(0,0,0,0.2)"}/>
          <rect x="10" y="2" width="3" height="10" rx="0.5" fill={signalBars >= 3 ? "#111" : "rgba(0,0,0,0.2)"}/>
          <rect x="15" y="0" width="3" height="12" rx="0.5" fill={signalBars >= 4 ? "#111" : "rgba(0,0,0,0.2)"}/>
        </svg>

        {/* WiFi — show wifiStrength arcs out of 3 */}
        <svg width={px(15)} height={px(11)} viewBox="0 0 20 13" fill="none">
          <path d="M10 11.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3z"
            fill={wifiStrength >= 1 ? "#111" : "rgba(0,0,0,0.2)"}/>
          <path d="M6.2 8.2C7.3 7.1 8.6 6.5 10 6.5s2.7.6 3.8 1.7"
            stroke={wifiStrength >= 2 ? "#111" : "rgba(0,0,0,0.2)"}
            strokeWidth="1.5" strokeLinecap="round" fill="none"/>
          <path d="M3 5C5.1 2.9 7.4 1.8 10 1.8s4.9 1.1 7 3.2"
            stroke={wifiStrength >= 3 ? "#111" : "rgba(0,0,0,0.2)"}
            strokeWidth="1.5" strokeLinecap="round" fill="none"/>
        </svg>

        {/* Battery — variable fill */}
        <svg width={px(25)} height={px(12)} viewBox="0 0 25 12" fill="none">
          {/* Shell */}
          <rect x="0.5" y="0.5" width="21" height="11" rx="3.5" stroke="#111" strokeWidth="1"/>
          {/* Fill */}
          <rect x="1.5" y="1.5" width={batteryFill} height="9" rx="2.5" fill={batteryColor}/>
          {/* Nub */}
          <path d="M23 4v4" stroke="#111" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
      </div>
    </div>
  );
}

// ── Sold listing row ─────────────────────────────────────────────────────────
function SoldRow({ row, last, px }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: px(8),
      paddingTop: px(6), paddingBottom: px(6),
      borderBottom: last ? "none" : `${px(1)}px solid #f5f5f5` }}>

      {/* Thumbnail — grey placeholder box */}
      <div style={{ width: px(80), height: px(80), borderRadius: px(8), overflow: "hidden",
        flexShrink: 0, background: "#e8e8e8",
        display: "flex", alignItems: "center", justifyContent: "center" }}>
        <svg width={px(28)} height={px(28)} fill="none" viewBox="0 0 24 24" stroke="#bbb" strokeWidth={1.2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
      </div>

      {/* Title + source */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ display: "block", fontSize: px(14), fontWeight: "500", color: "#000",
          lineHeight: 1.15, margin: `0 0 ${px(4)}px`, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {row.title || "Sold listing"}
        </p>
        <div style={{ display: "flex", gap: px(6) }}>
          <span style={{ fontSize: px(12), color: "#3b82f6" }}>{row.source || "eBay"}</span>
          <span style={{ fontSize: px(12), color: "#ef4444", fontWeight: "500" }}>• Sold</span>
        </div>
      </div>

      {/* Price + chevron */}
      <div style={{ display: "flex", alignItems: "center", gap: px(3), flexShrink: 0 }}>
        <span style={{ fontSize: px(15), fontWeight: "700", color: "#000" }}>
          {row.price ? `$${row.price}` : "—"}
        </span>
        <svg width={px(11)} height={px(11)} viewBox="0 0 24 24" fill="none"
          stroke="rgba(0,0,0,0.25)" strokeWidth="2.5">
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 18l6-6-6-6"/>
        </svg>
      </div>
    </div>
  );
}
