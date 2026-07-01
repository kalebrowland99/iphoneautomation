import { UNHEALTHY_AMERICAN_FOOD_CATEGORIES } from "@/lib/unhealthyAmericanFoods";

/** Farm gallery: 20 phones × 3 MP4s each. */
export const LABELY_FARM_PHONE_COUNT = 20;
export const LABELY_FARM_VIDEOS_PER_PHONE = 3;
export const LABELY_FARM_VIDEO_COUNT = LABELY_FARM_PHONE_COUNT * LABELY_FARM_VIDEOS_PER_PHONE;
/** Product scan slides per video — three brands from the same genre. */
export const LABELY_FARM_SCAN_SLOTS = 3;

/** Back-compat aliases used elsewhere. */
export const LABELY_FARM_BATCH_COUNT = LABELY_FARM_VIDEO_COUNT;
export const LABELY_ITEMS_PER_BATCH = LABELY_FARM_SCAN_SLOTS;

function mulberry32(seed) {
  let t = seed >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

function dailyShuffle(items, salt = "") {
  const day = new Date().toISOString().slice(0, 10);
  let seed = 0;
  for (const ch of `${day}:${salt}`) seed = (Math.imul(seed, 31) + ch.charCodeAt(0)) >>> 0;
  const rand = mulberry32(seed || 1);
  const arr = [...items];
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

/**
 * One genre per video slot on every phone (video 1 / 2 / 3). Rotates daily.
 * Example: video 1 = chips, video 2 = cereal, video 3 = soda.
 */
export function pickLabelyFarmVideoGenres() {
  const shuffled = dailyShuffle(UNHEALTHY_AMERICAN_FOOD_CATEGORIES, "labely-farm-video-genres");
  const picked = shuffled.slice(0, LABELY_FARM_VIDEOS_PER_PHONE);
  if (picked.length >= LABELY_FARM_VIDEOS_PER_PHONE) return picked;
  return UNHEALTHY_AMERICAN_FOOD_CATEGORIES.slice(0, LABELY_FARM_VIDEOS_PER_PHONE);
}

/** @deprecated — use pickLabelyFarmVideoGenres */
export function pickLabelyFarmFoodTypes() {
  return pickLabelyFarmVideoGenres();
}

/**
 * Three brand names from one genre for a single video.
 * Offset by phone so different phones can get different triplets in the same genre.
 */
export function productsForFarmVideo(genreCategory, phoneIndex) {
  const pool = Array.isArray(genreCategory?.items) ? genreCategory.items.filter(Boolean) : [];
  const genreLabel = String(genreCategory?.name || "Packaged food").trim();
  if (!pool.length) {
    return Array.from({ length: LABELY_FARM_SCAN_SLOTS }, (_, i) => `${genreLabel} item ${i + 1}`);
  }
  const start = (Math.max(0, phoneIndex) * LABELY_FARM_SCAN_SLOTS) % pool.length;
  const items = [];
  const seen = new Set();
  for (let i = 0; i < pool.length && items.length < LABELY_FARM_SCAN_SLOTS; i++) {
    const name = String(pool[(start + i) % pool.length]).trim();
    const key = name.toLowerCase();
    if (!name || seen.has(key)) continue;
    seen.add(key);
    items.push(name);
  }
  while (items.length < LABELY_FARM_SCAN_SLOTS) {
    items.push(`${genreLabel} item ${items.length + 1}`);
  }
  return items;
}

/**
 * Build the full farm video plan: each video = one genre, three brands in that genre.
 * Brave photos resolve once per unique product name and reuse across phones.
 */
export function buildLabelyFarmVideoPlan(options = {}) {
  const phoneCount = Math.max(1, Number(options.phoneCount) || LABELY_FARM_PHONE_COUNT);
  const videosPerPhone = Math.max(1, Number(options.videosPerPhone) || LABELY_FARM_VIDEOS_PER_PHONE);
  const totalVideos = phoneCount * videosPerPhone;
  const videoGenres = pickLabelyFarmVideoGenres();

  const batches = [];
  for (let v = 0; v < totalVideos; v++) {
    const phoneIndex = Math.floor(v / videosPerPhone);
    const videoOnPhone = (v % videosPerPhone) + 1;
    const genre = videoGenres[videoOnPhone - 1] ?? videoGenres[0];
    const genreName = genre?.name ?? "Packaged food";
    const items = productsForFarmVideo(genre, phoneIndex);
    batches.push({
      id: `phone-${phoneIndex + 1}-video-${videoOnPhone}`,
      name: `Phone ${phoneIndex + 1} · video ${videoOnPhone} · ${genreName}`,
      phoneIndex,
      videoOnPhone,
      batchNumber: v + 1,
      itemsRaw: items.join("\n"),
      slideshowCount: 1,
      foodDbMatches: {},
      foodGenre: genreName,
      foodTypes: [genreName],
    });
  }
  return batches;
}

/** Unique product names across a farm video plan (one Brave search each when reusing photos). */
export function uniqueProductNamesInFarmPlan(batches) {
  const seen = new Set();
  const out = [];
  for (const batch of batches ?? []) {
    for (const line of String(batch?.itemsRaw || "").split("\n")) {
      const name = line.trim();
      if (!name) continue;
      const key = name.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(name);
    }
  }
  return out;
}

/** @deprecated name — returns the farm video plan (async for route compat). */
export async function buildLabelyFarmBatches(options = {}) {
  return buildLabelyFarmVideoPlan(options);
}
