/** Default batch configs for unattended /automation farm runs. */

export const LABELY_FARM_PHONE_COUNT = 20;
export const LABELY_FARM_VIDEOS_PER_PHONE = 3;
export const LABELY_BATCH_COUNT = LABELY_FARM_PHONE_COUNT * LABELY_FARM_VIDEOS_PER_PHONE;

/** Static fallback when Brave is unavailable (3 food types × sample products). */
export const DEFAULT_LABELY_FOOD_BATCHES = [
  {
    name: "Sugary drinks",
    items: ["Coca-Cola", "Mountain Dew", "Red Bull"],
    slideshowCount: 1,
  },
  {
    name: "Chips & snacks",
    items: ["Doritos", "Cheetos", "Lay's Classic"],
    slideshowCount: 1,
  },
  {
    name: "Candy & chocolate",
    items: ["Snickers", "M&M's", "Skittles"],
    slideshowCount: 1,
  },
];

function labelyFoodDbBatches() {
  return DEFAULT_LABELY_FOOD_BATCHES.map((batch, i) => ({
    id: `batch-${i + 1}`,
    name: batch.name,
    itemsRaw: batch.items.join("\n"),
    slideshowCount: batch.slideshowCount,
  }));
}

export function getFarmDefaults(brand) {
  const key = String(brand || "labely").trim().toLowerCase();
  if (key === "valcoin") {
    return {
      brand: "valcoin",
      config: {
        appId: "valcoin",
        outputFormat: "labelyScan",
        labelyScanSlotCount: 1,
      },
    };
  }
  return {
    brand: "labely",
    config: {
      appId: "labely",
      outputFormat: "labelyScan",
      labelyAiProducts: true,
      labelyUseFoodDatabasePhotos: true,
      labelyUseBraveImages: true,
      labelyUseSelfieImage: false,
      labelyScanSlotCount: 3,
      labelyFoodDbBatches: labelyFoodDbBatches(),
    },
    batchCount: LABELY_BATCH_COUNT,
  };
}
