/**
 * Estimate Brave Image Search API calls for a farm Labely run.
 * @param {{ videoCount?: number, scansPerVideo?: number, reuseByProduct?: boolean, uniqueProductCount?: number }} opts
 */
export function estimateBraveSearchesForFarm({
  videoCount = 60,
  scansPerVideo = 3,
  reuseByProduct = true,
  uniqueProductCount = null,
} = {}) {
  if (reuseByProduct) {
    if (Number.isFinite(uniqueProductCount) && uniqueProductCount >= 0) {
      return Math.floor(uniqueProductCount);
    }
    // ~15 products per category column × 3 types (pool size), names repeat across videos
    const columns = Math.max(1, Math.floor(Number(scansPerVideo) || 3));
    return columns * 15;
  }
  const videos = Math.max(0, Math.floor(Number(videoCount) || 0));
  const scans = Math.max(0, Math.floor(Number(scansPerVideo) || 0));
  return videos * scans;
}
