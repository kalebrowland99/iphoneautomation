import { inlineSlotImageFields } from "@/lib/exportImagePrepare";
import { isLabelyScanTourFormat, scanTourSlotCount } from "@/lib/slideLayout";

/** Apps that load Numista catalogue photos (CORS blocks direct export). */
export function needsExportImageInlining(config) {
  const aid = config?.appId ?? "thrifty";
  return aid === "valcoin" || aid === "labely";
}

/**
 * Remote catalogue URLs break html-to-image / canvas export (CORS).
 * Inline data URLs before capture so every slide produces frames.
 * @param {object} config
 * @returns {Promise<object>}
 */
export async function ensureExportImageUrls(config) {
  if (!config || !Array.isArray(config.slots)) return config;

  const slots = config.slots.map((s) => ({ ...s }));
  const slotCount = isLabelyScanTourFormat(config)
    ? Math.min(slots.length, scanTourSlotCount(config) + 1)
    : slots.length;

  for (let i = 0; i < slotCount; i++) {
    slots[i] = await inlineSlotImageFields(slots[i]);
  }

  return { ...config, slots };
}
