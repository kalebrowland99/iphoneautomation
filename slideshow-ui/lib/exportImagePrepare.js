/**
 * Export must not fetch cross-origin images from the browser (CORS).
 * Server proxies Numista bytes; we rewrite slot data + live DOM <img> src to data:
 * URLs before html-to-image (it re-fetches every http(s) src unless already data:).
 */

const NUMISTA_HOST = /^https:\/\/([a-z]{2}\.)?numista\.com\//i;
const WIKIMEDIA_HOST = /^https:\/\/upload\.wikimedia\.org\//i;

export function isDataImageUrl(url) {
  return String(url || "").trim().startsWith("data:image/");
}

export function isRemoteHttpImageUrl(url) {
  const s = String(url || "").trim();
  return /^https?:\/\//i.test(s);
}

/** Same-origin or root-relative — safe for html-to-image without proxying. */
export function isSameOriginImageUrl(url) {
  const s = String(url || "").trim();
  if (!s || isDataImageUrl(s) || s.startsWith("blob:")) return true;
  if (s.startsWith("/")) return true;
  if (typeof window === "undefined") return false;
  try {
    return new URL(s, window.location.href).origin === window.location.origin;
  } catch {
    return false;
  }
}

async function blobToDataUrl(blob) {
  if (!blob || !blob.type) return "";
  return await new Promise((resolve) => {
    const reader = new FileReader();
    reader.onerror = () => resolve("");
    reader.onloadend = () => resolve(typeof reader.result === "string" ? reader.result : "");
    reader.readAsDataURL(blob);
  });
}

async function directDataUrl(remoteUrl) {
  try {
    const res = await fetch(remoteUrl, { mode: "cors", credentials: "omit" });
    if (!res.ok) return "";
    const blob = await res.blob();
    const dataUrl = await blobToDataUrl(blob);
    return dataUrl.startsWith("data:image/") ? dataUrl : "";
  } catch {
    return "";
  }
}

async function nextImageDataUrl(remoteUrl) {
  const q = new URLSearchParams({ url: remoteUrl, w: "1080", q: "85" });
  try {
    const res = await fetch(`/_next/image?${q.toString()}`);
    if (!res.ok) return "";
    const blob = await res.blob();
    const dataUrl = await blobToDataUrl(blob);
    return dataUrl.startsWith("data:image/") ? dataUrl : "";
  } catch {
    return "";
  }
}

async function numistaProxyDataUrl(remoteUrl) {
  const q = new URLSearchParams({ url: remoteUrl });
  try {
    const res = await fetch(`/api/numista-image?${q.toString()}`);
    const data = await res.json().catch(() => ({}));
    const fromJson = typeof data?.imageDataUrl === "string" ? data.imageDataUrl.trim() : "";
    if (fromJson.startsWith("data:image/")) return fromJson;
  } catch {
    /* fall through */
  }
  return "";
}

/**
 * Convert a remote image URL to a data URL for export. Wikimedia is
 * CORS-friendly so we fetch directly. Numista falls through Vercel
 * `/_next/image` then our same-origin proxy.
 * @param {string} remoteUrl
 * @returns {Promise<string>}
 */
export async function remoteImageToDataUrl(remoteUrl) {
  const u = String(remoteUrl || "").trim();
  if (!u) return "";
  if (isDataImageUrl(u)) return u;
  if (isSameOriginImageUrl(u)) return u;

  if (WIKIMEDIA_HOST.test(u)) {
    const direct = await directDataUrl(u);
    if (direct.startsWith("data:image/")) return direct;
  }

  if (NUMISTA_HOST.test(u)) {
    const viaNext = await nextImageDataUrl(u);
    if (viaNext.startsWith("data:image/")) return viaNext;

    const proxied = await numistaProxyDataUrl(u);
    if (proxied.startsWith("data:image/")) return proxied;
  }

  return "";
}

const SLOT_IMAGE_KEYS = ["imageUrl", "labelyShelfImageUrl"];

/**
 * @param {object} slot
 * @returns {Promise<object>}
 */
export async function inlineSlotImageFields(slot) {
  if (!slot || typeof slot !== "object") return slot;
  let next = { ...slot };

  await Promise.all(
    SLOT_IMAGE_KEYS.map(async (key) => {
      const url = String(next[key] || "").trim();
      if (!url || isDataImageUrl(url) || isSameOriginImageUrl(url)) return;
      const dataUrl = await remoteImageToDataUrl(url);
      if (dataUrl.startsWith("data:image/")) next[key] = dataUrl;
    }),
  );

  const hero = String(next.imageUrl || "").trim();
  const shelf = String(next.labelyShelfImageUrl || "").trim();
  if (hero.startsWith("data:") && !shelf.startsWith("data:")) {
    next.labelyShelfImageUrl = hero;
  } else if (shelf.startsWith("data:") && !hero.startsWith("data:")) {
    next.imageUrl = shelf;
  }

  return next;
}

/**
 * Rewrite every cross-origin <img> under root to a data URL before html-to-image capture.
 * @param {ParentNode | null} root
 * @param {{ strict?: boolean }} [opts]
 */
export async function inlineRemoteImagesInElement(root, { strict = false } = {}) {
  if (!root || typeof document === "undefined") return;

  const imgs = [...root.querySelectorAll("img")];
  const failures = [];

  await Promise.all(
    imgs.map(async (img) => {
      const src = String(img.currentSrc || img.getAttribute("src") || img.src || "").trim();
      if (!src || isDataImageUrl(src) || isSameOriginImageUrl(src)) return;

      const dataUrl = await remoteImageToDataUrl(src);
      if (!dataUrl.startsWith("data:image/")) {
        failures.push(src.slice(0, 120));
        return;
      }

      img.removeAttribute("srcset");
      img.src = dataUrl;
      if (img.decode) await img.decode().catch(() => {});
    }),
  );

  if (strict && failures.length > 0) {
    throw new Error(
      `Could not prepare ${failures.length} image(s) for export (Numista proxy failed). Regenerate or check NUMISTA_API_KEY.`,
    );
  }
}
