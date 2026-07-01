"use client";

import { numistaDisplaySrc } from "@/lib/numistaImageClient";

export default function CollageSlide({ config, S }) {
  const { slots } = config;
  const isLabely = (config.appId ?? "thrifty") === "labely";

  const W = Math.round(1080 * S);
  const H = Math.round(1920 * S);
  const gap = isLabely ? 0 : Math.round(3 * S);

  return (
    <div style={{ width: W, height: H, position: "relative", background: "#111", overflow: "hidden" }}>
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gridTemplateRows: "1fr 1fr 1fr",
          gap: `${gap}px`,
          background: isLabely ? "#0a0a0a" : "#111",
        }}
      >
        {slots.map((slot, i) => (
          <div
            key={i}
            style={{
              position: "relative",
              overflow: "hidden",
              minWidth: 0,
              minHeight: 0,
              width: "100%",
              height: "100%",
              background: "#1c1c1c",
            }}
          >
            {slot.imageUrl ? (
              <img
                src={numistaDisplaySrc(slot.imageUrl)}
                alt={`Slot ${i + 1}`}
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                  objectPosition: "center",
                  display: "block",
                }}
              />
            ) : (
              <EmptyCell index={i} S={S} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyCell({ index, S }) {
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: Math.round(6 * S),
        border: `1px dashed rgba(255,255,255,0.1)`,
      }}
    >
      <svg width={Math.round(28 * S)} height={Math.round(28 * S)} fill="none" viewBox="0 0 24 24"
        stroke="rgba(255,255,255,0.15)" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
      </svg>
      <span style={{ color: "rgba(255,255,255,0.15)", fontSize: Math.round(11 * S), fontFamily: "Arial", fontWeight: "600" }}>
        {index + 1}
      </span>
    </div>
  );
}
