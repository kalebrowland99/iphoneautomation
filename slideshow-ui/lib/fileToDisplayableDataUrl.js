/**
 * Browser-side uploads: normalize to data URLs. HEIC/HEIF → JPEG when needed
 * so img elements, canvas export, and vision APIs work cross-browser.
 */

const RASTER_EXT = /\.(jpe?g|png|gif|webp|bmp|tif|tiff|heic|heif)$/i;

export const IMAGE_FILE_ACCEPT = "image/*,.heic,.heif,.jpg,.jpeg,.png,.webp,.gif,.bmp,.tiff,.tif";

export function isLikelyRasterImageFile(file) {
  if (!file || typeof file !== "object") return false;
  const type = String(file.type || "").toLowerCase();
  if (type.startsWith("image/")) return true;
  const name = String(file.name || "");
  return RASTER_EXT.test(name);
}

function isHeicLike(file) {
  const type = String(file.type || "").toLowerCase();
  if (type === "image/heic" || type === "image/heif") return true;
  return /\.(heic|heif)$/i.test(String(file.name || ""));
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(new Error("Could not read file"));
    r.readAsDataURL(file);
  });
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(new Error("Could not read converted image"));
    r.readAsDataURL(blob);
  });
}

async function loadHeic2any() {
  const mod = await import("heic2any");
  const fn = mod.default;
  return typeof fn === "function" ? fn : /** @type {any} */ (mod);
}

/** Safari / some WebKit builds decode HEIC natively — avoids WASM failures in Chrome-from-iPhone flows when user is on Safari. */
async function heicLikeToJpegDataUrlViaBitmap(file) {
  if (typeof createImageBitmap !== "function") {
    throw new Error("createImageBitmap unavailable");
  }
  const bmp = await createImageBitmap(file);
  try {
    const c = document.createElement("canvas");
    c.width = bmp.width;
    c.height = bmp.height;
    const ctx = c.getContext("2d");
    if (!ctx) throw new Error("No 2d context");
    ctx.drawImage(bmp, 0, 0);
    const url = c.toDataURL("image/jpeg", 0.92);
    if (!url?.startsWith("data:image/jpeg")) throw new Error("Canvas export failed");
    return url;
  } finally {
    bmp.close();
  }
}

/** Sharp on the Next.js server — reliable HEIC in Chrome (localhost / typical Node deploys). */
async function convertImageViaServer(file) {
  const fd = new FormData();
  fd.append("file", file, file.name || "photo.heic");
  const res = await fetch("/api/convert-heic", { method: "POST", body: fd });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = typeof json.error === "string" ? json.error : `Server convert failed (${res.status})`;
    throw new Error(msg);
  }
  if (typeof json.dataUrl !== "string" || !json.dataUrl.startsWith("data:image/")) {
    throw new Error("Invalid server response.");
  }
  return json.dataUrl;
}

async function heicLikeToJpegWithHeic2any(file) {
  const heic2any = await loadHeic2any();
  let converted;
  try {
    converted = await heic2any({
      blob: file,
      toType: "image/jpeg",
      quality: 0.88,
    });
  } catch (firstErr) {
    try {
      converted = await heic2any({
        blob: file,
        toType: "image/png",
      });
    } catch {
      throw firstErr;
    }
  }
  const blob = Array.isArray(converted) ? converted[0] : converted;
  if (!(blob instanceof Blob)) {
    throw new Error("HEIC conversion returned no image.");
  }
  return blobToDataUrl(blob);
}

async function fileHeicLikeToDisplayableDataUrl(file) {
  try {
    return await heicLikeToJpegDataUrlViaBitmap(file);
  } catch {
    /* fall through — e.g. Chrome cannot decode HEIC in createImageBitmap */
  }
  try {
    return await convertImageViaServer(file);
  } catch (e) {
    console.warn("[image upload] server HEIC decode:", e);
  }
  return heicLikeToJpegWithHeic2any(file);
}

/** @returns {Promise<string>} data URL (JPEG after HEIC decode when needed). */
export async function fileToDisplayableDataUrl(file) {
  if (!isLikelyRasterImageFile(file)) {
    throw new Error("Not a supported image file.");
  }
  if (!isHeicLike(file)) {
    return readFileAsDataUrl(file);
  }
  return fileHeicLikeToDisplayableDataUrl(file);
}

/**
 * Same as {@link fileToDisplayableDataUrl} but returns `{ ok, dataUrl?, error? }` — never throws.
 * Useful for bulk uploads so one bad file does not fail the whole batch.
 */
export async function tryFileToDisplayableDataUrl(file) {
  try {
    const dataUrl = await fileToDisplayableDataUrl(file);
    return { ok: true, dataUrl };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}
