import { readdir, stat } from "fs/promises";
import { join } from "path";

/** Recursive image paths relative to `dir` (same logic as /api/references). */
export async function walkReferenceImagesDir(dir, base = "") {
  let results = [];
  let entries;
  try {
    entries = await readdir(dir);
  } catch {
    return results;
  }
  for (const entry of entries) {
    const fullPath = join(dir, entry);
    const relative = base ? `${base}/${entry}` : entry;
    const s = await stat(fullPath).catch(() => null);
    if (!s) continue;
    if (s.isDirectory()) {
      results = results.concat(await walkReferenceImagesDir(fullPath, relative));
    } else if (/\.(jpe?g|png|webp|gif)$/i.test(entry)) {
      results.push(relative);
    }
  }
  return results;
}

export function publicReferenceDirForAppId(appId) {
  if (appId === "valcoin") return join(process.cwd(), "public", "valcoin", "references");
  if (appId === "labely-selfie") return join(process.cwd(), "public", "labely", "selfie-references");
  if (appId === "labely") return join(process.cwd(), "public", "labely", "references");
  return join(process.cwd(), "public", "references");
}

/** Relative paths like Thrifty’s sidebar uses (random pick → referenceFile for generate-image). */
export async function listPublicReferenceImageRelPaths(appId) {
  const dir = publicReferenceDirForAppId(appId);
  return walkReferenceImagesDir(dir);
}
