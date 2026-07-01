/** First usable preview URL for a saved show (thumbnail in gallery rail). */
export function galleryThumbUrl(show) {
  const ps = String(show?.previewScreenshot || "").trim();
  if (ps) return ps;
  const slots = Array.isArray(show?.slots) ? show.slots : [];
  for (const s of slots) {
    const u = String(s?.imageUrl || "").trim();
    if (u) return u;
  }
  return null;
}

export function isBlankSavedShow(show) {
  return !galleryThumbUrl(show);
}

/**
 * Drop gallery entries with no preview image (failed/interrupted batch slots).
 * @param {object[]} shows
 * @param {number | null | undefined} activeShowIdx
 */
export function pruneBlankSavedSlideshows(shows, activeShowIdx = null) {
  const input = Array.isArray(shows) ? shows : [];
  const kept = [];
  let newActive = null;
  for (let i = 0; i < input.length; i++) {
    if (!isBlankSavedShow(input[i])) {
      if (typeof activeShowIdx === "number" && activeShowIdx === i) {
        newActive = kept.length;
      }
      kept.push(input[i]);
    }
  }
  return {
    shows: kept,
    activeShowIdx: newActive,
    removedCount: input.length - kept.length,
  };
}
