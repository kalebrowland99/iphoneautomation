/** Shared slide indexing for standard / app-only / pose-person / iMessage-mom / starterPack formats. */

function appScreenType(config) {
  return (config?.appId ?? "thrifty") === "labely" ? "labely" : "thrifty";
}

/** Default slides/SKUs in "Labely + scan intro" (batch exports may override this per saved show). */
export const LABELY_SCAN_TOUR_SLOTS = 3;
export const LABELY_SCAN_TOUR_INTRO_SLIDES = 1;

/** Slides/SKUs in "Valcoin coin tour" — opening 6-coin collage, then scan ×6 + slide-up. */
export const VALCOIN_TOUR_SLOTS = 6;

/** Labely grocery tour or Valcoin coin tour — same scan export pipeline, different counts. */
export function isLabelyScanTourFormat(config) {
  const aid = config?.appId ?? "thrifty";
  return (aid === "labely" || aid === "valcoin") && (config?.outputFormat ?? "standard") === "labelyScan";
}

/** Per-app number of coin/grocery slots in the scan tour. */
export function scanTourSlotCount(config) {
  if ((config?.appId ?? "thrifty") === "valcoin") return VALCOIN_TOUR_SLOTS;
  const n = Math.floor(Number(config?.labelyScanSlotCount));
  return Number.isFinite(n) && n > 0 ? n : LABELY_SCAN_TOUR_SLOTS;
}

/** Valcoin has exactly one output format now (collage + scan tour). */
export function normalizeValcoinOutputFormat(_fmt) {
  return "labelyScan";
}

/** One fullscreen Labely card (slot 1), no collage. */
export function isLabelySingleSlideFormat(config) {
  const f = config?.outputFormat ?? "standard";
  return (config?.appId ?? "thrifty") === "labely" && f === "labelyOnly";
}

/** Formats that skip the opening collage slide. */
export function skipsCollageOpening(config) {
  if (isLabelySingleSlideFormat(config)) return true;
  // Valcoin scan tour opens with a 6-coin collage, so it does NOT skip the collage.
  if (isLabelyScanTourFormat(config) && (config?.appId ?? "thrifty") === "valcoin") return false;
  return isLabelyScanTourFormat(config);
}

export function getTotalSlides(config) {
  const n = config.slots?.length ?? 6;
  const f = config.outputFormat ?? "standard";
  if (isLabelyScanTourFormat(config)) return LABELY_SCAN_TOUR_INTRO_SLIDES + scanTourSlotCount(config);
  if (isLabelySingleSlideFormat(config)) return 1;
  if (f === "posePerson") return n;
  if (f === "imessageMom") return 4;
  if (f === "appOnly") return 1 + n;
  if (f === "starterPack") return 1; // single logical slide; export loop handles phases
  return 1 + n * 2;
}

/**
 * @returns {object} Slide descriptor for preview/export.
 */
export function getSlideInfo(config, slideIndex) {
  const f = config.outputFormat ?? "standard";
  const slots = config.slots ?? [];

  if (isLabelyScanTourFormat(config)) {
    const aid = config?.appId ?? "thrifty";
    const tourSlots = scanTourSlotCount(config);
    if (slideIndex === 0) {
      // Valcoin opens with a 6-coin collage; Labely opens with its single-image shelf intro.
      if (aid === "valcoin") return { type: "collage" };
      return { type: "labelyShelfIntro", slot: slots[0], itemIndex: 0 };
    }
    const idx = Math.min(slideIndex - LABELY_SCAN_TOUR_INTRO_SLIDES, tourSlots - 1);
    if (aid === "valcoin") {
      return { type: "thrifty", slot: slots[idx] ?? slots[0], itemIndex: idx };
    }
    return { type: "labely", slot: slots[idx] ?? slots[0], itemIndex: idx };
  }

  if (isLabelySingleSlideFormat(config)) {
    return { type: "labely", slot: slots[0], itemIndex: 0 };
  }

  if (f === "posePerson") {
    const itemIndex = slideIndex;
    return { type: "fullBleed", slot: slots[itemIndex], itemIndex };
  }

  if (f === "starterPack") {
    return { type: "starterPack" };
  }

  if (f === "imessageMom") {
    const slot = slots[0];
    if (slideIndex === 0) return { type: "imessage",     slot, itemIndex: 0 };
    if (slideIndex === 1) return { type: "voicemail",    slot, itemIndex: 0 };
    if (slideIndex === 2) return { type: "imessageText", slot, itemIndex: 0 };
    return { type: appScreenType(config), slot, itemIndex: 0 };
  }

  if (slideIndex === 0) return { type: "collage" };

  if (f === "appOnly") {
    const itemIndex = slideIndex - 1;
    return { type: appScreenType(config), slot: slots[itemIndex], itemIndex };
  }

  const itemIndex = Math.floor((slideIndex - 1) / 2);
  const isReveal = (slideIndex - 1) % 2 === 0;
  return {
    type: isReveal ? "reveal" : appScreenType(config),
    slot: slots[itemIndex],
    itemIndex,
  };
}

/** Map preview slide index → slot index for AI refresh */
export function slideIndexToSlotIndex(slideIndex, config) {
  const f = config.outputFormat ?? "standard";
  if (f === "posePerson") return slideIndex;
  if (isLabelyScanTourFormat(config)) {
    if (slideIndex === 0) return null;
    return slideIndex - LABELY_SCAN_TOUR_INTRO_SLIDES;
  }
  if (isLabelySingleSlideFormat(config)) return 0;
  if (f === "imessageMom") return 0;
  if (f === "starterPack") return slideIndex; // slots 0-2 map directly
  if (slideIndex === 0) return null;
  if (f === "appOnly") return slideIndex - 1;
  return Math.floor((slideIndex - 1) / 2);
}
