import { braveImagesConfigured, pickBraveFoodImageDataUrl, searchBraveFoodImages } from "@/lib/braveFoodImage";
import { getUsedBraveImageUrls, normalizeBraveImageUrl } from "@/lib/braveUsedImages";

/** Resolve a food name to Brave image candidates (same shape as /api/labely-food-suggestions). */
export async function lookupFoodBrave(query) {
  const q = String(query || "").trim();
  if (!q) return { query: q, status: "empty" };
  if (!braveImagesConfigured()) {
    return { query: q, status: "error", error: "Brave Image Search is not configured on the server." };
  }

  const used = await getUsedBraveImageUrls();
  const buildDetails = (items, { filterUsed }) => items.slice(0, 20).map((item, i) => ({
    label: item.title || `${q} (${i + 1})`,
    imageUrl: item.link,
  })).filter((d) => !filterUsed || !used.has(normalizeBraveImageUrl(d.imageUrl)));

  let { items } = await searchBraveFoodImages(q, { count: 20 });
  let candidateDetails = buildDetails(items, { filterUsed: true });
  let recycled = false;

  if (!candidateDetails.length && items.length) {
    candidateDetails = buildDetails(items, { filterUsed: false });
    recycled = candidateDetails.length > 0;
  }

  if (!candidateDetails.length) {
    const pick = await pickBraveFoodImageDataUrl(q, { allowRecycle: true });
    if (pick?.sourceUrl) {
      candidateDetails = [{
        label: q,
        imageUrl: pick.sourceUrl,
      }];
      recycled = Boolean(pick.recycled);
    }
  }

  if (!candidateDetails.length) return { query: q, status: "missing" };
  const candidates = candidateDetails.map((d) => d.label);
  return {
    query: q,
    status: "found",
    match: candidates[0] || q,
    candidates,
    candidateDetails,
    ...(recycled ? { recycled: true } : {}),
  };
}
