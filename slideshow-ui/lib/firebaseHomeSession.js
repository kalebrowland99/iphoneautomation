/**
 * Persists the same logical session as localStorage (config, gallery, batch rows)
 * using Firestore + Storage so large data URLs are not capped by the 1MB doc limit.
 *
 * Upload/download use retries + post-upload verification (SaaS-style resilience).
 */

import { signInAnonymously } from "firebase/auth";
import {
  collection,
  deleteDoc,
  doc,
  getDoc,
  getDocs,
  setDoc,
  writeBatch,
} from "firebase/firestore";
import { getDownloadURL, getMetadata, ref, uploadBytes } from "firebase/storage";
import { getFirebaseAuth, getFirebaseDb, getFirebaseStorage, isFirebaseConfigured } from "./firebaseClient";

export const FBS_PREFIX = "__FBS__";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Any real raster/SVG data URL we should move to Storage (keeps Firestore small + consistent). */
function isPersistableImageDataUrl(v) {
  return typeof v === "string"
    && v.startsWith("data:image/")
    && v.length > 120;
}

/**
 * @param {import('firebase/storage').StorageReference} storageRef
 * @param {Blob} blob
 * @param {string} contentType
 */
async function uploadBytesWithRetry(storageRef, blob, contentType) {
  let lastErr;
  const maxAttempts = 4;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      await uploadBytes(storageRef, blob, { contentType });
      await getMetadata(storageRef);
      return;
    } catch (e) {
      lastErr = e;
      if (attempt < maxAttempts) await sleep(350 * attempt);
    }
  }
  throw lastErr;
}

/**
 * @param {import('firebase/storage').FirebaseStorage} storage
 * @param {string} path
 */
async function getDownloadUrlWithRetry(storage, path) {
  let lastErr;
  const maxAttempts = 5;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await getDownloadURL(ref(storage, path));
    } catch (e) {
      lastErr = e;
      if (attempt < maxAttempts) await sleep(280 * attempt);
    }
  }
  console.warn("[firebaseHomeSession] getDownloadURL failed after retries:", path, lastErr);
  return "";
}

/**
 * @param {unknown} input
 * @param {string} uid
 * @param {Map<string, string>} cache dataUrl -> storage fullPath
 * @param {import('firebase/storage').FirebaseStorage} storage
 */
async function replaceDataUrlsWithRefs(input, uid, cache, storage) {
  if (input === null || input === undefined) return input;
  if (isPersistableImageDataUrl(input)) {
    const s = /** @type {string} */ (input);
    if (cache.has(s)) return `${FBS_PREFIX}${cache.get(s)}`;
    let blob;
    try {
      blob = await fetch(s).then((r) => r.blob());
    } catch (e) {
      console.warn("[firebaseHomeSession] data URL fetch failed, keeping inline (may skip if too large)", e);
      return input;
    }
    const id = typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}_${Math.random().toString(16).slice(2)}`;
    const path = `users/${uid}/sessionAssets/${id}`;
    const r = ref(storage, path);
    await uploadBytesWithRetry(r, blob, blob.type || "application/octet-stream");
    cache.set(s, path);
    return `${FBS_PREFIX}${path}`;
  }
  if (typeof input === "string" && input.startsWith(FBS_PREFIX)) return input;
  if (Array.isArray(input)) {
    const out = [];
    for (let i = 0; i < input.length; i++) {
      out.push(await replaceDataUrlsWithRefs(input[i], uid, cache, storage));
    }
    return out;
  }
  if (typeof input === "object") {
    const out = {};
    for (const [k, v] of Object.entries(input)) {
      out[k] = await replaceDataUrlsWithRefs(v, uid, cache, storage);
    }
    return out;
  }
  return input;
}

/** @param {unknown} value @param {Set<string>} acc */
function collectFbsPaths(value, acc) {
  if (typeof value === "string" && value.startsWith(FBS_PREFIX)) {
    acc.add(value.slice(FBS_PREFIX.length));
    return;
  }
  if (Array.isArray(value)) {
    for (const v of value) collectFbsPaths(v, acc);
    return;
  }
  if (value && typeof value === "object") {
    for (const v of Object.values(value)) collectFbsPaths(v, acc);
  }
}

/**
 * @param {unknown} value
 * @param {Map<string, string>} urlByPath
 */
function resolveFbsInPlace(value, urlByPath) {
  if (typeof value === "string" && value.startsWith(FBS_PREFIX)) {
    const p = value.slice(FBS_PREFIX.length);
    const url = urlByPath.get(p);
    return url && url.length > 0 ? url : null;
  }
  if (Array.isArray(value)) return value.map((v) => resolveFbsInPlace(v, urlByPath));
  if (value && typeof value === "object") {
    const out = {};
    for (const [k, v] of Object.entries(value)) {
      out[k] = resolveFbsInPlace(v, urlByPath);
    }
    return out;
  }
  return value;
}

/**
 * @param {Set<string>} paths
 * @param {import('firebase/storage').FirebaseStorage} storage
 */
async function pathsToDownloadUrls(paths, storage) {
  const map = new Map();
  await Promise.all(
    [...paths].map(async (p) => {
      const url = await getDownloadUrlWithRetry(storage, p);
      map.set(p, url);
    })
  );
  return map;
}

function workspaceDocRef(db, uid) {
  return doc(db, "users", uid, "workspace", "v1");
}

function galleryColRef(db, uid) {
  return collection(db, "users", uid, "workspace", "v1", "gallery");
}

const MAX_BATCH_OPS = 400;

/**
 * @returns {Promise<string | null>} Firebase uid or null
 */
export async function signInFirebaseAnonymously() {
  if (!isFirebaseConfigured()) return null;
  const auth = getFirebaseAuth();
  if (!auth) return null;
  if (auth.currentUser?.uid) return auth.currentUser.uid;
  const cred = await signInAnonymously(auth);
  return cred.user?.uid ?? null;
}

/**
 * @param {string} uid
 * @param {{
 *   config: object,
 *   savedSlideshows: object[],
 *   activeShowIdx: number | null,
 *   currentSlide: number,
 *   numSlideshows?: number,
 *   batchImageDataUrls?: (string | null)[],
 *   savedAt: number,
 * }} payload
 */
export async function saveHomeSessionRemote(uid, payload) {
  const db = getFirebaseDb();
  const storage = getFirebaseStorage();
  if (!db || !storage || !uid) return;

  const cache = new Map();
  const metaSerialized = await replaceDataUrlsWithRefs(
    {
      savedAt: payload.savedAt,
      currentSlide: payload.currentSlide,
      activeShowIdx: payload.activeShowIdx ?? null,
      numSlideshows: typeof payload.numSlideshows === "number" ? payload.numSlideshows : 3,
      batchImageDataUrls: Array.isArray(payload.batchImageDataUrls) ? payload.batchImageDataUrls : [],
      config: payload.config,
      galleryCount: Array.isArray(payload.savedSlideshows) ? payload.savedSlideshows.length : 0,
    },
    uid,
    cache,
    storage
  );

  const shows = Array.isArray(payload.savedSlideshows) ? payload.savedSlideshows : [];
  const serializedShows = [];
  for (let i = 0; i < shows.length; i++) {
    serializedShows.push(await replaceDataUrlsWithRefs(shows[i], uid, cache, storage));
  }

  const gcol = galleryColRef(db, uid);
  const existing = await getDocs(gcol);
  for (const d of existing.docs) {
    const n = Number.parseInt(d.id, 10);
    if (!Number.isFinite(n) || n >= serializedShows.length) {
      await deleteDoc(d.ref);
    }
  }

  for (let start = 0; start < serializedShows.length; start += MAX_BATCH_OPS) {
    const batch = writeBatch(db);
    const end = Math.min(start + MAX_BATCH_OPS, serializedShows.length);
    for (let i = start; i < end; i++) {
      batch.set(doc(gcol, String(i)), { show: serializedShows[i] });
    }
    await batch.commit();
  }

  await setDoc(workspaceDocRef(db, uid), { ...metaSerialized, v: 1 }, { merge: false });
}

/**
 * @param {string} uid
 * @returns {Promise<null | {
 *   config: object,
 *   savedSlideshows: object[],
 *   activeShowIdx: number | null,
 *   currentSlide: number,
 *   numSlideshows: number,
 *   batchImageDataUrls: (string | null)[],
 *   savedAt: number,
 * }>}
 */
export async function loadHomeSessionRemote(uid) {
  const db = getFirebaseDb();
  const storage = getFirebaseStorage();
  if (!db || !storage || !uid) return null;

  const metaSnap = await getDoc(workspaceDocRef(db, uid));
  if (!metaSnap.exists) return null;
  const meta = metaSnap.data() ?? {};
  const galleryCount = typeof meta.galleryCount === "number" ? meta.galleryCount : 0;

  const savedSlideshows = [];
  const gcol = galleryColRef(db, uid);
  for (let i = 0; i < galleryCount; i++) {
    const s = await getDoc(doc(gcol, String(i)));
    const data = s.data();
    if (data?.show) savedSlideshows.push(data.show);
    else savedSlideshows.push({});
  }

  const merged = {
    savedAt: typeof meta.savedAt === "number" ? meta.savedAt : 0,
    currentSlide: typeof meta.currentSlide === "number" ? meta.currentSlide : 0,
    activeShowIdx: typeof meta.activeShowIdx === "number" ? meta.activeShowIdx : null,
    numSlideshows: typeof meta.numSlideshows === "number" ? meta.numSlideshows : 3,
    batchImageDataUrls: Array.isArray(meta.batchImageDataUrls) ? meta.batchImageDataUrls : [],
    config: meta.config && typeof meta.config === "object" ? meta.config : {},
    savedSlideshows,
  };

  const pathSet = new Set();
  collectFbsPaths(merged.config, pathSet);
  collectFbsPaths(merged.batchImageDataUrls, pathSet);
  for (const sh of merged.savedSlideshows) collectFbsPaths(sh, pathSet);

  const urlByPath = await pathsToDownloadUrls(pathSet, storage);
  return {
    savedAt: merged.savedAt,
    currentSlide: merged.currentSlide,
    activeShowIdx: merged.activeShowIdx,
    numSlideshows: merged.numSlideshows,
    batchImageDataUrls: /** @type {(string | null)[]} */ (resolveFbsInPlace(merged.batchImageDataUrls, urlByPath)),
    config: resolveFbsInPlace(merged.config, urlByPath),
    savedSlideshows: merged.savedSlideshows.map((sh) => resolveFbsInPlace(sh, urlByPath)),
  };
}
