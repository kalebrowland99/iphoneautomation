import { sniffImageMimeFromBytes } from "@/lib/openFoodFactsProductImage";

/**
 * Download a remote image and return a data URL (for same-origin export / canvas).
 * @param {string} imageUrl
 * @param {string} [userAgent]
 * @returns {Promise<string | null>}
 */
const FETCH_MS = 20_000;

const BROWSER_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

/** Numista CDN is behind Cloudflare; bare fetch gets 403 — need browser-like headers. */
const FETCH_HEADER_STRATEGIES = [
  () => ({
    "User-Agent": BROWSER_UA,
    Accept: "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    Referer: "https://en.numista.com/",
    "Sec-Fetch-Dest": "image",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "same-site",
  }),
  (ua) => ({
    "User-Agent": ua || BROWSER_UA,
    Accept: "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    Referer: "https://en.numista.com/",
  }),
  (ua) => ({ "User-Agent": ua || BROWSER_UA, Accept: "image/*,*/*;q=0.8" }),
];

function arrayBufferToBase64(ab) {
  if (typeof Buffer !== "undefined") return Buffer.from(ab).toString("base64");
  const bytes = new Uint8Array(ab);
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}

function looksLikeImageBytes(ab, headerMime) {
  if (!ab || ab.byteLength <= 0) return false;
  const ct = String(headerMime || "").toLowerCase();
  if (ct.includes("text/html") || ct.includes("application/json")) return false;
  if (ct.startsWith("image/")) return true;
  return Boolean(sniffImageMimeFromBytes(ab));
}

export async function fetchRemoteImageDataUrl(imageUrl, userAgent = BROWSER_UA) {
  if (!imageUrl || typeof imageUrl !== "string") return null;
  const target = imageUrl.trim();
  if (!target) return null;

  for (const headersFor of FETCH_HEADER_STRATEGIES) {
    try {
      const res = await fetch(target, {
        headers: headersFor(userAgent),
        redirect: "follow",
        cache: "no-store",
        signal: AbortSignal.timeout(FETCH_MS),
      });
      if (!res.ok) continue;
      const ab = await res.arrayBuffer();
      if (ab.byteLength <= 0 || ab.byteLength > 25 * 1024 * 1024) continue;
      const headerMime = (res.headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
      if (!looksLikeImageBytes(ab, headerMime)) continue;
      let mime = headerMime.startsWith("image/") ? headerMime : null;
      if (!mime) mime = sniffImageMimeFromBytes(ab);
      if (!mime) continue;
      return `data:${mime};base64,${arrayBufferToBase64(ab)}`;
    } catch {
      /* try next strategy */
    }
  }
  return null;
}
