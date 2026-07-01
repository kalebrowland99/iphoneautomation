/** Caption font size in 1080px design space — always 47–55px, stable for a given seed. */

export const CAPTION_FONT_MIN = 47;
export const CAPTION_FONT_MAX = 55;

export function captionFontSize1080(seedKey) {
  const s = String(seedKey ?? "default");
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619) >>> 0;
  return CAPTION_FONT_MIN + (h % (CAPTION_FONT_MAX - CAPTION_FONT_MIN + 1));
}
