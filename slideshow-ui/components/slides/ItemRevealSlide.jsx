"use client";

import { useMemo } from "react";
import { tickerBoxCaptionTextStyle, captionWrapperStyle } from "@/lib/captionStyles";
import { captionFontSize1080 } from "@/lib/captionFontSize";
import { getBrand } from "@/lib/brand";
import { numistaDisplaySrc } from "@/lib/numistaImageClient";

// Stable seeded PRNG — same output for same seed, no re-randomisation on re-render
function seededRand(seed) {
  const x = Math.sin(seed + 3.14) * 10000;
  return x - Math.floor(x);
}

// Derive a numeric seed from the slot's content so each slot gets
// consistent (but unique) randomisation that survives export re-renders
function slotSeed(slot) {
  const str = (slot.itemName || "") + (slot.spentPrice || "") + (slot.soldPrice || "");
  let h = 5381;
  for (let i = 0; i < str.length; i++) h = ((h << 5) + h) ^ str.charCodeAt(i);
  return Math.abs(h);
}

export default function ItemRevealSlide({ slot, S, config = {} }) {
  const brand = getBrand(config);
  const captionStyle = config.captionStyle ?? "tiktok";
  const captionBg    = config.captionBg    ?? "#e03030";
  const captionColor = config.captionColor ?? "#ffffff";
  const outputFormat = config.outputFormat ?? "standard";
  const isLabely = (config.appId ?? "thrifty") === "labely";
  const W = Math.round(1080 * S);
  const H = Math.round(1920 * S);
  const px = (n) => Math.round(n * S);

  const showLetsCheckApp =
    !isLabely && (outputFormat === "standard" || outputFormat === "appOnly");

  // All random values derived from a stable seed — same layout every render/export
  const seed = useMemo(() => slotSeed(slot), [slot.itemName, slot.spentPrice, slot.soldPrice]);

  const captionSizePx = useMemo(
    () =>
      captionFontSize1080(`${slot.itemName}|${slot.spentPrice}|${slot.soldPrice}|reveal`),
    [slot.itemName, slot.spentPrice, slot.soldPrice]
  );

  const REVEAL_SAFE_ZONES = [0.06, 0.14, 0.28, 0.42, 0.56, 0.68, 0.76];
  const captionLineH = Math.round(captionSizePx * S * 1.2);
  const captionPadY = Math.round(10 * S) * 2;
  const blankLineGapH = showLetsCheckApp ? captionLineH * 2 : 0;
  const appBoxH = showLetsCheckApp ? captionPadY + captionLineH : 0;
  const captionBoxH = showLetsCheckApp ? blankLineGapH + appBoxH : 0;
  const maxTop = H - captionBoxH - Math.round(H * 0.02);

  const zoneIdx = useMemo(() => Math.floor(seededRand(seed + 1) * REVEAL_SAFE_ZONES.length), [seed]);
  const jitterX = useMemo(() => Math.round((seededRand(seed + 2) - 0.5) * 16 * S),  [seed, S]);
  const jitterY = useMemo(() => Math.round((seededRand(seed + 3) - 0.5) * 16 * S),  [seed, S]);
  const tilt    = useMemo(() => ((seededRand(seed + 4) - 0.5) * 4).toFixed(2),       [seed]); // ±2 deg
  const captionTop = useMemo(() => {
    const raw = Math.round(H * REVEAL_SAFE_ZONES[zoneIdx]) + jitterY;
    return Math.min(raw, maxTop);
  }, [seed, H, maxTop, zoneIdx, jitterY]);

  return (
    <div style={{ width: W, height: H, position: "relative", background: "#000", overflow: "hidden" }}>
      {/* Full-screen image */}
      {slot.imageUrl ? (
        <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
          <img
            src={numistaDisplaySrc(slot.imageUrl)}
            alt={slot.itemName || "Item"}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "contain",
              objectPosition: "center",
              display: "block",
            }}
          />
        </div>
      ) : (
        <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "#1c1c1c" }}>
          <svg width={px(120)} height={px(120)} fill="none" viewBox="0 0 24 24" stroke="rgba(255,255,255,0.12)" strokeWidth={0.8}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        </div>
      )}

      {/* Bottom gradient scrim */}
      <div
        style={{
          position: "absolute",
          bottom: 0, left: 0, right: 0,
          height: "50%",
          background: "linear-gradient(to top, rgba(0,0,0,0.92) 0%, rgba(0,0,0,0.55) 50%, transparent 100%)",
          pointerEvents: "none",
        }}
      />

      {/* Optional “lets check {app}!” for non-Labely */}
      {showLetsCheckApp ? (
        <div
          style={{
            position: "absolute",
            left: 0,
            width: W,
            top: captionTop,
            display: "flex",
            justifyContent: "center",
            pointerEvents: "none",
            zIndex: 10,
          }}
        >
          <div
            style={{
              marginLeft: captionStyle === "tickerBox" ? 0 : jitterX,
              transform: captionStyle === "tickerBox" ? "none" : `rotate(${tilt}deg)`,
              maxWidth: Math.round(W * 0.85),
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
            }}
          >
            {blankLineGapH > 0 ? <div style={{ height: blankLineGapH }} /> : null}
            <div style={{
              ...captionWrapperStyle(S, { captionStyle: "tickerBox", captionBg }),
              padding: `${Math.round(10 * S)}px ${Math.round(20 * S)}px`,
              width: "fit-content",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}>
              <span style={tickerBoxCaptionTextStyle(S, { fontSize: Math.round(captionSizePx * S), fontWeight: "800", color: captionColor })}>
                {`lets check ${brand.appLower}!`}
              </span>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
