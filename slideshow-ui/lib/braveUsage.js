/**
 * Monthly Brave Image Search usage counter (server-side).
 * Brave Search plan: $5/mo free credits ≈ 1,000 searches at $5/1,000.
 */

import { mkdir, readFile, writeFile } from "fs/promises";
import { join } from "path";

const USAGE_DIR = process.env.VERCEL ? join("/tmp", "autoslideshow") : join(process.cwd(), "data");
const USAGE_FILE = join(USAGE_DIR, "brave-search-usage.json");

export function getBraveMonthlyLimit() {
  const raw = Number(process.env.BRAVE_SEARCH_MONTHLY_LIMIT);
  return Number.isFinite(raw) && raw > 0 ? Math.floor(raw) : 1000;
}

function currentMonthKey() {
  const d = new Date();
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

async function readUsageFile() {
  try {
    const raw = await readFile(USAGE_FILE, "utf8");
    const data = JSON.parse(raw);
    if (!data || typeof data !== "object") return { month: currentMonthKey(), count: 0 };
    const month = typeof data.month === "string" ? data.month : currentMonthKey();
    const count = Math.max(0, Number(data.count) || 0);
    return { month, count };
  } catch {
    return { month: currentMonthKey(), count: 0 };
  }
}

async function writeUsageFile(payload) {
  await mkdir(USAGE_DIR, { recursive: true });
  await writeFile(USAGE_FILE, JSON.stringify(payload), "utf8");
}

/** @returns {Promise<{ month: string, used: number, limit: number, remaining: number }>} */
export async function getBraveUsageSnapshot() {
  const limit = getBraveMonthlyLimit();
  const stored = await readUsageFile();
  const month = currentMonthKey();
  const used = stored.month === month ? stored.count : 0;
  return {
    month,
    used,
    limit,
    remaining: Math.max(0, limit - used),
  };
}

/** @param {number} [n] */
export async function recordBraveSearches(n = 1) {
  const increment = Math.max(0, Math.floor(Number(n) || 0));
  if (increment <= 0) return getBraveUsageSnapshot();

  const month = currentMonthKey();
  const stored = await readUsageFile();
  const used = (stored.month === month ? stored.count : 0) + increment;
  await writeUsageFile({ month, count: used });

  const limit = getBraveMonthlyLimit();
  return {
    month,
    used,
    limit,
    remaining: Math.max(0, limit - used),
  };
}
