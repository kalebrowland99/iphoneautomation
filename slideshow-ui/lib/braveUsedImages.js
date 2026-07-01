/**
 * Brave image URLs that have been exported in a slideshow — excluded from future picks.
 */

import { createHash } from "crypto";
import { mkdir, readFile, writeFile } from "fs/promises";
import { join } from "path";

const USAGE_DIR = process.env.VERCEL ? join("/tmp", "autoslideshow") : join(process.cwd(), "data");
const USED_FILE = join(USAGE_DIR, "brave-used-images.json");

const TRACKING_PARAMS = [
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_term",
  "utm_content",
  "fbclid",
  "gclid",
];

/** @param {string} url */
export function normalizeBraveImageUrl(url) {
  const s = String(url || "").trim();
  if (!s || !/^https?:\/\//i.test(s)) return "";
  try {
    const u = new URL(s);
    u.protocol = "https:";
    u.hostname = u.hostname.replace(/^www\./i, "").toLowerCase();
    for (const p of TRACKING_PARAMS) u.searchParams.delete(p);
    u.hash = "";
    return u.toString();
  } catch {
    return s;
  }
}

/** @param {Buffer | Uint8Array} buffer */
export function braveImageContentHash(buffer) {
  if (!buffer?.length) return "";
  return createHash("sha256").update(buffer).digest("hex").slice(0, 24);
}

/** @returns {Promise<Set<string>>} */
async function readUsedSet() {
  try {
    const raw = await readFile(USED_FILE, "utf8");
    const data = JSON.parse(raw);
    const urls = Array.isArray(data?.urls) ? data.urls : [];
    return new Set(urls.map(normalizeBraveImageUrl).filter(Boolean));
  } catch {
    return new Set();
  }
}

/** @returns {Promise<Set<string>>} */
export async function getUsedBraveImageUrls() {
  return readUsedSet();
}

/** @param {string} url */
export async function isBraveImageUsed(url) {
  const norm = normalizeBraveImageUrl(url);
  if (!norm) return false;
  const used = await readUsedSet();
  return used.has(norm);
}

/** @param {string[]} urls */
export async function markBraveImagesUsed(urls) {
  const incoming = (Array.isArray(urls) ? urls : [])
    .map(normalizeBraveImageUrl)
    .filter(Boolean);
  if (!incoming.length) return { added: 0, total: 0 };

  const used = await readUsedSet();
  let added = 0;
  for (const u of incoming) {
    if (!used.has(u)) {
      used.add(u);
      added++;
    }
  }
  await mkdir(USAGE_DIR, { recursive: true });
  await writeFile(USED_FILE, JSON.stringify({ urls: [...used] }), "utf8");
  return { added, total: used.size };
}
