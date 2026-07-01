"use client";

import { useMemo } from "react";
import { makeJitter } from "@/lib/jitter";

/**
 * iOS Messages dark-mode chat screenshot.
 * Shows mom's follow-up texts after the voicemail: called but no answer,
 * GF's thrift hauls are inappropriate, gave the item away.
 */

const IPHONE_SCALE = 1080 / 390;
const FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Display", system-ui, sans-serif';
const IOS_BLUE    = "#007AFF";
// iSpoof exact values
const BUBBLE_RECV = "#E5E5EA";   // contact bubble
const BUBBLE_SENT = "#007AFF";   // user bubble
const MSG_BG      = "#ffffff";   // messages area — light mode (matches iSpoof download)
const NAV_BG      = "#f9f9f9";   // nav/header area light
const STATUS_BG   = "#000000";   // status bar stays dark

function hashStr(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619) >>> 0;
  return h;
}

// Same contact-name pool as VoicemailMomSlide so they always match
import { MOM_CONTACT_NAMES } from "@/lib/momContactNames";
const CONTACT_NAMES = MOM_CONTACT_NAMES;
import { getBrand } from "@/lib/brand";

function momName(itemName) {
  if (!itemName) return "that thing";
  let s = itemName.trim();
  // Treat placeholder default names like "Item 1", "Item 2" as empty
  if (/^item\s+\d+$/i.test(s)) return "that thing";
  s = s
    .replace(/\s*\(.*?\)/g, "")
    .replace(/^(the|a|an)\s+/i, "")
    .replace(/\b(vintage|authentic|pre-owned|pre owned|used|like-new|like new|gently used)\b/gi, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!s) return "that thing";
  return s.toLowerCase();
}

// Each variant returns [{from:"mom"|"son", text}] — full conversation thread
const M = (text) => ({ from: "mom", text });
const S = (text) => ({ from: "son", text });

// Time strings shown above the first bubble
const TIME_LABELS = [
  "Today 8:34 AM", "Today 9:12 AM", "Today 10:47 AM",
  "Today 11:03 AM", "Today 2:18 PM",
];

export default function IMessageTextSlide({ slot, S, config }) {
  const brand = getBrand(config);
  const appLower = brand.appLower;

  // Son reply variants — reference the sold price
  const SON_REPLIES = [
    (p) => `mom i looked it up on ${appLower} and you literally gave away a $${p} item`,
    (p) => `MOM. i just checked ${appLower}. that was a $${p} item you gave away`,
    (p) => `mom why would you do that, ${appLower} says that thing was worth $${p}`,
    (p) => `you gave away a $${p} item mom. i looked it up on ${appLower}`,
    (p) => `mom ${appLower} says that was $${p}. you gave away $${p}.`,
  ];

  // Mom's comeback variants
  const MOM_COMEBACKS = [
    `idc what ${appLower} says. get a real job and stop reselling things`,
    `i don't care about ${appLower}. get a job. stop reselling. end of conversation.`,
    `${appLower} is not a job. get a real job and stop this reselling nonsense`,
    `i don't want to hear about ${appLower}. you need to get a job and stop this.`,
    "good. maybe that will teach you to answer your phone. also get a job.",
  ];

  const THREAD_VARIANTS = [
    (n, p, seed) => [
      M("i called you but you didn't pick up 🙄"),
      M(`we seriously need to talk about your girlfriend's thrift haul videos, they are completely inappropriate and embarrassing for this family`),
      M(`since you couldn't bother to answer your phone i went ahead and gave the ${n} away to another lady at the store. hope it was worth it.`),
      S(SON_REPLIES[(seed >>> 1) % SON_REPLIES.length](p)),
      M(MOM_COMEBACKS[(seed >>> 4) % MOM_COMEBACKS.length]),
    ],
    (n, p, seed) => [
      M("you didn't answer so i left a voicemail but i'll say it here too"),
      M(`your girlfriend's thrift videos are NOT okay and the whole family agrees, it needs to stop`),
      M(`also because you didn't call me back i gave your ${n} to someone else at goodwill. it's gone. call me.`),
      S(SON_REPLIES[(seed >>> 1) % SON_REPLIES.length](p)),
      M(MOM_COMEBACKS[(seed >>> 4) % MOM_COMEBACKS.length]),
    ],
    (n, p, seed) => [
      M("i called. no answer. typical."),
      M(`i need you to talk to your girlfriend about her thrift haul videos — they are offensive and she will not be welcome at family events if this continues`),
      M(`i waited for you to call back and you didn't so i gave the ${n} away. someone else has it now. that's on you.`),
      S(SON_REPLIES[(seed >>> 1) % SON_REPLIES.length](p)),
      M(MOM_COMEBACKS[(seed >>> 4) % MOM_COMEBACKS.length]),
    ],
    (n, p, seed) => [
      M("hey i called you like 3 times, you need to answer your phone"),
      M(`this is about your girlfriend's thrift videos — the whole family has seen them and we are NOT okay with it, she needs to stop`),
      M(`and since you ignored me i donated the ${n} i found for you back to goodwill. it's gone. next time answer your phone.`),
      S(SON_REPLIES[(seed >>> 1) % SON_REPLIES.length](p)),
      M(MOM_COMEBACKS[(seed >>> 4) % MOM_COMEBACKS.length]),
    ],
    (n, p, seed) => [
      M("you didn't pick up so now i'm texting you 🙄"),
      M(`your girlfriend's little thrift haul videos are embarrassing and inappropriate and i need you to tell her to stop before the next family event`),
      M(`i held onto that ${n} for you all day waiting for you to call back and you never did so i gave it away. gone. i hope she posts THAT in a video.`),
      S(SON_REPLIES[(seed >>> 1) % SON_REPLIES.length](p)),
      M(MOM_COMEBACKS[(seed >>> 4) % MOM_COMEBACKS.length]),
    ],
  ];
  const px = (n) => Math.round(n * IPHONE_SCALE * S);
  const J  = makeJitter(config?.jitterSeed ?? 0);

  const W = Math.round(1080 * S);
  const H = Math.round(1920 * S);

  const seed = useMemo(() => hashStr(
    (slot?.itemName || "") + (slot?.spentPrice || "") + (slot?.soldPrice || "")
  ), [slot?.itemName, slot?.spentPrice, slot?.soldPrice]);

  const contactName = useMemo(() => {
    const override = (config?.voicemailDisplayNumber ?? "").trim();
    if (override) return override;
    return CONTACT_NAMES[seed % CONTACT_NAMES.length];
  }, [config?.voicemailDisplayNumber, seed]);

  const bubbles = useMemo(() => {
    // Prefer AI-generated thread stored on the slot
    if (Array.isArray(slot?.imessageThread) && slot.imessageThread.length >= 3) {
      return slot.imessageThread.map((m) => ({ from: m.from, text: m.text }));
    }
    // Seeded fallback
    const n = momName(slot?.itemName);
    const p = slot?.soldPrice ? slot.soldPrice : "???";
    return THREAD_VARIANTS[(seed >>> 0) % THREAD_VARIANTS.length](n, p, seed);
  }, [seed, slot?.itemName, slot?.soldPrice, slot?.imessageThread]);

  const timeLabel = TIME_LABELS[(seed >>> 2) % TIME_LABELS.length];
  const shortName   = contactName.replace(/\s*\(.*?\)/, "").trim().split(/\s+/)[0];
  const avatarLetter = shortName[0]?.toUpperCase() ?? "M";

  // ── Layout (all in iPhone pts, matching iSpoof) ───────────────────────────
  // J(id, maxPt) adds ±maxPt pt per-generation so each export is pixel-unique
  const statusH    = 50   + J(10, 2);
  const islandH    = 37;
  const navH       = 82   + J(11, 2);
  const inputBarH  = 82   + J(12, 2);
  const avatarSz   = 40   + J(13, 1);
  const avatarGap  = 8    + J(14, 1);
  const leftPad    = 12   + J(15, 2);
  const rightPad   = 12   + J(16, 2);
  const bubbleMaxW = 255  + J(17, 3);
  const fontSize   = 17   + J(18, 1);
  const padV       = 8    + J(19, 1);
  const padH       = 14   + J(20, 1);
  const sameGap    = 4    + J(21, 1);
  const turnGap    = 16   + J(22, 2);

  return (
    <div style={{
      width: W, height: H,
      background: STATUS_BG,
      fontFamily: FONT,
      position: "relative",
      overflow: "hidden",
    }}>

      {/* ── Status bar (dark) ───────────────────────────────────────────────── */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0,
        height: px(statusH),
        background: STATUS_BG,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        paddingLeft: px(22), paddingRight: px(18),
        zIndex: 10,
      }}>
        <span style={{ color: "#fff", fontSize: px(15), fontWeight: 600, letterSpacing: "-0.02em" }}>9:41</span>
        <div style={{ display: "flex", alignItems: "center", gap: px(6) }}>
          {[6, 9, 12, 15].map((h, i) => (
            <div key={i} style={{ width: px(3.5), height: px(h), background: "#fff", borderRadius: px(1.5), alignSelf: "flex-end" }} />
          ))}
          <svg width={px(17)} height={px(13)} viewBox="0 0 24 18" fill="white" style={{ marginLeft: px(2) }}>
            <path d="M12 4C7.31 4 3.07 5.9 0 8.98L2.4 11.5C4.83 9.02 8.24 7.5 12 7.5s7.17 1.52 9.6 4L24 9C20.93 5.9 16.69 4 12 4zm0 6c-3.04 0-5.78 1.21-7.78 3.16L6.6 15.5C8.04 14.03 10 13.1 12 13.1s3.96.93 5.4 2.4l2.38-2.34C17.78 11.21 15.04 10 12 10zm0 6a4 4 0 00-2.83 1.17L12 20l2.83-2.83A4 4 0 0012 16z"/>
          </svg>
          <div style={{ position: "relative", marginLeft: px(2) }}>
            <div style={{ width: px(27), height: px(13), borderRadius: px(3), border: `${px(1.5)}px solid rgba(255,255,255,0.45)`, overflow: "hidden" }}>
              <div style={{ position: "absolute", inset: px(1.5), right: "20%", background: "#fff", borderRadius: px(1.5) }} />
            </div>
            <div style={{ position: "absolute", right: px(-3.5), top: "30%", bottom: "30%", width: px(2.5), background: "rgba(255,255,255,0.45)", borderRadius: "0 1px 1px 0" }} />
          </div>
        </div>
      </div>

      {/* ── Dynamic Island ──────────────────────────────────────────────────── */}
      <div style={{
        position: "absolute",
        top: px(11), left: "50%",
        transform: "translateX(-50%)",
        width: px(126), height: px(islandH),
        background: "#000",
        borderRadius: px(19),
        zIndex: 20,
      }} />

      {/* ── Nav / Header (light, matches iSpoof) ────────────────────────────── */}
      <div style={{
        position: "absolute", top: px(statusH), left: 0, right: 0,
        height: px(navH),
        background: NAV_BG,
        borderBottom: `${px(0.5)}px solid #d1d1d6`,
        display: "flex", alignItems: "center",
        paddingLeft: px(10), paddingRight: px(16),
        zIndex: 10,
      }}>
        {/* Back chevron — iSpoof style */}
        <div style={{ minWidth: px(36), display: "flex", alignItems: "center" }}>
          <svg width={px(11)} height={px(19)} viewBox="0 0 11 19" fill="none" stroke={IOS_BLUE} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 1L1 9.5 9 18"/>
          </svg>
        </div>

        {/* Center — avatar + name (iSpoof layout) */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: px(3) }}>
          <div style={{
            width: px(avatarSz), height: px(avatarSz), borderRadius: "50%",
            background: "linear-gradient(45deg,#667eea 0%,#764ba2 100%)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <span style={{ color: "#fff", fontSize: px(18), fontWeight: 500 }}>{avatarLetter}</span>
          </div>
          <span style={{ color: "#000", fontSize: px(13), fontWeight: 500 }}>{shortName}</span>
        </div>

        {/* Video icon (right) — iSpoof */}
        <div style={{ minWidth: px(36), display: "flex", justifyContent: "flex-end" }}>
          <svg width={px(22)} height={px(16)} viewBox="0 0 24 18" fill={IOS_BLUE}>
            <path d="M15 3H2a1 1 0 00-1 1v10a1 1 0 001 1h13a1 1 0 001-1V4a1 1 0 00-1-1zm7 2.5l-5 3.5 5 3.5V5.5z"/>
          </svg>
        </div>
      </div>

      {/* ── Messages area (white, light mode — matches iSpoof export) ───────── */}
      <div style={{
        position: "absolute",
        top: px(statusH + navH),
        left: 0, right: 0,
        bottom: px(inputBarH),
        background: MSG_BG,
        display: "flex",
        flexDirection: "column",
        justifyContent: "flex-end",
        paddingLeft: px(leftPad),
        paddingRight: px(rightPad),
        paddingBottom: px(14),
        overflowY: "hidden",
      }}>
        {/* "iMessage / Today X:XX" — iSpoof header */}
        <div style={{
          textAlign: "center",
          color: "#8E8E93",
          fontSize: px(13),
          fontWeight: 400,
          marginBottom: px(14),
          lineHeight: 1.5,
        }}>
          <div style={{ fontWeight: 500 }}>iMessage</div>
          <div>Today {timeLabel}</div>
        </div>

        {/* Bubbles — iSpoof exact radii */}
        {bubbles.map((msg, idx) => {
          const isSon    = msg.from === "son";
          const isVeryLast = idx === bubbles.length - 1;
          // iSpoof exact: sent=18 18 4 18 (BR small), recv=18 18 18 4 (BL small)
          // px() returns a number so we must append "px" for CSS shorthand strings
          const r  = `${px(18)}px`;
          const rt = `${px(4)}px`;
          const borderRadius = isSon
            ? `${r} ${r} ${rt} ${r}`   // user-bubble
            : `${r} ${r} ${r} ${rt}`;  // contact-bubble

          return (
            <div key={idx} style={{
              display: "flex",
              flexDirection: "row",
              alignItems: "flex-end",
              justifyContent: isSon ? "flex-end" : "flex-start",
              marginTop: idx > 0 ? px(sameGap) : 0,
              marginBottom: bubbles[idx + 1]?.from !== msg.from ? px(turnGap - sameGap) : 0,
            }}>
              {/* Avatar for received — iSpoof: contact-photo beside bubble */}
              {!isSon && (
                <div style={{
                  width: px(avatarSz), height: px(avatarSz), borderRadius: "50%",
                  background: "linear-gradient(45deg,#667eea 0%,#764ba2 100%)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  flexShrink: 0, marginRight: px(8),
                }}>
                  <span style={{ color: "#fff", fontSize: px(16), fontWeight: 500 }}>{avatarLetter}</span>
                </div>
              )}

              <div>
                <div style={{
                  maxWidth: px(bubbleMaxW),
                  background: isSon ? BUBBLE_SENT : BUBBLE_RECV,
                  borderRadius,
                  padding: `${px(padV)}px ${px(padH)}px`,
                  wordWrap: "break-word",
                }}>
                  <span style={{
                    color: isSon ? "#fff" : "#000",
                    fontSize: px(fontSize),
                    lineHeight: 1.35,
                    fontWeight: 400,
                    display: "block",
                  }}>
                    {msg.text}
                  </span>
                </div>
                {/* Delivered under last message — iSpoof: message-status */}
                {isVeryLast && (
                  <div style={{
                    fontSize: px(13),
                    color: "#8E8E93",
                    marginTop: px(2),
                    textAlign: isSon ? "right" : "left",
                  }}>
                    Delivered
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Input bar (light, matches iSpoof) ───────────────────────────────── */}
      <div style={{
        position: "absolute",
        bottom: 0, left: 0, right: 0,
        height: px(inputBarH),
        background: NAV_BG,
        borderTop: `${px(0.5)}px solid #d1d1d6`,
        display: "flex", alignItems: "center",
        paddingLeft: px(12), paddingRight: px(14),
        gap: px(10),
      }}>
        {/* Camera button — iSpoof style round border */}
        <div style={{
          width: px(32), height: px(32), borderRadius: "50%",
          border: `${px(2)}px solid #8E8E93`,
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0,
        }}>
          <svg width={px(16)} height={px(14)} viewBox="0 0 24 20" fill="none" stroke="#8E8E93" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M23 17a2 2 0 01-2 2H3a2 2 0 01-2-2V7a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/>
            <circle cx="12" cy="12" r="4"/>
          </svg>
        </div>

        {/* iMessage text input + mic (iSpoof layout) */}
        <div style={{
          flex: 1, height: px(36),
          background: "#fff",
          border: `${px(1)}px solid #d1d1d6`,
          borderRadius: px(18),
          display: "flex", alignItems: "center",
          paddingLeft: px(14), paddingRight: px(10),
          justifyContent: "space-between",
        }}>
          <span style={{ color: "#8E8E93", fontSize: px(16) }}>iMessage</span>
          {/* Mic waveform — iSpoof */}
          <svg width={px(18)} height={px(18)} viewBox="0 0 24 24" fill="none" stroke="#8E8E93" strokeWidth="1.8" strokeLinecap="round">
            <path d="M12 2a3 3 0 013 3v7a3 3 0 01-6 0V5a3 3 0 013-3z"/>
            <path d="M19 10v2a7 7 0 01-14 0v-2"/>
            <line x1="12" y1="19" x2="12" y2="23"/>
            <line x1="8" y1="23" x2="16" y2="23"/>
          </svg>
        </div>
      </div>
    </div>
  );
}
