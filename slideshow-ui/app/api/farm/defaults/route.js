import { getFarmDefaults } from "@/lib/farmDefaults";
import { buildLabelyFarmBatches, pickLabelyFarmVideoGenres } from "@/lib/farmLabelyFoods";

export const maxDuration = 300;

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const brand = searchParams.get("brand") || "labely";
  const key = String(brand).trim().toLowerCase();
  const phoneCount = Math.max(1, Number(searchParams.get("phoneCount")) || 20);
  const videosPerPhone = Math.max(1, Number(searchParams.get("videosPerPhone")) || 3);

  if (key === "labely") {
    const labelyFoodDbBatches = await buildLabelyFarmBatches({ phoneCount, videosPerPhone });
    const videoGenres = pickLabelyFarmVideoGenres().map((c) => c.name);
    return Response.json({
      brand: "labely",
      config: {
        appId: "labely",
        outputFormat: "labelyScan",
        labelyAiProducts: true,
        labelyUseFoodDatabasePhotos: true,
        labelyUseBraveImages: true,
        labelyBraveReusePhotos: true,
        labelyUseSelfieImage: false,
        labelyScanSlotCount: 3,
        labelyFarmVideoGenres: videoGenres,
        labelyFoodDbBatches,
      },
      batchCount: labelyFoodDbBatches.length,
      videoCount: phoneCount * videosPerPhone,
      videoGenres,
      foodTypes: videoGenres,
      source: "farm-plan",
    });
  }  return Response.json(getFarmDefaults(key));
}
