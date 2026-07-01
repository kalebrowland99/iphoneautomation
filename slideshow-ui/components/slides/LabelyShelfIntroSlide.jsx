"use client";

import { numistaDisplaySrc } from "@/lib/numistaImageClient";

export default function LabelyShelfIntroSlide({ slot, S, hidePlaceholder = false }) {
  const W = Math.round(1080 * S);
  const H = Math.round(1920 * S);
  const heroUrl = String(slot?.labelyShelfImageUrl || "").trim();

  return (
    <div style={{ width: W, height: H, position: "relative", background: "#000", overflow: "hidden" }}>
      {heroUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={numistaDisplaySrc(heroUrl)}
          alt={slot.itemName || "Product intro"}
          style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "center", display: "block" }}
        />
      ) : hidePlaceholder ? (
        <div style={{ width: "100%", height: "100%", background: "#000" }} />
      ) : (
        <div
          style={{
            width: "100%",
            height: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "linear-gradient(180deg,#111,#000)",
            color: "rgba(255,255,255,0.25)",
            fontSize: Math.round(15 * S),
            fontFamily: "Arial, sans-serif",
          }}
        >
          Intro scene
        </div>
      )}
    </div>
  );
}
