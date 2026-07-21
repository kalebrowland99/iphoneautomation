import {
  LABELY_SCAN_TOUR_INTRO_SLIDES,
  isLabelyScanTourFormat,
  isLabelySingleSlideFormat,
  scanTourSlotCount,
} from "@/lib/slideLayout";

/** Short centered outro lines — variations of “the app i use is called labely”. */
export const LABELY_OUTRO_TEXT_POOL = [
  "the app i use is called labely",
  "i check everything on labely before i buy it",
  "labely is the app i use to read ingredient labels",
  "i scan my groceries on labely first",
  "the app that shows me what is really in my food is labely",
  "i use labely every time i go grocery shopping",
  "labely is how i find out what brands hide",
  "before i eat this i check it on labely",
  "i found this out with an app called labely",
  "labely is the app i trust for clean ingredients",
];

function hashSeed(seed) {
  const s = String(seed ?? "");
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function pickLabelyOutroText(seed = "") {
  const pool = LABELY_OUTRO_TEXT_POOL;
  if (!pool.length) return "the app i use is called labely";
  const idx = hashSeed(seed) % pool.length;
  return pool[idx];
}

export function shouldShowLabelyOutro(_config, _itemIndex = 0) {
  // Outro CTA (“i use this app… / labely”) disabled — last slides show product UI only.
  return false;
}

/** Slide index in VideoPreview for the last Labely scan segment. */
export function lastLabelySlideIndex(config) {
  if ((config?.appId ?? "thrifty") !== "labely") return 0;
  if (isLabelySingleSlideFormat(config)) return 0;
  if (isLabelyScanTourFormat(config)) {
    return LABELY_SCAN_TOUR_INTRO_SLIDES + scanTourSlotCount(config) - 1;
  }
  return 0;
}

export function resolveLabelyOutroText(config, seed = "") {
  const explicit = String(config?.labelyOutroText || "").trim();
  if (explicit) return explicit;
  const jitter = config?.jitterSeed ?? 0;
  return pickLabelyOutroText(`${jitter}:${seed}`);
}
