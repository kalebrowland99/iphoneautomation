"use client";

import { useMemo } from "react";
import { makeJitter } from "@/lib/jitter";
import { getBrand } from "@/lib/brand";

/**
 * iOS iMessage long-press screenshot — dark mode.
 * Sizes in iPhone pts (390pt wide), scaled by IPHONE_SCALE * S.
 */

const IPHONE_SCALE = 1080 / 390;
const IOS_BLUE = "#007AFF";
const FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", system-ui, sans-serif';

function slotSeed(slot) {
  const str = (slot?.itemName || "") + (slot?.spentPrice || "") + (slot?.soldPrice || "");
  let h = 5381;
  for (let i = 0; i < str.length; i++) h = ((h << 5) + h) ^ str.charCodeAt(i);
  return Math.abs(h);
}

function seededRand(seed, i = 0) {
  const x = Math.sin(seed * 0.001 + i * 12.9898) * 10000;
  return x - Math.floor(x);
}

/** Blurred fake iMessage thread (blue + grey bubbles) — layout varies by seed. */
function IMessageThreadBackdrop({ seed, px }) {
  const variant = seed % 5;
  const baseGrad = [
    "linear-gradient(165deg, #0a0a0f 0%, #12121a 40%, #0d1520 100%)",
    "linear-gradient(180deg, #08080c 0%, #141820 55%, #0a1018 100%)",
    "linear-gradient(195deg, #0c0c12 0%, #101820 45%, #0e1420 100%)",
    "linear-gradient(170deg, #0a0b10 0%, #121a24 50%, #0b121c 100%)",
    "linear-gradient(180deg, #09090e 0%, #0f1620 40%, #0a121c 100%)",
  ][variant];

  const blueTints = ["#0A84FF", "#2B95FF", "#1a7fe0", "#3d8fd9", "#0070e0"];
  const greyTints = ["#3A3A3C", "#48484A", "#2C2C2E", "#545456", "#636366"];

  const bubbles = useMemo(() => {
    const list = [];
    const n = 9 + (seed % 4);
    for (let i = 0; i < n; i++) {
      const isBlue = seededRand(seed, i * 3) > 0.4;
      list.push({
        isBlue,
        topPct: seededRand(seed, i * 11 + 2) * 72,
        wPct: 32 + seededRand(seed, i * 5 + 3) * 35,
        hPt: 16 + seededRand(seed, i * 13 + 4) * 44,
        edge: seededRand(seed, i * 19 + 6) * 14,
        opacity: 0.38 + seededRand(seed, i * 17 + 5) * 0.42,
      });
    }
    return list;
  }, [seed]);

  const blurPx = 8 + (seed % 6);

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        overflow: "hidden",
        background: baseGrad,
        borderRadius: 0,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: px(-28),
          filter: `blur(${blurPx}px)`,
          WebkitFilter: `blur(${blurPx}px)`,
          transform: "scale(1.1)",
          transformOrigin: "center center",
        }}
      >
        {bubbles.map((b, i) => (
          <div
            key={i}
            style={{
              position: "absolute",
              ...(b.isBlue
                ? { right: `${b.edge}%`, left: "auto" }
                : { left: `${b.edge}%`, right: "auto" }),
              top: `${b.topPct}%`,
              width: `${b.wPct}%`,
              maxWidth: "78%",
              height: px(b.hPt),
              borderRadius: px(18),
              background: b.isBlue ? blueTints[(seed + i) % blueTints.length] : greyTints[(seed + i) % greyTints.length],
              opacity: b.opacity,
              boxShadow: "0 1px 8px rgba(0,0,0,0.35)",
            }}
          />
        ))}
      </div>
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(ellipse 92% 78% at 50% 42%, transparent 25%, rgba(0,0,0,0.5) 100%)",
          pointerEvents: "none",
        }}
      />
    </div>
  );
}

function MenuIconReply({ size }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M9 10l-4 4 4 4M5 14h10.5a4.5 4.5 0 100-9H5"
        stroke="rgba(255,255,255,0.85)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function MenuIconSticker({ size }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10c1.19 0 2.34-.21 3.41-.59L20 17V12C20 6.48 16.42 2 12 2z"
        stroke="rgba(255,255,255,0.85)" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M15 11l-3 3-2-2" stroke="rgba(255,255,255,0.85)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function MenuIconSave({ size }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 3v13M8 12l4 4 4-4" stroke="rgba(255,255,255,0.85)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5 20h14" stroke="rgba(255,255,255,0.85)" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function MenuIconCopy({ size }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="8" y="8" width="12" height="12" rx="2" stroke="rgba(255,255,255,0.85)" strokeWidth="1.6" />
      <path d="M6 16H5a2 2 0 01-2-2V5a2 2 0 012-2h9a2 2 0 012 2v1"
        stroke="rgba(255,255,255,0.85)" strokeWidth="1.6" />
    </svg>
  );
}

const MENU_ROWS = [
  { label: "Reply",       Icon: MenuIconReply },
  { label: "Add Sticker", Icon: MenuIconSticker },
  { label: "Save",        Icon: MenuIconSave },
  { label: "Copy",        Icon: MenuIconCopy },
];

const TAPBACK_ITEMS = [
  { t: "❤️", text: false },
  { t: "👍", text: false },
  { t: "👎", text: false },
  { t: "😂", text: false },
  { t: "❕", text: false },
  { t: "❓", text: false },
];

export default function IMessageMomSlide({ slot, S, config }) {
  const brand = getBrand(config);
  // px() converts iPhone pts → canvas pixels
  const px = (n) => Math.round(n * IPHONE_SCALE * S);
  const J  = makeJitter(config?.jitterSeed ?? 0);

  const W = Math.round(1080 * S);
  const H = Math.round(1920 * S);

  const watermark = brand.appId === "valcoin" ? "" : (config?.tiktokWatermark ?? "").trim();

  const seed = useMemo(() => slotSeed(slot), [slot]);

  /** Which tapback gets the blue circle — any of the 6, changes per slot/seed. */
  const selectedTapback = useMemo(() => seed % TAPBACK_ITEMS.length, [seed]);

  // ── Layout constants (all in iPhone pts) — J(id) = ±Npt per generation ──
  const padX       = 14   + J(50, 2);
  const padTop     = 24   + J(51, 2);
  const padBottom  = 18   + J(52, 2);
  const gapAfterTb = 10   + J(53, 1);
  const gapAfterImg = 10  + J(54, 1);
  const tbH        = 46   + J(55, 1);
  const menuRowH   = 54   + J(56, 1);
  const menuH      = MENU_ROWS.length * menuRowH;
  const menuRadius = 14   + J(57, 1);

  const totalPt = H / (IPHONE_SCALE * S);
  const imgH_pt = totalPt - padTop - tbH - gapAfterTb - gapAfterImg - menuH - padBottom;
  const imgW_pt = 390 - padX * 2;

  const tbItemSize = px(40);

  return (
    <div style={{
      width: W, height: H,
      background: "#000",
      fontFamily: FONT,
      position: "relative",
      overflow: "hidden",
    }}>
      {/* ── Full-screen iMessage thread backdrop ── */}
      <div style={{ position: "absolute", inset: 0, zIndex: 0 }}>
        <IMessageThreadBackdrop seed={seed} px={px} />
      </div>

      <div style={{
        position: "absolute",
        left: 0, right: 0,
        top: px(padTop),
        zIndex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "stretch",
        paddingLeft: px(padX),
        paddingRight: px(padX),
      }}>

        {/* ── Tapback + photo ── */}
        <div
          style={{
            width: "100%",
            alignSelf: "center",
            maxWidth: px(imgW_pt),
            marginBottom: px(gapAfterImg),
          }}
        >
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
            }}
          >
            <div style={{ display: "flex", justifyContent: "center", marginBottom: px(gapAfterTb) }}>
              <div style={{
                display: "inline-flex",
                alignItems: "center",
                gap: px(4),
                padding: `${px(5)}px ${px(10)}px`,
                borderRadius: 9999,
                background: "rgba(52,52,52,0.96)",
                boxShadow: "0 4px 24px rgba(0,0,0,0.5)",
              }}>
                {TAPBACK_ITEMS.map((item, i) => {
                  const sel = i === selectedTapback;
                  return (
                    <div key={i} style={{
                      width: tbItemSize,
                      height: tbItemSize,
                      borderRadius: tbItemSize / 2,
                      background: sel ? IOS_BLUE : "transparent",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: px(20),
                      lineHeight: 1,
                    }}>
                      {item.t}
                    </div>
                  );
                })}
              </div>
            </div>

            <div style={{
              height: px(imgH_pt),
              width: "100%",
              maxWidth: px(imgW_pt),
              borderRadius: px(18),
              overflow: "hidden",
              background: "#1c1c1c",
              position: "relative",
              alignSelf: "center",
              boxShadow: "0 4px 24px rgba(0,0,0,0.45), inset 0 0 0 0.5px rgba(255,255,255,0.08)",
            }}>
              {slot?.imageUrl
                ? <img src={slot.imageUrl} alt="" style={{ width: "100%", height: "100%", objectFit: "contain", objectPosition: "center", display: "block" }} />
                : <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "rgba(255,255,255,0.2)", fontSize: px(14) }}>No photo</div>
              }
              {watermark && (
                <div style={{
                  position: "absolute", right: px(8), bottom: px(6),
                  fontSize: px(11), fontWeight: 600,
                  color: "rgba(255,255,255,0.9)",
                  textShadow: "0 1px 3px rgba(0,0,0,0.8)",
                }}>
                  {watermark}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── Action sheet ── */}
        <div style={{
          borderRadius: px(menuRadius),
          overflow: "hidden",
          background: "rgba(38,38,38,0.97)",
          border: "0.5px solid rgba(255,255,255,0.1)",
        }}>
          {MENU_ROWS.map((row, idx) => (
            <div key={row.label}>
              {idx > 0 && <div style={{ height: 0.5, background: "rgba(80,80,80,0.8)", marginLeft: px(16) }} />}
              <div style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                paddingLeft: px(16),
                paddingRight: px(16),
                height: px(menuRowH),
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: px(12) }}>
                  <span style={{ color: "#fff", fontSize: px(17), fontWeight: 400, letterSpacing: "-0.02em" }}>
                    {row.label}
                  </span>
                </div>
                <row.Icon size={px(22)} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
