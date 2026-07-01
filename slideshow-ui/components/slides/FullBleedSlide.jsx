"use client";

/** Pose-person format: full-frame image only (no overlays). */

export default function FullBleedSlide({ slot, S }) {
  const W = Math.round(1080 * S);
  const H = Math.round(1920 * S);

  return (
    <div style={{ width: W, height: H, position: "relative", background: "#000", overflow: "hidden" }}>
      {slot.imageUrl ? (
        <img
          src={slot.imageUrl}
          alt={slot.itemName || "Item"}
          style={{ width: "100%", height: "100%", objectFit: "contain", objectPosition: "center", display: "block" }}
        />
      ) : (
        <div
          style={{
            width: "100%",
            height: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "#1c1c1c",
            color: "rgba(255,255,255,0.2)",
            fontSize: Math.round(14 * S),
            fontFamily: "Arial, sans-serif",
          }}
        >
          No image
        </div>
      )}
    </div>
  );
}
