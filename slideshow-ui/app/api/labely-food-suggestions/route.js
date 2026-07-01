import { NextResponse } from "next/server";
import { extractOpenFoodFactsImage } from "@/lib/openFoodFactsProductImage";
import { braveImagesConfigured } from "@/lib/braveFoodImage";
import { lookupFoodBrave } from "@/lib/labelyBraveFoodLookup";
import { getBraveUsageSnapshot } from "@/lib/braveUsage";

export const maxDuration = 300;

const OPEN_FOOD_FACTS_SEARCH = "https://world.openfoodfacts.org/cgi/search.pl";
const SEARCH_PAGE_SIZE = 40;

function normalizeFoodText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function productLabel(product) {
  const name = String(product?.product_name || product?.generic_name || "").trim();
  const brand = String(product?.brands || "").split(",")[0]?.trim() || "";
  return [brand, name].filter(Boolean).join(" ").trim();
}

function scoreProduct(product, terms) {
  const haystack = normalizeFoodText([
    product?.product_name,
    product?.generic_name,
    product?.brands,
  ].filter(Boolean).join(" "));
  const tokens = normalizeFoodText(terms).split(/\s+/).filter((t) => t.length >= 3);
  if (!haystack || tokens.length === 0) return 0;
  let score = 0;
  for (const token of tokens) {
    if (haystack.includes(token)) score += 1;
  }
  if (extractOpenFoodFactsImage(product)) score += 3;
  return score;
}

function isStrongMatch(product, query) {
  const label = normalizeFoodText(productLabel(product));
  const q = normalizeFoodText(query);
  return Boolean(q && label && (label === q || label.includes(q)));
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function fetchSearchPage(params) {
  const url = `${OPEN_FOOD_FACTS_SEARCH}?${params.toString()}`;
  for (let attempt = 0; attempt < 2; attempt++) {
    const res = await fetch(url, {
      headers: {
        Accept: "application/json",
        "User-Agent": "AutoSlideshow Labely/1.0 (food-photo recommendations)",
      },
    });
    if (res.ok) return res.json().catch(() => null);
    if (![429, 500, 502, 503, 504].includes(res.status)) return null;
    await sleep(350 * (attempt + 1));
  }
  return null;
}

async function fetchProducts(query) {
  const params = new URLSearchParams({
    search_terms: query,
    search_simple: "1",
    action: "process",
    json: "1",
    page: "1",
    page_size: String(SEARCH_PAGE_SIZE),
    fields: "product_name,generic_name,brands,image_front_url,image_url,selected_images",
  });

  const data = await fetchSearchPage(params);
  return Array.isArray(data?.products) ? data.products : [];
}

function queryVariants(query) {
  const q = String(query || "").trim();
  const variants = [q];
  const corrected = q.replace(/\bcelcius\b/gi, "celsius");
  if (corrected !== q) variants.push(corrected);
  const firstWord = normalizeFoodText(corrected).split(/\s+/).find((t) => t.length >= 3);
  if (firstWord && !variants.some((x) => normalizeFoodText(x) === firstWord)) variants.push(firstWord);
  return variants.filter(Boolean);
}

/** First winning image URL per product label (rank order preserved via ranked iteration). */
function candidateDetailsFromRanked(ranked, candidateLabels) {
  const imageByLabel = new Map();
  for (const x of ranked) {
    const img = extractOpenFoodFactsImage(x.product);
    if (!img || imageByLabel.has(x.label)) continue;
    imageByLabel.set(x.label, img);
  }
  return candidateLabels.map((label) => ({
    label,
    imageUrl: imageByLabel.get(label) || "",
  }));
}

async function lookupFood(query) {
  const q = String(query || "").trim();
  if (!q) return { query: q, status: "empty" };
  const fetched = await Promise.all(queryVariants(q).map((variant) => fetchProducts(variant)));
  const products = fetched.flat();
  const ranked = products
    .filter((p) => extractOpenFoodFactsImage(p))
    .map((p) => ({ product: p, score: scoreProduct(p, q), label: productLabel(p) }))
    .filter((x) => x.label)
    .sort((a, b) => b.score - a.score);
  const candidates = [...new Set(ranked.map((x) => x.label))].slice(0, 12);
  const strong = products.find((p) => extractOpenFoodFactsImage(p) && isStrongMatch(p, q));
  if (strong) {
    const match = productLabel(strong);
    const ordered = [match, ...candidates.filter((x) => x !== match)].slice(0, 12);
    const strongImg = extractOpenFoodFactsImage(strong);
    let candidateDetails = candidateDetailsFromRanked(ranked, ordered);
    if (strongImg) {
      candidateDetails = candidateDetails.map((d) =>
        d.label === match ? { ...d, imageUrl: strongImg } : d
      );
    }
    return {
      query: q,
      status: "found",
      match,
      candidates: ordered,
      candidateDetails,
    };
  }

  const best = ranked[0];
  if (!best) return { query: q, status: "missing" };

  const found = best.score >= 4 || normalizeFoodText(best.label).includes(normalizeFoodText(q));
  const row = found
    ? { query: q, status: "found", match: best.label, candidates }
    : { query: q, status: "recommend", suggestion: best.label, candidates };
  return {
    ...row,
    candidateDetails: candidateDetailsFromRanked(ranked, candidates),
  };
}

export async function POST(req) {
  try {
    const body = await req.json().catch(() => ({}));
    const items = Array.isArray(body.items) ? body.items : [];
    const useBraveImages =
      body.useBraveImages === true
      || body.useBingImages === true
      || body.useGoogleImages === true;
    const unique = [...new Set(items.map((x) => String(x || "").trim()).filter(Boolean))].slice(0, 20);
    const results = await Promise.all(
      unique.map((item) => (useBraveImages ? lookupFoodBrave(item) : lookupFood(item))),
    );
    const braveUsage = useBraveImages && braveImagesConfigured()
      ? await getBraveUsageSnapshot()
      : null;
    return NextResponse.json({ results, braveUsage });
  } catch (err) {
    console.error("[labely-food-suggestions]", err);
    return NextResponse.json(
      { error: err?.message || "Unknown server error", results: [] },
      { status: 500 }
    );
  }
}
