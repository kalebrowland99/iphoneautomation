/**
 * In-memory Brave picks reserved for one slideshow generation (per client token).
 * Prevents the same photo from appearing twice in a single slideshow even under
 * concurrent / overlapping API requests.
 */

import { normalizeBraveImageUrl } from "@/lib/braveUsedImages";

const RESERVE_TTL_MS = 60 * 60 * 1000;
/** @type {Map<string, { urls: Set<string>, hashes: Set<string>, expiresAt: number }>} */
const stores = new Map();

function purgeExpired() {
  const now = Date.now();
  for (const [token, entry] of stores) {
    if (entry.expiresAt <= now) stores.delete(token);
  }
}

function getOrCreate(token) {
  purgeExpired();
  const key = String(token || "").trim();
  if (!key) return null;
  let entry = stores.get(key);
  if (!entry) {
    entry = { urls: new Set(), hashes: new Set(), expiresAt: Date.now() + RESERVE_TTL_MS };
    stores.set(key, entry);
  } else {
    entry.expiresAt = Date.now() + RESERVE_TTL_MS;
  }
  return entry;
}

/** @param {string} token */
export function getSlideshowBraveExclude(token) {
  const entry = getOrCreate(token);
  if (!entry) return { urls: [], hashes: [] };
  return { urls: [...entry.urls], hashes: [...entry.hashes] };
}

/**
 * @param {string} token
 * @param {string} sourceUrl
 * @param {string} [contentHash]
 */
export function noteSlideshowBravePick(token, sourceUrl, contentHash) {
  const entry = getOrCreate(token);
  if (!entry) return;
  const norm = normalizeBraveImageUrl(sourceUrl);
  if (norm) entry.urls.add(norm);
  const h = String(contentHash || "").trim();
  if (h) entry.hashes.add(h);
}
