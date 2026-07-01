/** Browser session persistence for the main video generator (app picker, workspace, gallery). */

import { normalizeValcoinOutputFormat } from "@/lib/slideLayout";

export const HOME_SESSION_KEY = "ts_home_session_v1";

const APP_IDS = new Set(["thrifty", "valcoin", "labely", "videoUniqueizer"]);

/** Data URLs in slots / batch buffers exceed localStorage (~5MB); strip before retry saves. */
function stripDataUrlFieldsFromSlot(slot) {
  if (!slot || typeof slot !== "object") return slot;
  const next = { ...slot };
  for (const k of ["imageUrl", "labelyShelfImageUrl"]) {
    if (typeof next[k] === "string" && next[k].startsWith("data:")) next[k] = "";
  }
  return next;
}

function stripSlotsHeavyImages(slots) {
  if (!Array.isArray(slots)) return [];
  return slots.map((s) => stripDataUrlFieldsFromSlot(s));
}

function stripConfigHeavyImages(config) {
  if (!config || typeof config !== "object") return config;
  return { ...config, slots: stripSlotsHeavyImages(config.slots) };
}

function stripPreviewScreenshotsOnly(shows) {
  if (!Array.isArray(shows)) return [];
  return shows.map((sh) => {
    if (!sh || typeof sh !== "object") return sh;
    const { previewScreenshot, ...rest } = sh;
    return { ...rest };
  });
}

function stripSavedShowsHeavyImages(shows) {
  if (!Array.isArray(shows)) return [];
  return shows.map((sh) => {
    if (!sh || typeof sh !== "object") return sh;
    const { previewScreenshot, ...rest } = sh;
    return {
      ...rest,
      slots: stripSlotsHeavyImages(rest.slots),
    };
  });
}

function nullOutBatchDataUrls(batch) {
  if (!Array.isArray(batch)) return [];
  return batch.map((x) => (typeof x === "string" && x.startsWith("data:") ? null : x));
}

/**
 * @param {object} defaults - full default workspace (e.g. defaultConfig)
 * @param {(i: number) => object} emptySlotFn
 * @param {object} saved - partial persisted config
 */
export function mergePersistedConfig(defaults, emptySlotFn, saved) {
  if (!saved || typeof saved !== "object") return { ...defaults };
  const merged = { ...defaults, ...saved };
  if (Array.isArray(saved.slots)) {
    merged.slots = saved.slots.map((s, i) => ({ ...emptySlotFn(i), ...s }));
  }
  if (APP_IDS.has(saved.appId)) merged.appId = saved.appId;
  if (merged.appId === "valcoin") {
    merged.outputFormat = normalizeValcoinOutputFormat(merged.outputFormat);
  }
  if (merged.appId === "labely") {
    merged.outputFormat = "labelyScan";
    merged.labelyAiProducts = true;
    merged.labelyUseBraveImages = saved.labelyUseBraveImages !== false;
    merged.labelyFoodItemsRaw =
      typeof saved.labelyFoodItemsRaw === "string" ? saved.labelyFoodItemsRaw : "";
  }
  merged.captionText = "";
  delete merged.labelyFreiburgCategory;
  if (!Array.isArray(merged.poseReferenceImages)) merged.poseReferenceImages = [];
  return merged;
}

export function readHomeSession() {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(HOME_SESSION_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data || typeof data !== "object") return null;
    return data;
  } catch {
    return null;
  }
}

/**
 * @param {object} payload
 * @param {object} payload.config
 * @param {object[]} payload.savedSlideshows
 * @param {number | null} payload.activeShowIdx
 * @param {number} payload.currentSlide
 */
export function writeHomeSession(payload) {
  if (typeof window === "undefined") return;
  const body = { v: 1, ...payload };
  const trySet = (obj) => {
    localStorage.setItem(HOME_SESSION_KEY, JSON.stringify(obj));
  };
  const isQuota = (e) => e?.name === "QuotaExceededError" || e?.code === 22;

  try {
    trySet(body);
    return;
  } catch (e) {
    if (!isQuota(e)) {
      console.warn("[homeSession] save failed", e);
      return;
    }
  }

  try {
    trySet({
      ...body,
      savedSlideshows: stripPreviewScreenshotsOnly(body.savedSlideshows || []),
    });
    return;
  } catch (e) {
    if (!isQuota(e)) {
      console.warn("[homeSession] slim save failed", e);
      return;
    }
  }

  try {
    trySet({
      ...body,
      config: stripConfigHeavyImages(body.config),
      savedSlideshows: stripSavedShowsHeavyImages(body.savedSlideshows || []),
      batchImageDataUrls: nullOutBatchDataUrls(body.batchImageDataUrls || []),
    });
    return;
  } catch (e) {
    if (!isQuota(e)) {
      console.warn("[homeSession] stripped slot images save failed", e);
      return;
    }
  }

  try {
    trySet({
      v: 1,
      appId: body.config?.appId ?? "thrifty",
      currentSlide: body.currentSlide ?? 0,
      activeShowIdx: body.activeShowIdx ?? null,
      numSlideshows: body.numSlideshows,
      batchImageDataUrls: nullOutBatchDataUrls(body.batchImageDataUrls || []),
      config: stripConfigHeavyImages(body.config),
      savedSlideshows: [],
      savedAt: body.savedAt,
    });
    return;
  } catch (e) {
    if (!isQuota(e)) {
      console.warn("[homeSession] gallery-cleared save failed", e);
      return;
    }
  }

  try {
    trySet({
      v: 1,
      appId: body.config?.appId ?? "thrifty",
      currentSlide: body.currentSlide ?? 0,
      activeShowIdx: null,
      numSlideshows: body.numSlideshows,
      batchImageDataUrls: [],
      config: stripConfigHeavyImages(body.config),
      savedSlideshows: [],
      savedAt: body.savedAt,
    });
  } catch (e) {
    console.warn("[homeSession] could not persist gallery (quota).", e);
  }
}
