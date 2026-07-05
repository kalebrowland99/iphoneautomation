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

function newRunSeed() {
  return `${Date.now()}-${Math.random()}`;
}

/** Deterministic shuffle from a string seed (unique job id → unique lineup). */
function seededShuffle(items, seed) {
  const arr = [...items];
  let state = 0;
  const s = String(seed || "labely-farm");
  for (let i = 0; i < s.length; i++) {
    state = (state * 31 + s.charCodeAt(i)) >>> 0;
  }
  const rand = () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 0x100000000;
  };
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

/**
 * One genre per video slot on every phone (video 1 / 2 / 3). New shuffle each run.
 * Example: video 1 = chips, video 2 = cereal, video 3 = soda.
 */
export function pickLabelyFarmVideoGenres(seed = "") {
  const shuffled = seededShuffle(
    UNHEALTHY_AMERICAN_FOOD_CATEGORIES,
    `${seed || newRunSeed()}:genres`,
  );
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
 * Random within the genre pool, seeded per run + phone + video slot.
 */
export function productsForFarmVideo(genreCategory, phoneIndex, videoOnPhone = 1, seed = "") {
  const pool = Array.isArray(genreCategory?.items) ? genreCategory.items.filter(Boolean) : [];
  const genreLabel = String(genreCategory?.name || "Packaged food").trim();
  if (!pool.length) {
    return Array.from({ length: LABELY_FARM_SCAN_SLOTS }, (_, i) => `${genreLabel} item ${i + 1}`);
  }
  const shuffleSeed = `${seed || newRunSeed()}:p${phoneIndex}:v${videoOnPhone}:${genreLabel}`;
  const shuffled = seededShuffle(pool, shuffleSeed);
  const items = [];
  const seen = new Set();
  for (const name of shuffled) {
    const trimmed = String(name || "").trim();
    const key = trimmed.toLowerCase();
    if (!trimmed || seen.has(key)) continue;
    seen.add(key);
    items.push(trimmed);
    if (items.length >= LABELY_FARM_SCAN_SLOTS) break;
  }
  while (items.length < LABELY_FARM_SCAN_SLOTS) {
    items.push(`${genreLabel} item ${items.length + 1}`);
  }
  return items;
}

/**
 * Build the full farm video plan: each video = one genre, three brands in that genre.
 * Pass options.seed (farm job id) so each Run button press gets a fresh lineup.
 * Brave photos resolve once per unique product name and reuse across phones.
 */
export function buildLabelyFarmVideoPlan(options = {}) {
  const phoneCount = Math.max(1, Number(options.phoneCount) || LABELY_FARM_PHONE_COUNT);
  const videosPerPhone = Math.max(1, Number(options.videosPerPhone) || LABELY_FARM_VIDEOS_PER_PHONE);
  const totalVideos = phoneCount * videosPerPhone;
  const seed = String(options.seed || newRunSeed());
  const videoGenres = pickLabelyFarmVideoGenres(seed);

  const batches = [];
  for (let v = 0; v < totalVideos; v++) {
    const phoneIndex = Math.floor(v / videosPerPhone);
    const videoOnPhone = (v % videosPerPhone) + 1;
    const genre = videoGenres[videoOnPhone - 1] ?? videoGenres[0];
    const genreName = genre?.name ?? "Packaged food";
    const items = productsForFarmVideo(genre, phoneIndex, videoOnPhone, seed);
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
