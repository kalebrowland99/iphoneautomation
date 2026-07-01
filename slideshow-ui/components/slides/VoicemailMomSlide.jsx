"use client";

import { useMemo } from "react";
import { makeJitter } from "@/lib/jitter";
import { getBrand } from "@/lib/brand";

/**
 * iOS Phone app — Voicemail playback screen (light mode).
 * Sizes in iPhone pts (390pt wide), scaled by IPHONE_SCALE * S.
 */

const IPHONE_SCALE = 1080 / 390;
const FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", system-ui, sans-serif';
const IOS_BLUE  = "#007AFF";
const IOS_GREEN = "#34C759";
const IOS_RED   = "#FF3B30";
const IOS_GREY  = "#8E8E93";
const IOS_BG2   = "#F2F2F7";

function hashStr(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619) >>> 0;
  return h;
}

const APP_VARIANTS = [
  (n) => `Hey honey it's mom, I found a ${n} at Goodwill and I just had to call you about it. Also I need to talk to you because your girlfriend's thrift haul videos are completely inappropriate and honestly if she keeps posting that kind of content she is not welcome at family events, I'm sorry.`,
  (n) => `Sweetie it's mom, I was at Goodwill and found a ${n} and I thought of you right away. And I don't want to cause drama but I've seen your girlfriend's thrift videos and they are not okay, the family has talked and she will not be invited to things if that continues, just so you know.`,
  (n) => `Hi honey it's mom, quick one — I found a ${n} at Goodwill today and I grabbed it for you. Also I have to be honest with you, your girlfriend's little thrift haul videos have been making the rounds in the family and we all agree it's inappropriate, so she is not welcome at family gatherings until further notice.`,
  (n) => `It's mom, so I found this ${n} at Goodwill and I picked it up for you, call me when you get this. One more thing and I say this with love — your girlfriend's thrift videos are embarrassing and the family is not comfortable having her around at events if she's going to keep doing that, we need to talk.`,
  (n) => `Hey it's your mom, I found a ${n} at the Goodwill and I just knew you'd want it honey so I got it. Also please don't be upset but your girlfriend's thrift haul videos are completely inappropriate and at this point the family has decided she's not welcome at any family events if she continues, that's all I'll say.`,
];

/**
 * Turns "The North Face Puffer Jacket (Size L)" → "north face jacket"
 * — strips leading "The/A/An", drops parenthetical size notes,
 *   collapses redundant brand words, lowercases for natural mom speech.
 */
function momName(itemName) {
  if (!itemName) return "that thing";
  let s = itemName.trim();
  // Treat placeholder default names like "Item 1", "Item 2" as empty
  if (/^item\s+\d+$/i.test(s)) return "that thing";
  // Remove parenthetical size/condition notes like "(Size L)" or "(NWT)"
  s = s.replace(/\s*\(.*?\)/g, "").trim();
  // Remove leading articles
  s = s.replace(/^(the|a|an)\s+/i, "").trim();
  // Drop common filler words mom wouldn't say
  s = s.replace(/\b(vintage|authentic|pre-owned|pre owned|used|like-new|like new|gently used)\b/gi, "").trim();
  // Collapse extra spaces
  s = s.replace(/\s+/g, " ").trim();
  if (!s) return "that thing";
  // Lowercase — mom doesn't know brand capitalization rules
  return s.toLowerCase();
}

function defaultTranscript(itemName, seed) {
  const n = momName(itemName) || "that thing";
  const pick = (seed >>> 0) % APP_VARIANTS.length;
  return APP_VARIANTS[pick](n);
}

import { MOM_CONTACT_NAMES } from "@/lib/momContactNames";
const CONTACT_NAMES = MOM_CONTACT_NAMES;

export default function VoicemailMomSlide({ slot, S, config }) {
  const brand = getBrand(config);
  const px = (n) => Math.round(n * IPHONE_SCALE * S);
  const J  = makeJitter(config?.jitterSeed ?? 0);

  const W = Math.round(1080 * S);
  const H = Math.round(1920 * S);

  const metaLine = useMemo(() => {
    const d = slot?.date?.trim();
    return d ? `Unknown — ${d}` : "Unknown — Apr 1, 2026 at 9:39 AM";
  }, [slot?.date]);

  const seed = useMemo(
    () => hashStr((slot?.itemName || "") + (slot?.spentPrice || "") + (slot?.soldPrice || "")),
    [slot?.itemName, slot?.spentPrice, slot?.soldPrice]
  );

  const displayName = useMemo(() => {
    if (brand.appId === "valcoin") return "";
    const override = (config?.voicemailDisplayNumber ?? "").trim();
    if (override) return override;
    return CONTACT_NAMES[seed % CONTACT_NAMES.length];
  }, [brand.appId, config?.voicemailDisplayNumber, seed]);

  const transcript = useMemo(() => {
    const t = (slot?.voicemailTranscript ?? "").trim();
    if (t) return t;
    return defaultTranscript(slot?.itemName, seed);
  }, [slot?.voicemailTranscript, slot?.itemName, slot?.spentPrice, slot?.soldPrice]);

  // ── Heights (iPhone pts) — J(id) adds ±2pt per-generation for anti-fingerprint
  const statusH  = 54  + J(30, 2);
  const navH     = 88  + J(31, 2);
  const metaH    = 36  + J(32, 1);
  const scrubH   = 52  + J(33, 1);
  const ctrlH    = 72  + J(34, 2);
  const pillsH   = 50  + J(35, 1);
  const pillGap  = 8   + J(36, 1);
  const tabH     = 82  + J(37, 2);

  // Total fixed = statusH + navH + metaH + scrubH + ctrlH + pillsH + tabH
  const fixedPt = statusH + navH + metaH + scrubH + ctrlH + pillsH + tabH;
  const totalPt = H / (IPHONE_SCALE * S);
  const transcriptH = Math.max(60, totalPt - fixedPt - 16); // 16pt top/bottom padding in section

  return (
    <div style={{
      width: W, height: H,
      background: "#FFFFFF",
      fontFamily: FONT,
      color: "#000",
      position: "relative",
      overflow: "hidden",
      display: "flex",
      flexDirection: "column",
    }}>

      {/* ── Status bar ────────────────────────────────────────────────── */}
      <div style={{
        flexShrink: 0,
        height: px(statusH),
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        paddingLeft: px(24),
        paddingRight: px(18),
        paddingTop: px(16),
      }}>
        <span style={{ fontSize: px(17), fontWeight: 600, letterSpacing: "-0.02em" }}>8:34</span>
        <div style={{ display: "flex", alignItems: "center", gap: px(5) }}>
          {/* Signal bars */}
          <div style={{ display: "flex", alignItems: "flex-end", gap: px(1.5), height: px(11) }}>
            {[4, 6, 9, 11].map((h, i) => (
              <div key={i} style={{ width: px(3), height: px(h), background: "#000", borderRadius: px(1) }} />
            ))}
          </div>
          <span style={{ fontSize: px(13), fontWeight: 600, letterSpacing: "-0.01em" }}>5G+</span>
          {/* Battery */}
          <div style={{
            width: px(25), height: px(12),
            border: `${px(1)}px solid rgba(0,0,0,0.35)`,
            borderRadius: px(3),
            padding: px(1.5),
            display: "flex",
            position: "relative",
          }}>
            <div style={{ width: "75%", background: "#000", borderRadius: px(1.5) }} />
            <div style={{
              position: "absolute", right: px(-3), top: "25%", bottom: "25%",
              width: px(2.5), background: "rgba(0,0,0,0.4)", borderRadius: `0 ${px(2)}px ${px(2)}px 0`,
            }} />
          </div>
        </div>
      </div>

      {/* ── Navigation bar ────────────────────────────────────────────── */}
      <div style={{
        flexShrink: 0,
        height: px(navH),
        display: "flex",
        alignItems: "center",
        paddingLeft: px(14),
        paddingRight: px(14),
        gap: px(8),
        borderBottom: `${px(0.5)}px solid rgba(0,0,0,0.1)`,
      }}>
        {/* Back */}
        <div style={{ fontSize: px(28), color: IOS_BLUE, lineHeight: 1, fontWeight: 300, marginTop: px(-2) }}>‹</div>
        {/* Title */}
        <div style={{ flex: 1, textAlign: "center" }}>
          <div style={{ fontSize: px(17), fontWeight: 600, letterSpacing: "-0.02em" }}>
            {displayName} <span style={{ color: "#C7C7CC", fontWeight: 400 }}>›</span>
          </div>
        </div>
        {/* Call button */}
        <div style={{
          width: px(44), height: px(44),
          borderRadius: "50%",
          background: IOS_GREEN,
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0,
        }}>
          <svg width={px(22)} height={px(22)} viewBox="0 0 24 24" fill="white" aria-hidden>
            <path d="M20.01 15.38c-1.23 0-2.42-.2-3.53-.56a.977.977 0 00-1.01.24l-1.57 1.97c-4.51-2.38-7.17-5.19-9.53-9.53l1.97-1.57a.99.99 0 00.25-1.11c-.37-1.12-.56-2.3-.56-3.53 0-.54-.45-.99-.99-.99H4.19C3.65 3 3 3.24 3 3.99 3 13.28 10.73 21 20.01 21c.71 0 .99-.63.99-1.18v-3.45c0-.54-.45-.99-.99-.99z" />
          </svg>
        </div>
      </div>

      {/* ── Meta line ─────────────────────────────────────────────────── */}
      <div style={{
        flexShrink: 0,
        height: px(metaH),
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: px(13),
        color: IOS_GREY,
      }}>
        {metaLine}
      </div>

      {/* ── Scrubber ──────────────────────────────────────────────────── */}
      <div style={{
        flexShrink: 0,
        height: px(scrubH),
        paddingLeft: px(20),
        paddingRight: px(20),
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        gap: px(6),
      }}>
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: px(12),
          color: IOS_GREY,
        }}>
          <span>00:00</span>
          <span>-00:15</span>
        </div>
        <div style={{ height: px(4), background: "#E5E5EA", borderRadius: px(2), position: "relative" }}>
          <div style={{
            position: "absolute",
            left: 0, top: "50%",
            transform: "translateY(-50%)",
            width: px(14), height: px(14),
            borderRadius: "50%",
            background: "#fff",
            border: `${px(1)}px solid #C7C7CC`,
            boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
          }} />
        </div>
      </div>

      {/* ── Playback controls ─────────────────────────────────────────── */}
      <div style={{
        flexShrink: 0,
        height: px(ctrlH),
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        paddingLeft: px(32),
        paddingRight: px(32),
      }}>
        {/* Share */}
        <svg width={px(22)} height={px(22)} viewBox="0 0 24 24" fill="#000" aria-hidden>
          <path d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92 1.61 0 2.92-1.31 2.92-2.92s-1.31-2.92-2.92-2.92z" />
        </svg>
        {/* Skip back */}
        <svg width={px(26)} height={px(26)} viewBox="0 0 24 24" fill="#000" aria-hidden>
          <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z" />
        </svg>
        {/* Play */}
        <svg width={px(38)} height={px(38)} viewBox="0 0 24 24" fill="#000" aria-hidden>
          <path d="M8 5v14l11-7z" />
        </svg>
        {/* Speaker */}
        <svg width={px(26)} height={px(26)} viewBox="0 0 24 24" fill="#000" aria-hidden>
          <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" />
        </svg>
        {/* Trash */}
        <svg width={px(22)} height={px(22)} viewBox="0 0 24 24" fill="#000" aria-hidden>
          <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" />
        </svg>
      </div>

      {/* ── Action pills ──────────────────────────────────────────────── */}
      <div style={{
        flexShrink: 0,
        height: px(pillsH),
        display: "flex",
        alignItems: "center",
        paddingLeft: px(20),
        paddingRight: px(20),
        gap: px(pillGap),
      }}>
        <div style={{
          flex: 1, height: px(36),
          borderRadius: 9999,
          background: IOS_BG2,
          display: "flex", alignItems: "center", justifyContent: "center",
          gap: px(5),
          fontSize: px(15), fontWeight: 500, color: IOS_BLUE,
        }}>
          <svg width={px(16)} height={px(16)} viewBox="0 0 24 24" fill={IOS_BLUE} aria-hidden>
            <path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z" />
          </svg>
          Add Contact
        </div>
        <div style={{
          flex: 1, height: px(36),
          borderRadius: 9999,
          background: IOS_BG2,
          display: "flex", alignItems: "center", justifyContent: "center",
          gap: px(5),
          fontSize: px(15), fontWeight: 500, color: IOS_RED,
        }}>
          <svg width={px(15)} height={px(15)} viewBox="0 0 24 24" fill={IOS_RED} aria-hidden>
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
          </svg>
          Report Spam
        </div>
      </div>

      {/* ── Transcript ────────────────────────────────────────────────── */}
      <div style={{
        flex: "1 1 0",
        minHeight: px(transcriptH),
        padding: `${px(8)}px ${px(20)}px`,
        display: "flex",
        flexDirection: "column",
      }}>
        <div style={{ fontSize: px(13), color: IOS_GREY, marginBottom: px(6) }}>
          Transcript (low confidence)
        </div>
        <div style={{
          fontSize: px(16),
          lineHeight: 1.45,
          color: "#000",
          letterSpacing: "-0.01em",
          overflow: "hidden",
        }}>
          {transcript}
        </div>
      </div>

      {/* ── Tab bar ───────────────────────────────────────────────────── */}
      <div style={{
        flexShrink: 0,
        height: px(tabH),
        background: "rgba(248,248,248,0.97)",
        borderTop: `${px(0.5)}px solid #D1D1D6`,
        display: "flex",
        alignItems: "flex-start",
        paddingTop: px(8),
        paddingBottom: px(20),
        paddingLeft: px(10),
        paddingRight: px(10),
      }}>
        {/* Calls — active */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: px(3) }}>
          <div style={{ position: "relative" }}>
            <svg width={px(26)} height={px(26)} viewBox="0 0 24 24" fill={IOS_BLUE} aria-hidden>
              <path d="M20.01 15.38c-1.23 0-2.42-.2-3.53-.56a.977.977 0 00-1.01.24l-1.57 1.97c-4.51-2.38-7.17-5.19-9.53-9.53l1.97-1.57a.99.99 0 00.25-1.11c-.37-1.12-.56-2.3-.56-3.53 0-.54-.45-.99-.99-.99H4.19C3.65 3 3 3.24 3 3.99 3 13.28 10.73 21 20.01 21c.71 0 .99-.63.99-1.18v-3.45c0-.54-.45-.99-.99-.99z" />
            </svg>
            <div style={{
              position: "absolute",
              top: px(-5), right: px(-8),
              background: IOS_RED,
              color: "#fff",
              fontSize: px(10), fontWeight: 700,
              minWidth: px(16), height: px(16),
              borderRadius: 9999,
              display: "flex", alignItems: "center", justifyContent: "center",
              paddingLeft: px(2), paddingRight: px(2),
            }}>2</div>
          </div>
          <span style={{ fontSize: px(10), color: IOS_BLUE, fontWeight: 500 }}>Calls</span>
        </div>
        {/* Contacts */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: px(3) }}>
          <svg width={px(26)} height={px(26)} viewBox="0 0 24 24" fill={IOS_GREY} aria-hidden>
            <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
          </svg>
          <span style={{ fontSize: px(10), color: IOS_GREY }}>Contacts</span>
        </div>
        {/* Keypad */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: px(3) }}>
          <div style={{ width: px(26), height: px(26), display: "grid", gridTemplateColumns: "1fr 1fr", gap: px(4), padding: px(2) }}>
            {[0,1,2,3].map(i => (
              <div key={i} style={{ borderRadius: "50%", background: IOS_GREY, aspectRatio: "1" }} />
            ))}
          </div>
          <span style={{ fontSize: px(10), color: IOS_GREY }}>Keypad</span>
        </div>
        {/* Search */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: px(3) }}>
          <svg width={px(26)} height={px(26)} viewBox="0 0 24 24" fill="none" aria-hidden>
            <circle cx="11" cy="11" r="7" stroke={IOS_GREY} strokeWidth="2" />
            <path d="M16.5 16.5l4 4" stroke={IOS_GREY} strokeWidth="2" strokeLinecap="round" />
          </svg>
          <span style={{ fontSize: px(10), color: IOS_GREY }}>Search</span>
        </div>
      </div>

    </div>
  );
}
