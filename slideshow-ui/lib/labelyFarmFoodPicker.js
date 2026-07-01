import {
  UNHEALTHY_AMERICAN_FOOD_CATEGORIES,
  allUnhealthyAmericanFoods,
} from "@/lib/unhealthyAmericanFoods";

const LABELY_BATCH_COUNT = 3;
const FOODS_PER_BATCH = 3;

/** Deterministic shuffle from a string seed (farm job id). */
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
 * Pick random unhealthy American foods for Labely food-DB batch mode.
 * Photos are fetched via Brave Image Search ("{food} in store") during generation.
 *
 * @param {string} [seed] Farm job id — different job → different food lineup.
 */
export function pickRandomLabelyFoodBatches(seed = "") {
  const pool = seededShuffle(allUnhealthyAmericanFoods(), seed || String(Date.now()));
  const needed = LABELY_BATCH_COUNT * FOODS_PER_BATCH;
  const picks = [];
  while (picks.length < needed) {
    for (const food of pool) {
      if (picks.length >= needed) break;
      if (!picks.includes(food)) picks.push(food);
    }
    if (pool.length < needed && picks.length < needed) break;
  }

  const categories = seededShuffle(UNHEALTHY_AMERICAN_FOOD_CATEGORIES, `${seed}-cat`);
  const batches = [];
  for (let i = 0; i < LABELY_BATCH_COUNT; i++) {
    const slice = picks.slice(i * FOODS_PER_BATCH, (i + 1) * FOODS_PER_BATCH);
    const cat = categories[i % categories.length];
    batches.push({
      id: `batch-${i + 1}`,
      name: cat?.name || `Unhealthy picks ${i + 1}`,
      itemsRaw: slice.join("\n"),
      slideshowCount: 1,
    });
  }
  return batches;
}

export function labelyFoodDbBatches(seed = "") {
  return pickRandomLabelyFoodBatches(seed);
}

export { LABELY_BATCH_COUNT };
