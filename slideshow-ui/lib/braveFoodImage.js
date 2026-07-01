/**
 * Brave Search Image API for food photos.
 * Requires BRAVE_SEARCH_API_KEY (Search plan — image search included).
 * @see https://api-dashboard.search.brave.com/api-reference/images/image_search
 */

import { recordBraveSearches } from "@/lib/braveUsage";
import {
  braveImageContentHash,
  getUsedBraveImageUrls,
  markBraveImagesUsed,
  normalizeBraveImageUrl,
} from "@/lib/braveUsedImages";

const BRAVE_IMAGE_SEARCH = "https://api.search.brave.com/res/v1/images/search";
const FETCH_MS = 15_000;

/** Build the Brave image query from a food name. */
export function buildBraveFoodSearchQuery(foodName) {
  const q = String(foodName || "").trim();
  if (!q) return "";
  return `${q} in store`;
}

/** Alternate queries tried before recycling or giving up (each = 1 API search). */
export function alternateBraveFoodSearchQueries(foodName) {
  const q = String(foodName || "").trim();
  if (!q) return [];
  const seen = new Set();
  const out = [];
  for (const candidate of [
    buildBraveFoodSearchQuery(q),
    `${q} grocery store aisle`,
    `${q} product packaging`,
    `${q} supermarket shelf`,
    q,
  ]) {
    const key = candidate.toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(candidate);
  }
  return out;
}

export function braveImagesConfigured() {
  return Boolean(process.env.BRAVE_SEARCH_API_KEY?.trim());
}

/**
 * @param {string} query
 * @param {{ count?: number, excludeUrls?: Iterable<string> }} [opts]
 * @returns {Promise<{ items: { link: string, title: string, thumbnail: string }[], configured: boolean, status?: number }>}
 */
export async function searchBraveFoodImages(query, { count = 10, excludeUrls } = {}) {
  const key = process.env.BRAVE_SEARCH_API_KEY?.trim();
  if (!key) return { items: [], configured: false };

  const searchQ = buildBraveFoodSearchQuery(query);
  if (!searchQ) return { items: [], configured: true };

  const params = new URLSearchParams({
    q: searchQ,
    count: String(Math.min(Math.max(count, 1), 50)),
    country: "US",
    search_lang: "en",
    safesearch: "strict",
    spellcheck: "true",
  });

  try {
    const res = await fetch(`${BRAVE_IMAGE_SEARCH}?${params.toString()}`, {
      headers: {
        Accept: "application/json",
        "X-Subscription-Token": key,
      },
      cache: "no-store",
      signal: AbortSignal.timeout(FETCH_MS),
    });
    await recordBraveSearches(1);
    if (!res.ok) return { items: [], configured: true, status: res.status };
    const data = await res.json().catch(() => ({}));
    const { usedUrls } = await buildUsedBraveUrlSet(excludeUrls);
    const items = Array.isArray(data?.results)
      ? data.results
          .map((item) => ({
            link: String(item?.properties?.url || item?.url || "").trim(),
            title: String(item?.title || "").trim(),
            thumbnail: String(item?.thumbnail?.src || item?.thumbnail || "").trim(),
          }))
          .filter((item) => item.link && !usedUrls.has(normalizeBraveImageUrl(item.link)))
      : [];
    return { items, configured: true };
  } catch {
    return { items: [], configured: true };
  }
}

/**
 * Persisted + in-session URLs that must not be picked again.
 * @param {Iterable<string> | undefined} excludeUrls
 * @param {Iterable<string> | undefined} excludeContentHashes
 */
async function buildUsedBraveUrlSet(excludeUrls, excludeContentHashes, { includePersisted = true } = {}) {
  const used = includePersisted ? await getUsedBraveImageUrls() : new Set();
  if (excludeUrls) {
    for (const raw of excludeUrls) {
      const norm = normalizeBraveImageUrl(raw);
      if (norm) used.add(norm);
    }
  }
  const usedHashes = new Set();
  if (excludeContentHashes) {
    for (const raw of excludeContentHashes) {
      const h = String(raw || "").trim();
      if (h) usedHashes.add(h);
    }
  }
  return { usedUrls: used, usedHashes };
}

async function pickFromBraveQueries(queries, { usedUrls, usedHashes, persistUsed, filterUsedUrls }) {
  for (const query of queries) {
    const searchQ = String(query || "").trim();
    if (!searchQ) continue;
    const excludeUrls = filterUsedUrls ? [...usedUrls] : undefined;
    const { items } = await searchBraveFoodImages(searchQ, { count: 80, excludeUrls });
    for (const item of items) {
      const sourceUrl = String(item?.link || "").trim();
      const picked = await tryBraveSourceUrl(sourceUrl, usedUrls, usedHashes, { persistUsed });
      if (picked) return picked;
    }
  }
  return null;
}

/**
 * Pick an unused Brave food photo and return as a data URL (server-side fetch).
 * Marks the URL used immediately so later slots / slideshows never reuse it.
 * @param {string} query — food name from the list / GPT seed
 * @param {{ excludeUrls?: Iterable<string>, excludeContentHashes?: Iterable<string> }} [opts]
 * @returns {Promise<{ dataUrl: string, sourceUrl: string, contentHash: string } | null>}
 */
export async function pickBraveFoodImageDataUrl(query, {
  excludeUrls,
  excludeContentHashes,
  persistUsed = true,
  allowRecycle = true,
} = {}) {
  const q = String(query || "").trim();
  if (!q || !braveImagesConfigured()) return null;

  const queries = alternateBraveFoodSearchQueries(q);
  const { usedUrls, usedHashes } = await buildUsedBraveUrlSet(excludeUrls, excludeContentHashes);

  const fresh = await pickFromBraveQueries(queries, {
    usedUrls,
    usedHashes,
    persistUsed,
    filterUsedUrls: true,
  });
  if (fresh) return { ...fresh, recycled: false };

  if (!allowRecycle) return null;

  const sessionOnly = await buildUsedBraveUrlSet(excludeUrls, excludeContentHashes, {
    includePersisted: false,
  });
  const recycled = await pickFromBraveQueries(queries.slice(0, 3), {
    usedUrls: sessionOnly.usedUrls,
    usedHashes: sessionOnly.usedHashes,
    persistUsed,
    filterUsedUrls: false,
  });
  if (recycled) return { ...recycled, recycled: true };

  return null;
}

/**
 * Use a known Brave image URL (food-db preset) with the same dedup rules as search picks.
 * @param {string} sourceUrl
 * @param {{ excludeUrls?: Iterable<string>, excludeContentHashes?: Iterable<string> }} [opts]
 */
export async function braveUrlToImagePick(sourceUrl, {
  excludeUrls,
  excludeContentHashes,
  persistUsed = true,
  allowReuse = false,
} = {}) {
  const { usedUrls, usedHashes } = await buildUsedBraveUrlSet(excludeUrls, excludeContentHashes, {
    includePersisted: !allowReuse,
  });
  return tryBraveSourceUrl(String(sourceUrl || "").trim(), usedUrls, usedHashes, { persistUsed });
}

async function tryBraveSourceUrl(sourceUrl, usedUrls, usedHashes, { persistUsed = true } = {}) {
  const norm = normalizeBraveImageUrl(sourceUrl);
  if (!sourceUrl || !norm || usedUrls.has(norm)) return null;
  const fetched = await fetchRemoteImageBuffer(sourceUrl);
  if (!fetched) return null;
  const contentHash = braveImageContentHash(fetched.buffer);
  if (contentHash && usedHashes.has(contentHash)) return null;
  const dataUrl = `data:${fetched.contentType};base64,${fetched.buffer.toString("base64")}`;
  if (!dataUrl.startsWith("data:image/")) return null;
  if (persistUsed) await markBraveImagesUsed([sourceUrl]);
  usedUrls.add(norm);
  if (contentHash) usedHashes.add(contentHash);
  return { dataUrl, sourceUrl, contentHash };
}

/** @param {string} url */
async function fetchRemoteImageBuffer(url) {
  try {
    const res = await fetch(url, {
      headers: {
        Accept: "image/*",
        "User-Agent": "AutoSlideshow/1.0 (Labely Brave food photo)",
      },
      redirect: "follow",
      cache: "no-store",
      signal: AbortSignal.timeout(FETCH_MS),
    });
    if (!res.ok) return null;
    const contentType = String(res.headers.get("content-type") || "image/jpeg")
      .split(";")[0]
      .trim();
    if (!contentType.startsWith("image/")) return null;
    const buf = Buffer.from(await res.arrayBuffer());
    if (!buf.length) return null;
    return { buffer: buf, contentType };
  } catch {
    return null;
  }
}
