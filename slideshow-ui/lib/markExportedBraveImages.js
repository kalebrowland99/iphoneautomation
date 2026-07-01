/**
 * Mark Brave food photos as used after slideshow export so they are not picked again.
 */

/** @param {object | null | undefined} cfg */
export function collectBraveImageUrlsFromConfig(cfg) {
  if ((cfg?.appId ?? "") !== "labely" || !cfg?.labelyUseBraveImages) return [];
  const urls = new Set();
  for (const slot of cfg?.slots ?? []) {
    const u = String(slot?.labelyDbImageUrl || "").trim();
    if (/^https?:\/\//i.test(u)) urls.add(u);
  }
  return [...urls];
}

/** @param {object | object[] | null | undefined} cfgOrCfgs */
export async function markExportedBraveImagesUsed(cfgOrCfgs) {
  const cfgs = Array.isArray(cfgOrCfgs) ? cfgOrCfgs : cfgOrCfgs ? [cfgOrCfgs] : [];
  const urls = new Set();
  for (const cfg of cfgs) {
    for (const u of collectBraveImageUrlsFromConfig(cfg)) urls.add(u);
  }
  if (!urls.size) return;

  try {
    await fetch("/api/brave-used-images", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls: [...urls] }),
    });
  } catch (err) {
    console.warn("[markExportedBraveImages]", err);
  }
}

/** @param {string} url */
export async function markExportedBraveImageUrl(url) {
  const u = String(url || "").trim();
  if (!/^https?:\/\//i.test(u)) return;
  await markExportedBraveImagesUsed({
    appId: "labely",
    labelyUseBraveImages: true,
    slots: [{ labelyDbImageUrl: u }],
  });
}
