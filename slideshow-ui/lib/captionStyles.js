/** Caption style helpers. S = display/export scale factor. */

export const TIKTOK_FONT_FAMILY = "'TikTok Sans', system-ui, sans-serif";

export function tiktokTextShadow(S) {
  const w = Math.max(0.5, Math.round(1.15 * S * 10) / 10);
  const dirs = [
    [w, 0], [-w, 0], [0, w], [0, -w],
    [w, w], [w, -w], [-w, w], [-w, -w],
  ];
  return dirs.map(([x, y]) => `${x}px ${y}px 0 #000`).join(", ");
}

/** White text + black stroke — classic TikTok caption look. */
export function tiktokCaptionTextStyle(S, { fontSize, fontWeight = "800", letterSpacing = "0.04em" }) {
  const strokeW = Math.max(0.5, Math.round(0.85 * S * 10) / 10);
  return {
    display: "block",
    color: "#ffffff",
    fontSize,
    fontWeight,
    lineHeight: 1.2,
    fontFamily: TIKTOK_FONT_FAMILY,
    letterSpacing,
    textAlign: "center",
    WebkitTextStroke: `${strokeW}px #000000`,
    paintOrder: "stroke fill",
    textShadow: tiktokTextShadow(S),
  };
}

/** Solid color block (news-ticker / subtitle style) — no stroke, no shadow. */
export function tickerBoxCaptionTextStyle(S, { fontSize, fontWeight = "800", letterSpacing = "0.04em", color = "#ffffff" }) {
  return {
    display: "block",
    color,
    fontSize,
    fontWeight,
    lineHeight: 1.25,
    fontFamily: TIKTOK_FONT_FAMILY,
    letterSpacing,
    textAlign: "center",
  };
}

/**
 * Returns wrapper + text styles for the chosen captionStyle.
 * wrapperExtra is merged into the outer pill div.
 */
export function captionWrapperStyle(S, { captionStyle = "tiktok", captionBg = "#e03030", borderRadius }) {
  const r = borderRadius ?? Math.round(12 * S);
  if (captionStyle === "tickerBox") {
    return {
      background: captionBg,
      borderRadius: r,
      boxShadow: `0 ${Math.round(3 * S)}px ${Math.round(12 * S)}px rgba(0,0,0,0.35)`,
    };
  }
  return { background: "transparent", borderRadius: r, boxShadow: "none" };
}
