/**
 * Random United-States-only coin photos from Wikimedia Commons.
 *
 * Why this exists: Numista's Cloudflare-protected CDN returns 502 to Vercel
 * function egress IPs and search results aren't always image-bearing.
 * Wikimedia Commons (upload.wikimedia.org) is free, no API key required, no
 * bot blocking, CORS-enabled (Access-Control-Allow-Origin: *), and has
 * tens of thousands of US coin photographs across well-curated categories.
 *
 * Strategy: every request includes the parent "Coins of the United States"
 * category (guaranteed to exist with hundreds of files) plus several random
 * denomination/series subcategories for variety. Each category is listed
 * via a single generator query (up to 500 files), filtered to real
 * photographs, de-duplicated by pageId, and one random candidate is returned.
 */

import { NextResponse } from "next/server";
import { fetchRemoteImageDataUrl } from "@/lib/fetchRemoteImageDataUrl";
import {
  PARENT_CATEGORY,
  COIN_SUBCATEGORIES,
} from "@/lib/usCoinWikimediaCategories";
import { WIKIMEDIA_COIN_FALLBACKS } from "@/lib/usCoinWikimediaFallbacks";

export const runtime = "nodejs";
export const maxDuration = 30;
/** Never serve a cached random pick — each call must roll fresh. */
export const dynamic = "force-dynamic";
export const revalidate = 0;

const WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php";
const USER_AGENT =
  "AutoSlideshow/1.0 (https://github.com/kalebrowland99/autoslideshow; +random coin photos)";
const WIKIMEDIA_FETCH_MS = 15_000;
const VERIFY_ATTEMPTS = 12;

function shuffleArray(items) {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function pickDistinctSubcategories(n) {
  const max = Math.min(n, COIN_SUBCATEGORIES.length);
  const picked = new Set();
  while (picked.size < max) {
    picked.add(COIN_SUBCATEGORIES[Math.floor(Math.random() * COIN_SUBCATEGORIES.length)]);
  }
  return [...picked];
}

/** Always include the parent category + N random subcategories. */
function pickCategoriesForRequest(subCount = 5) {
  return [PARENT_CATEGORY, ...pickDistinctSubcategories(subCount)];
}

/**
 * One MediaWiki query: list category members AND fetch image metadata in a
 * single round trip via a generator query.
 */
async function fetchCategoryFiles(category) {
  const params = new URLSearchParams({
    action: "query",
    generator: "categorymembers",
    gcmtitle: `Category:${category}`,
    gcmtype: "file",
    gcmlimit: "500",
    prop: "imageinfo",
    iiprop: "url|mime|size|extmetadata",
    iiurlwidth: "640",
    format: "json",
    formatversion: "2",
  });
  const url = `${WIKIMEDIA_API}?${params.toString()}`;
  try {
    const res = await fetch(url, {
      headers: { "User-Agent": USER_AGENT, Accept: "application/json" },
      signal: AbortSignal.timeout(WIKIMEDIA_FETCH_MS),
      cache: "no-store",
    });
    if (!res.ok) {
      return { ok: false, status: res.status, error: `HTTP ${res.status}` };
    }
    const data = await res.json().catch(() => null);
    return { ok: true, data };
  } catch (e) {
    const name = e?.name || "";
    return {
      ok: false,
      status: 502,
      error:
        name === "TimeoutError" || name === "AbortError"
          ? "Wikimedia request timed out"
          : String(e?.message || e || "Wikimedia request failed"),
    };
  }
}

const PHOTO_MIMES = new Set(["image/jpeg", "image/png", "image/webp"]);

/**
 * Files inside coin categories that aren't a single, clean coin photograph.
 *
 * Includes:
 *  - infographics, maps, paper money, banknotes, book pages
 *  - boxed presentation sets (e.g. "1992 Prestige Proof Set Box/Front/Back",
 *    "Silver Mint Set", "Uncirculated Set") — these show packaging, not a
 *    single coin face suitable for a tight collage cell.
 *  - lot/auction images and side-by-side group shots
 */
const REJECT_TITLE =
  /(map|chart|graph|logo|seal|coat[_ ]of[_ ]arms|flag|^stamp|banknote|paper money|diagram|schematic|cover|book|portrait of|prestige|proof set|mint set|uncirculated set|presentation set|souvenir set|presentation case|gift set|coin set|lot of|group of|collection of|catalog|catalogue|advertisement|philippines|hawaiian kingdom|kingdom of hawaii|kalakaua|liliuokalani|iceland|krona|leifur eiriksson|spanish puerto rico)/i;

function basenameToTitle(rawTitle) {
  return String(rawTitle || "")
    .replace(/^File:/i, "")
    .replace(/\.(jpe?g|png|webp|gif|tiff?)$/i, "")
    .replace(/[_]+/g, " ")
    .trim();
}

function extractCandidates(data) {
  const pages = data?.query?.pages;
  const list = Array.isArray(pages) ? pages : pages ? Object.values(pages) : [];
  const out = [];
  for (const p of list) {
    const info = Array.isArray(p?.imageinfo) ? p.imageinfo[0] : null;
    if (!info?.url) continue;
    const mime = String(info.mime || "").toLowerCase();
    if (!PHOTO_MIMES.has(mime)) continue;
    const title = basenameToTitle(p.title);
    if (!title || REJECT_TITLE.test(title)) continue;
    const url = info.thumburl || info.url;
    if (!url || !/^https:\/\/upload\.wikimedia\.org\//.test(url)) continue;
    out.push({
      url,
      sourceUrl: info.url,
      title,
      pageId: p.pageid ?? null,
      width: info.thumbwidth || info.width || null,
      height: info.thumbheight || info.height || null,
    });
  }
  return out;
}

async function pickVerifiedCoin(candidates) {
  const shuffled = shuffleArray(candidates).slice(0, VERIFY_ATTEMPTS);
  for (const picked of shuffled) {
    const imageDataUrl = await fetchRemoteImageDataUrl(picked.url, USER_AGENT);
    if (imageDataUrl?.startsWith("data:image/")) {
      return picked;
    }
  }
  return null;
}

async function loadCandidatePool() {
  const categories = pickCategoriesForRequest(7);
  const results = await Promise.all(categories.map((c) => fetchCategoryFiles(c)));

  const diagnostics = categories.map((category, i) => {
    const r = results[i];
    return {
      category,
      ok: r?.ok === true,
      status: r?.status ?? null,
      error: r?.error || null,
    };
  });

  const seenPageIds = new Set();
  const aggregated = [];
  for (const r of results) {
    if (!r?.ok) continue;
    for (const c of extractCandidates(r.data)) {
      if (c.pageId != null) {
        if (seenPageIds.has(c.pageId)) continue;
        seenPageIds.add(c.pageId);
      }
      aggregated.push(c);
    }
  }

  if (aggregated.length === 0) {
    const parent = await fetchCategoryFiles(PARENT_CATEGORY);
    if (parent.ok) {
      for (const c of extractCandidates(parent.data)) {
        if (c.pageId != null) {
          if (seenPageIds.has(c.pageId)) continue;
          seenPageIds.add(c.pageId);
        }
        aggregated.push(c);
      }
    }
  }

  if (aggregated.length === 0) {
    aggregated.push(...WIKIMEDIA_COIN_FALLBACKS);
  }

  return { aggregated, diagnostics };
}

const NO_CACHE_HEADERS = {
  "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
  Pragma: "no-cache",
};

export async function GET() {
  return NextResponse.json(
    {
      ok: true,
      route: "/api/wikimedia-coins",
      usage: 'POST JSON { action: "randomPhoto" }',
      parentCategory: PARENT_CATEGORY,
      subCategoryCount: COIN_SUBCATEGORIES.length,
    },
    { headers: NO_CACHE_HEADERS },
  );
}

export async function POST(req) {
  let body = {};
  try {
    body = await req.json();
  } catch {
    body = {};
  }
  const action = String(body.action || "").trim();

  if (action !== "randomPhoto") {
    return NextResponse.json(
      { error: 'Unknown action. Use { "action": "randomPhoto" }.' },
      { status: 400, headers: NO_CACHE_HEADERS },
    );
  }

  // 7 subcategories + parent = 8 categories per call. With ~526 leaves in
  // the pool (many of which only have 1-2 files), 7 picks per call balances
  // variety with the cost of parallel MediaWiki queries.
  const { aggregated, diagnostics } = await loadCandidatePool();

  if (aggregated.length === 0) {
    const firstError = diagnostics.find((d) => !d.ok && d.error)?.error || null;
    return NextResponse.json(
      {
        error: firstError
          ? `Wikimedia API error: ${firstError}`
          : "No US coin photos found in Wikimedia categories.",
        diagnostics,
      },
      { status: 502, headers: NO_CACHE_HEADERS },
    );
  }

  const exclude = new Set();
  const rawExclude = body.excludeSourceUrls;
  if (Array.isArray(rawExclude)) {
    for (const u of rawExclude) {
      const s = String(u || "").trim();
      if (s) exclude.add(s);
    }
  }

  let pool = aggregated;
  if (exclude.size > 0) {
    const filtered = aggregated.filter(
      (c) => !exclude.has(c.sourceUrl) && !exclude.has(c.url),
    );
    if (filtered.length > 0) pool = filtered;
  }

  const picked = await pickVerifiedCoin(pool);
  if (!picked) {
    return NextResponse.json(
      {
        error: "Could not download any coin photo from Wikimedia.",
        candidateCount: pool.length,
        diagnostics,
      },
      { status: 502, headers: NO_CACHE_HEADERS },
    );
  }

  return NextResponse.json(
    {
      imageUrl: picked.url,
      sourceUrl: picked.sourceUrl,
      title: picked.title,
      typeId: picked.pageId,
      candidateCount: pool.length,
      source: "wikimedia",
    },
    { headers: NO_CACHE_HEADERS },
  );
}
