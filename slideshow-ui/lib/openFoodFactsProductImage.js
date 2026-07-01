/**
 * Open Food Facts product JSON → best-effort pack photo URL.
 * Used by /api/labely and /api/labely-food-suggestions.
 */

/** Collect http(s) URLs from nested OFF `selected_images` blobs (any locale / size bucket). */
function collectOpenFoodFactsImageUrls(obj, out = [], depth = 0) {
  if (depth > 8 || out.length >= 12) return out;
  if (typeof obj === "string") {
    const s = obj.trim();
    if (/^https?:\/\//i.test(s)) out.push(s);
    return out;
  }
  if (!obj || typeof obj !== "object") return out;
  for (const v of Object.values(obj)) collectOpenFoodFactsImageUrls(v, out, depth + 1);
  return out;
}

export function extractOpenFoodFactsImage(product) {
  if (!product || typeof product !== "object") return "";
  const fromSelected = collectOpenFoodFactsImageUrls(product.selected_images?.front, [])[0] || "";
  return (
    product.image_front_url ||
    product.image_url ||
    fromSelected ||
    ""
  );
}

export function sniffImageMimeFromBytes(ab) {
  if (!ab || ab.byteLength < 12) return null;
  const u = new Uint8Array(ab, 0, Math.min(16, ab.byteLength));
  if (u[0] === 0xff && u[1] === 0xd8 && u[2] === 0xff) return "image/jpeg";
  if (u[0] === 0x89 && u[1] === 0x50 && u[2] === 0x4e && u[3] === 0x47) return "image/png";
  if (u[0] === 0x47 && u[1] === 0x49 && u[2] === 0x46) return "image/gif";
  if (u[0] === 0x52 && u[1] === 0x49 && u[2] === 0x46 && u[3] === 0x46 && u[8] === 0x57 && u[9] === 0x45 && u[10] === 0x42 && u[11] === 0x50) return "image/webp";
  return null;
}
