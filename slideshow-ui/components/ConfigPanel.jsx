"use client";

import { useRef, useState, useEffect, useMemo, useCallback } from "react";
import { flushSync } from "react-dom";
import { getFontEmbedCSS, toCanvas, toJpeg } from "html-to-image";
import { DISPLAY_SCALE } from "./VideoPreview";
import {
  getSlideInfo,
  getTotalSlides,
  slideIndexToSlotIndex,
  isLabelySingleSlideFormat,
  isLabelyScanTourFormat,
  scanTourSlotCount,
  LABELY_SCAN_TOUR_SLOTS,
} from "@/lib/slideLayout";
import { buildLabelyScanFrameSequence, captureScanSourceCanvas, captureShelfIntroCanvas } from "@/lib/labelyScanExport";
import { ensureExportImageUrls, needsExportImageInlining } from "@/lib/ensureExportImageUrls";
import { inlineRemoteImagesInElement } from "@/lib/exportImagePrepare";
import { getBrand } from "@/lib/brand";
import { savedShowMatchesApp } from "@/lib/showAppId";
import {
  fileToDisplayableDataUrl,
  tryFileToDisplayableDataUrl,
  isLikelyRasterImageFile,
  IMAGE_FILE_ACCEPT,
} from "@/lib/fileToDisplayableDataUrl";
import { iphoneRetailPhotoImperfectionPrompt } from "@/lib/iphoneRetailPhotoImperfectionPrompt";
import { fetchRandomNumistaCoin } from "@/lib/numistaImageClient";
import { BAD_LABELY_VERDICT, normalizeBadLabelyScore } from "@/lib/labelyRating";
import { dispatchBraveUsageUpdated } from "@/components/BraveSearchUsageBar";
import BraveSearchUsageBar from "@/components/BraveSearchUsageBar";
import { estimateBraveSearchesForFarm } from "@/lib/braveSearchEstimate";
import { LABELY_FARM_VIDEOS_PER_PHONE } from "@/lib/farmLabelyFoods";
import {
  clearGlobalJob,
  clearJobHeartbeat,
  getGlobalJob,
  jobControls,
  patchGlobalJob,
  setGlobalJob,
  writeJobHeartbeat,
} from "@/lib/globalJobProgress";
import { waitForPreviewPaint } from "@/lib/waitForPreviewPaint";
import {
  fetchFarmJobStatus,
  getFarmJobAutoRunState,
  markFarmJobAutoRunCancelled,
  markFarmJobAutoRunStarted,
  markFarmJobDone,
  markFarmJobFailed,
  notifyAutomationDone,
  setFarmJobStatus,
  shouldAutoRunFarmJob,
  uploadMp4ToFarm,
} from "@/lib/farmBridge";
import { markExportedBraveImagesUsed } from "@/lib/markExportedBraveImages";
import { appendAutomationLog } from "@/lib/automationLog";
import { isFarmUploadActive } from "@/lib/farmUpload";

function parseDataUrl(dataUrl) {
  if (!dataUrl || typeof dataUrl !== "string") return null;
  const m = dataUrl.match(/^data:([^;,]+);base64,(.+)$/);
  if (!m) return null;
  return { mimeType: m[1].trim().split(";")[0], base64: m[2].trim() };
}

/** FisherΓÇôYates shuffle (returns a new array). */
function shuffleArray(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

const PRESET_COLORS = [
  "#e03030","#e05c20","#d4a017","#1a8a3a","#1a5cbf","#7c22cc","#000000","#ffffff",
];

// ΓöÇΓöÇ Grail brand tiers (higher tier = picked more often) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
const BRAND_TIERS = {
  1: ["Kapital","Visvim","Issey Miyake","Yohji Yamamoto","Comme des Gar├ºons","Junya Watanabe","Undercover","Number Nine","Hysteric Glamour","Neighborhood","WTAPS","LGB","If Six Was Nine","Kiko Kostadinov"],
  2: ["Chrome Hearts","Rick Owens","Balenciaga","Louis Vuitton","Dior","Saint Laurent","Givenchy","Prada","Maison Margiela","Bottega Veneta","Celine","Gucci","Vetements","Amiri","Palm Angels","1017 ALYX 9SM","Acne Studios","Helmut Lang","Raf Simons"],
  3: ["Carhartt","Levi's","Dickies","Wrangler","Red Kap","Ben Davis","RRL","Nudie Jeans","APC","Evisu"],
  4: ["Supreme","Stussy","BAPE","Off-White","Palace","Kith","Fear of God","Essentials","Anti Social Social Club","Billionaire Boys Club","Rhude","Arc'teryx","Patagonia","The North Face","Columbia"],
  5: ["Nike","Jordan","Adidas","Yeezy","New Balance","Salomon","Asics","Converse","Vivienne Westwood","Tiffany & Co","Harley Davidson","NASCAR"],
};
const TIER_WEIGHTS = { 1: 5, 2: 4, 3: 3, 4: 3, 5: 2 };

function buildWeightedPool(items) {
  const pool = [];
  for (const item of items) {
    let weight = 2;
    for (const [tier, brands] of Object.entries(BRAND_TIERS)) {
      if (brands.some((b) => item.toLowerCase().includes(b.toLowerCase()))) {
        weight = TIER_WEIGHTS[parseInt(tier)];
        break;
      }
    }
    for (let i = 0; i < weight; i++) pool.push(item);
  }
  return pool;
}

const DEFAULT_BRAND_LIST = [
  // Tier 1 ΓÇö Japanese Archive
  "Kapital","Visvim","Issey Miyake","Yohji Yamamoto","Comme des Gar├ºons",
  "Junya Watanabe","Undercover","Number Nine","Hysteric Glamour",
  "Neighborhood","WTAPS","Kiko Kostadinov",
  // Tier 2 ΓÇö High Fashion
  "Chrome Hearts","Rick Owens","Balenciaga","Louis Vuitton","Dior",
  "Saint Laurent","Prada","Maison Margiela","Bottega Veneta","Gucci",
  "Vetements","Amiri","Helmut Lang","Raf Simons","Acne Studios",
  // Tier 3 ΓÇö Vintage Workwear
  "vintage Carhartt","vintage Levi's","vintage Dickies","vintage Wrangler",
  "vintage Carhartt jacket","Levi's 501 made in USA",
  // Tier 4 ΓÇö Streetwear
  "Supreme","Stussy","BAPE","Off-White","Palace","Fear of God",
  "Billionaire Boys Club","Arc'teryx","Patagonia","The North Face",
  // Tier 5 ΓÇö Sneakers / Merch
  "vintage Nike","Air Jordan vintage","vintage Adidas","Yeezy",
  "vintage New Balance","vintage Salomon","vintage Converse",
  "vintage Metallica band tee","vintage Nirvana band tee",
  "vintage Harley Davidson tee","vintage NASCAR jacket",
  "Naruto anime tee","vintage Vivienne Westwood",
].join("\n");

// Minimal slot factory ΓÇö used for batch generation (avoids circular import with page.js)
const freshSlot = (i) => ({
  imageUrl: null, prompt: "",
  itemName: `Item ${i + 1}`, spentPrice: "", soldPrice: "",
  date: new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
  matchItems: [
    { title: "", source: "eBay",     price: "", inStock: true },
    { title: "", source: "Poshmark", price: "", inStock: true },
  ],
  revealCaptionBg: "", revealCaptionColor: "", revealCaptionPosition: "bottom",
  revealCaptionSize: 72, revealCaptionBold: true,
  thriftyCaptionText: "", thriftyCaptionBg: "", thriftyCaptionColor: "",
  thriftyCaptionPosition: "top", thriftyCaptionSize: 72, thriftyCaptionBold: true,
  labelyBrand: "",
  labelyScore: 0,
  labelyVerdict: "",
  labelyAnalysis: "",
  labelyAnalysisTitle: "Labely's Analysis",
  labelyLegalNote: "No lawsuits found.",
  labelyShelfImageUrl: null,
  labelyDbImageUrl: null,
});

/** Pack photo from /api/labely (Brave search or AI fallback). */
function labelyProductImagePatch(ly) {
  if (!ly?.imageDataUrl) return {};
  return {
    imageUrl: ly.imageDataUrl,
    ...(String(ly.labelyDbImageUrl || "").trim()
      ? { labelyDbImageUrl: String(ly.labelyDbImageUrl).trim() }
      : {}),
  };
}

/** Reset Labely AI fields when this slot's photo no longer matches cached analysis (shuffle/reorder/new batch row). */
function labelySlotAfterImageSwap(prevSlot, imageUrl, slotIndex) {
  return {
    ...prevSlot,
    imageUrl,
    itemName: `Item ${slotIndex + 1}`,
    labelyBrand: "",
    labelyScore: 0,
    labelyVerdict: "",
    labelyAnalysis: "",
    labelyAnalysisTitle: "Labely's Analysis",
    labelyLegalNote: "No lawsuits found.",
  };
}

/** Random hex id for scrambled export names and ZIP entry metadata. */
function randomExportHex(byteLength = 8) {
  const u = new Uint8Array(byteLength);
  if (typeof crypto !== "undefined" && crypto.getRandomValues) {
    crypto.getRandomValues(u);
  } else {
    for (let i = 0; i < byteLength; i++) u[i] = Math.floor(Math.random() * 256);
  }
  return [...u].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** 1-based order prefix + long random hex tail (sortable, tail looks unstructured). */
function sanitizeFileToken(v) {
  return String(v || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 36);
}

/** Farm gallery name: slot-food-video so captions/onscreen can parse the food segment. */
function farmGalleryMp4Filename(farmSlot, videoOnPhone, show = null) {
  const slot = String(farmSlot).padStart(2, "0");
  const foodToken =
    sanitizeFileToken(
      show?.batchFoodName
      || show?.foodGenre
      || show?.slots?.find((s) => String(s?.itemName || "").trim())?.itemName
    ) || "food";
  return `${slot}-${foodToken}-${videoOnPhone}.mp4`;
}

function sequentialRandomMp4Name(orderIndexZeroBased, show = null) {
  const batch = Number(show?.batchNumber);
  const inBatch = Number(show?.batchSlideshowIndex);
  const foodToken =
    sanitizeFileToken(show?.batchFoodName)
    || (String(show?.appId || "").trim() === "valcoin" ? "coins" : "food");
  const rand = randomExportHex(6);
  if (Number.isFinite(batch) && batch > 0) {
    if (Number.isFinite(inBatch) && inBatch > 1) return `${batch}-${inBatch}-${foodToken}-${rand}.mp4`;
    return `${batch}-${foodToken}-${rand}.mp4`;
  }
  return `${orderIndexZeroBased + 1}${randomExportHex(14)}.mp4`;
}

function triggerMp4Download(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function triggerZipDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** ISO BMFF / MP4 ΓÇö `ftyp` box at byte offset 4. */
function isMp4Bytes(bytes) {
  return (
    bytes.length >= 12
    && bytes[4] === 0x66
    && bytes[5] === 0x74
    && bytes[6] === 0x79
    && bytes[7] === 0x70
  );
}

function isPngBytes(bytes) {
  return (
    bytes.length >= 8
    && bytes[0] === 0x89
    && bytes[1] === 0x50
    && bytes[2] === 0x4e
    && bytes[3] === 0x47
  );
}

/** Merge a saved gallery show into the workspace snapshot for export (keeps duration, transitions, audio). */
function galleryShowToExportConfig(workspace, show) {
  const appId = show.appId != null ? show.appId : workspace.appId;
  const isLabely = appId === "labely";
  const isValcoin = appId === "valcoin";
  const outputFormat = isValcoin
    ? "labelyScan"
    : show.outputFormat != null
      ? show.outputFormat
      : isLabely
        ? "labelyScan"
        : workspace.outputFormat;
  const rawSlots =
    Array.isArray(show.slots) && show.slots.length > 0 ? show.slots : workspace.slots;
  return {
    ...workspace,
    slots: rawSlots.map((s) => ({ ...s })),
    appId,
    outputFormat,
    captionText: "",
    jitterSeed: show.jitterSeed ?? workspace.jitterSeed,
    labelyOutroText: show.labelyOutroText ?? workspace.labelyOutroText,
    labelyScanSlotCount: isLabely
      ? show.labelyScanSlotCount ?? LABELY_SCAN_TOUR_SLOTS
      : show.labelyScanSlotCount ?? workspace.labelyScanSlotCount,
  };
}

function badLabelyPatch(score) {
  return { labelyScore: normalizeBadLabelyScore(score), labelyVerdict: BAD_LABELY_VERDICT };
}

function labelyShelfScenePrompt(itemName, brandName = "") {
  const item = [brandName, itemName].filter(Boolean).join(" ").trim() || "packaged grocery product";
  const t = item.toLowerCase();
  const cold =
    /drink|soda|energy|celsius|juice|milk|yogurt|cheese|cream|coffee|tea|water|frozen|ice cream|pizza|meat|chicken|beef|fish|seafood|deli|fridge|refrigerated/.test(t);
  const store = Math.random() < 0.5 ? "Walmart" : "Aldi";
  const placement = cold
    ? `inside a real ${store} grocery refrigerator or freezer aisle with glass doors, cold LED lighting, condensation on the door edges, and rows of nearby products`
    : `on a real ${store} grocery store shelf in the correct aisle for this product, with shelf rails, price tags, fluorescent retail lighting, and nearby competing products`;
  return `
${iphoneRetailPhotoImperfectionPrompt()}

No text overlays, no captions, no watermarks.

Create a realistic iPhone photo of ${placement}.

Hero product/aisle subject: ${item}.

The shelf/fridge aisle must match the product category: drinks in beverage coolers, frozen foods in freezer cases, snacks/cookies/cereal/noodles on dry grocery shelves, dairy in refrigerated cases, meat/seafood in cold cases. Make it look like a real casual shopper photo, not a clean ad. Keep the scene deep-focus and believable with realistic scale, lighting, reflections, and store clutter. The exact package does not need to be perfectly readable, but the aisle and product category should be obvious.
`.trim();
}

const LABELY_DB_BATCH_COUNT = 6;

/** Default target for large iPhone packs; export itself scales to the saved gallery. */
const GALLERY_IPHONE_DEVICE_COUNT = 20;

/** Valcoin gallery export: 6 batches ├ù 20 unique slideshows = 120 (same iPhone ZIP layout as Labely food DB). */
const VALCOIN_IPHONE_SLIDESHOWS_PER_BATCH = 20;
const VALCOIN_IPHONE_PACK_TOTAL = LABELY_DB_BATCH_COUNT * VALCOIN_IPHONE_SLIDESHOWS_PER_BATCH;

/**
 * Batch-gallery export: one ZIP per iPhone folder, using whatever batch-generated
 * shows are currently saved. Each iPhone gets one slideshow from each available
 * batch when present; uneven batches still export their remaining items.
 * @returns {null | { error: string } | { zipPlans: { iphoneNumber: number, jobs: { zipRelPath: string, show: object }[] }[] }}
 */
function tryBuildIphoneBatchZipPlan(savedSlideshows) {
  if (!Array.isArray(savedSlideshows) || savedSlideshows.length === 0) return null;

  const batchMetaOk = (bn) =>
    Number.isFinite(bn) && bn >= 1 && bn <= LABELY_DB_BATCH_COUNT;

  const rows = savedSlideshows.map((show, origIdx) => ({
    show,
    batchNumber: Number(show?.batchNumber),
    batchSlideshowIndex: Number(show?.batchSlideshowIndex),
    origIdx,
  }));

  const hasBatchMeta = (r) => batchMetaOk(r.batchNumber);
  const anyBatch = rows.some(hasBatchMeta);
  const allBatch = rows.every(hasBatchMeta);

  if (anyBatch && !allBatch) {
    return {
      error:
        "This gallery mixes batch-generated slideshows with others. Remove non-batch items or regenerate so every thumbnail uses batch export metadata.",
    };
  }
  if (!allBatch) return null;

  const appIds = new Set(rows.map((r) => String(r.show?.appId || "").trim()).filter(Boolean));
  if (appIds.size > 1) {
    return {
      error:
        "This gallery mixes different apps. iPhone pack export needs every item from the same app (all Labely or Valcoin batch runs).",
    };
  }

  /** @type {Map<number, typeof rows>} */
  const groups = new Map();
  for (let b = 1; b <= LABELY_DB_BATCH_COUNT; b++) groups.set(b, []);
  for (const row of rows) {
    groups.get(row.batchNumber).push(row);
  }

  for (let b = 1; b <= LABELY_DB_BATCH_COUNT; b++) {
    groups.get(b).sort((a, c) => {
      const ai = Number.isFinite(a.batchSlideshowIndex) ? a.batchSlideshowIndex : 0;
      const ci = Number.isFinite(c.batchSlideshowIndex) ? c.batchSlideshowIndex : 0;
      if (ai !== ci) return ai - ci;
      return a.origIdx - c.origIdx;
    });
  }

  const activeBatches = Array.from({ length: LABELY_DB_BATCH_COUNT }, (_, i) => i + 1)
    .filter((b) => groups.get(b).length > 0);
  if (activeBatches.length === 0) return null;

  const phoneCount = Math.max(...activeBatches.map((b) => groups.get(b).length));

  const zipPlans = [];
  let encodeOrdinal = 0;
  for (let phone = 0; phone < phoneCount; phone++) {
    const jobs = [];
    for (const b of activeBatches) {
      const row = groups.get(b)[phone];
      if (!row) continue;
      const filename = sequentialRandomMp4Name(encodeOrdinal++, row.show);
      jobs.push({ zipRelPath: filename, show: row.show });
    }
    if (jobs.length > 0) zipPlans.push({ iphoneNumber: phone + 1, jobs });
  }

  return { zipPlans };
}

/** Unique `.png` basename for ZIP (order inside archive = capture order). */
function uniqueRandomZipPngName(usedNames) {
  let name;
  do {
    name = `${randomExportHex(10)}.png`;
  } while (usedNames.has(name));
  usedNames.add(name);
  return name;
}

function uniqueZipPngPath(usedNames, dir = "", orderIndex = null) {
  const cleanDir = String(dir || "").replace(/^\/+|\/+$/g, "");
  if (!cleanDir) return uniqueRandomZipPngName(usedNames);
  let name;
  do {
    const prefix = Number.isFinite(orderIndex)
      ? `${String(orderIndex + 1).padStart(3, "0")}-`
      : "";
    name = `${cleanDir}/${prefix}${randomExportHex(10)}.png`;
  } while (usedNames.has(name));
  usedNames.add(name);
  return name;
}

function iphoneFolderName(iphoneNumber) {
  return `iPhone ${String(iphoneNumber).padStart(2, "0")}`;
}

function slideshowFolderName(orderIndexZeroBased, show = null, fallback = "") {
  const batch = Number(show?.batchNumber);
  const foodToken =
    sanitizeFileToken(show?.batchFoodName)
    || sanitizeFileToken(fallback)
    || (String(show?.appId || "").trim() === "valcoin" ? "coins" : "food");
  const batchPrefix = Number.isFinite(batch) && batch > 0 ? `batch-${batch}-` : "";
  return `Slideshow ${String(orderIndexZeroBased + 1).padStart(2, "0")} ${batchPrefix}${foodToken}`.trim();
}

/** Per-file ZIP metadata (fflate): variable mod time + short internal comment. */
function randomZipEntryOptions() {
  const skewMs = Math.floor(Math.random() * (4 * 365.25 * 24 * 3600 * 1000));
  return {
    level: 1,
    mtime: Date.now() - skewMs,
    comment: randomExportHex(6),
  };
}

const waitForFonts = async () => {
  if (!document.fonts?.ready) return;
  try {
    await document.fonts.ready;
  } catch {}
};

/** Ensure every <img> under the preview has loaded/decoded so html-to-image paints pixels (not empty/black). */
const waitForImagesDecoded = async (root) => {
  if (!root) return;
  const imgs = [...root.querySelectorAll("img")];
  await Promise.all(
    imgs.map(
      (img) =>
        new Promise((resolve) => {
          if (img.complete && img.naturalWidth > 0) {
            resolve();
            return;
          }
          const done = () => resolve();
          img.addEventListener("load", done, { once: true });
          img.addEventListener("error", done, { once: true });
        })
    )
  );
  await Promise.all(
    imgs.map((img) => (img.decode ? img.decode().catch(() => {}) : Promise.resolve()))
  );
};

// Scale preview DOM ΓåÆ 1080px wide export without forcing canvasWidth/height (breaks img paint in foreignObject on some browsers).
const EXPORT_CAPTURE_PIXEL_RATIO = 1080 / Math.round(1080 * DISPLAY_SCALE);

export default function ConfigPanel({
  config, setConfig, updateConfig, updateSlot, updateMatchItem,
  currentSlide, setCurrentSlide, totalSlides,
  isExporting, setIsExporting, exportProgress, setExportProgress,
  exportStatus, setExportStatus,
  onBusyChange, registerRefreshSlide, onSlideshowSaved, onSavedSlideshowsChange,
  activeShowIdx = null,
  savedSlideshows = [],
  numSlideshows,
  setNumSlideshows,
  batchImageDataUrls,
  setBatchImageDataUrls,
  persistHomeSessionNow,
  farmUpload = null,
  autoRunBatch = false,
}) {
  const isFarmAutomation = isFarmUploadActive(farmUpload);
  const labelyBraveReusePhotos = isFarmAutomation && config.labelyBraveReusePhotos !== false;
  const brand = getBrand(config);
  const isValcoin = brand.appId === "valcoin";
  const isLabely = brand.appId === "labely";
  const labelyUseSelfieImage = isLabely && !!config.labelyUseSelfieImage;
  const isValcoinIphonePackBatchMode = isValcoin && isLabelyScanTourFormat(config) && !isFarmAutomation;
  const labelyUploadsLocked = isLabely && !!config.labelyAiProducts;
  const labelyFoodDbBatchRows = Array.isArray(config.labelyFoodDbBatches) ? config.labelyFoodDbBatches : [];
  const labelyUseBraveImages = config.labelyUseBraveImages !== false;
  const isLabelyFoodDbBatchMode =
    isLabely
    && config.labelyUseFoodDatabasePhotos !== false
    && labelyFoodDbBatchRows.some(
      (b) =>
        (Number(b?.slideshowCount) || 0) > 0
        && String(b?.itemsRaw || "").split("\n").some((line) => line.trim()),
    );
  const farmVideoGenrePlan = useMemo(() => {
    const fromConfig = Array.isArray(config.labelyFarmVideoGenres)
      ? config.labelyFarmVideoGenres
      : [];
    if (fromConfig.length >= LABELY_FARM_VIDEOS_PER_PHONE) {
      return fromConfig.slice(0, LABELY_FARM_VIDEOS_PER_PHONE).map((genre, i) => ({
        video: i + 1,
        genre: String(genre || "").trim(),
      }));
    }
    const byVideo = new Map();
    for (const b of labelyFoodDbBatchRows) {
      const video = Number(b?.videoOnPhone);
      const genre = String(b?.foodGenre || b?.foodTypes?.[0] || "").trim();
      if (video > 0 && genre && !byVideo.has(video)) byVideo.set(video, genre);
    }
    return [1, 2, 3]
      .map((video) => ({ video, genre: byVideo.get(video) || "" }))
      .filter((row) => row.genre);
  }, [config.labelyFarmVideoGenres, labelyFoodDbBatchRows]);
  const farmUniqueProductCount = useMemo(() => {
    if (!labelyBraveReusePhotos) return null;
    const seen = new Set();
    for (const b of labelyFoodDbBatchRows) {
      for (const line of String(b?.itemsRaw || "").split("\n")) {
        const name = line.trim();
        if (name) seen.add(name.toLowerCase());
      }
    }
    return seen.size;
  }, [labelyBraveReusePhotos, labelyFoodDbBatchRows]);
  const savedForCurrentApp = useMemo(() => {
    const aid = config.appId ?? "thrifty";
    return savedSlideshows.filter((s) => savedShowMatchesApp(s, aid));
  }, [savedSlideshows, config.appId]);
  const referencesDirLabel =
    brand.appId === "valcoin"
      ? "public/valcoin/references/"
      : brand.appId === "labely"
        ? "public/labely/references/"
        : "public/references/";

  const VALUABLE_US_COINS = [
    // Key-date / classic
    "1909-S VDB Lincoln cent",
    "1916-D Mercury dime",
    "1877 Indian Head cent",
    "1901-S Barber quarter",
    "1894-S Barber dime",
    "1913 Liberty Head nickel",
    "1932-D Washington quarter",
    "1932-S Washington quarter",
    "1893-S Morgan silver dollar",
    "1921 Peace dollar",
    "1937-D 3-legged Buffalo nickel",
    "1922 no D Lincoln cent",
    "1914-D Lincoln cent",
    "1926-S Buffalo nickel",
    "1908-S Indian Head cent",
    "1873-CC Seated Liberty dollar",
    "1907 High Relief Saint-Gaudens double eagle",
    "1885 Liberty Head nickel",
    // Modern / popular errors & varieties
    "2004-D Wisconsin quarter (extra leaf error)",
    "1955 Lincoln cent (doubled die obverse)",
    "1972 Lincoln cent (doubled die obverse)",
    "1943 copper Lincoln cent",
    "1969-S Lincoln cent (doubled die obverse)",
    "1982 no-mint-mark Roosevelt dime (error variety)",
    "2000-P Sacagawea dollar (Cheerios variety)",
    "2007 Presidential dollar (missing edge lettering error)",
    "1995 doubled die Lincoln cent",
    // Proof / silver issues people recognize
    "1976-S silver Washington quarter (proof)",
    "1964 Washington quarter (proof)",
    "1892 Columbus commemorative half dollar",
    "1986 American Silver Eagle (bullion)",
    "1995-W American Silver Eagle (proof)",
    "1933 Saint-Gaudens double eagle",
  ];

  const DEFAULT_PROMPT = isValcoin
    ? "A single valuable US quarter coin on a wooden table, photographed like a real iPhone photo shot on 0.5├ù (ultra-wide). The coin should be a real existing valuable variety (random pick), natural room lighting, no hands, no text overlays, no other coins, no props. Composition: the coin should appear smaller in the frame (not filling the shot) with lots of surrounding table visible. Lens/look: subtle ultra-wide edge stretch and mild barrel distortion like iPhone 0.5├ù. Quality: intentionally a bit worse/rough ΓÇö slightly blurry/soft focus like a quick snap, less sharp, mild motion blur or missed focus is okay. Color: iPhone-like but a bit bland/flat (slightly desaturated, lower contrast), not cinematic. Texture: visible sensor grain and minor compression artifacts. Include realistic imperfections: light dust, tiny lint specks, faint fingerprints/smudges, small nicks, micro-scratches, slight wear/toning, and minor surface blemishes."
    : isLabely
    ? "Labely uses your uploaded photos only ΓÇö this prompt is not used to generate images. You can leave it or add notes for yourself."
    : "POV into a blue thrift shopping cart (buggy) full of tossed secondhand clothes ΓÇö garments may lie upside-down or sideways; bottom hems/waistbands should look softly folded or cuffed (no people, no hands). XXL hero piece: faded washed-out colors only, cotton lint balls, stray dog hair, slight print/color imperfections. Concrete floor and aisles behind, fluorescent light, shallow DOF, no overlays.";

  const [imageModel, setImageModelRaw] = useState("gpt-image-1"); // "gpt-image-1" | "gemini"
  const setImageModel = (v) => { setImageModelRaw(v); localStorage.setItem("ts_image_model", v); };
  const [globalPrompt, setGlobalPrompt] = useState(DEFAULT_PROMPT);
  const [generatingSlot, setGeneratingSlotRaw] = useState(null);
  const setGeneratingSlot = (val) => {
    setGeneratingSlotRaw(val);
    onBusyChange?.(val !== null);
  };
  const [aiErrors, setAiErrors] = useState({});
  const [genAllProgress, setGenAllProgress] = useState(null);
  // genAllProgress shape: { total: 6, done: number, current: number, phase: string, slotsDone: Set }
  const [referenceImages, setReferenceImages] = useState(null);
  const [mounted, setMounted] = useState(false);
  const storeKey = (base) => `${base}_${brand.appId}`;
  // Always start with consistent defaults for SSR; sync all persisted values from localStorage after mount
  const [brandItemsRaw, setBrandItemsRaw] = useState(DEFAULT_BRAND_LIST);
  useEffect(() => {
    const savedModel = localStorage.getItem("ts_image_model");
    if (savedModel) setImageModelRaw(savedModel);
    const savedPrompt = localStorage.getItem(storeKey("ts_global_prompt"));
    if (savedPrompt != null) setGlobalPrompt(savedPrompt);
    else setGlobalPrompt(DEFAULT_PROMPT);
    if (isLabely) {
      const raw = typeof config.labelyFoodItemsRaw === "string" ? config.labelyFoodItemsRaw : "";
      setBrandItemsRaw(raw);
      localStorage.setItem(storeKey("ts_brand_items"), raw);
      return;
    }
    const savedBrands = localStorage.getItem(storeKey("ts_brand_items"));
    if (savedBrands?.trim()) setBrandItemsRaw(savedBrands);
    else setBrandItemsRaw(isValcoin ? VALUABLE_US_COINS.join("\n") : DEFAULT_BRAND_LIST);
  }, [brand.appId, isLabely, config.labelyFoodItemsRaw]); // reload per-brand persisted values

  const pickValuableUSCoin = () => {
    const idx = Math.floor(Math.random() * VALUABLE_US_COINS.length);
    return VALUABLE_US_COINS[idx];
  };

  // When switching to Valcoin, make the default prompt/list coin-appropriate
  // (only if the user hasn't already customized them in localStorage).
  useEffect(() => {
    if (!mounted) return;
    if (!isValcoin) return;
    const savedPrompt = localStorage.getItem(storeKey("ts_global_prompt"));
    const savedBrands = localStorage.getItem(storeKey("ts_brand_items"));
    if (!savedPrompt) {
      setGlobalPrompt(DEFAULT_PROMPT);
      localStorage.setItem(storeKey("ts_global_prompt"), DEFAULT_PROMPT);
    }
    if (!savedBrands) {
      const list = VALUABLE_US_COINS.join("\n");
      setBrandItemsRaw(list);
      localStorage.setItem(storeKey("ts_brand_items"), list);
    }
  }, [mounted, isValcoin, brand.appId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Parsed brand items (non-empty lines) ΓÇö fall back to defaults when empty
  const brandItems = (() => {
    if (isLabely) {
      const raw =
        typeof config.labelyFoodItemsRaw === "string" ? config.labelyFoodItemsRaw : brandItemsRaw;
      return raw.split("\n").map((l) => l.trim()).filter(Boolean);
    }
    const parsed = brandItemsRaw.split("\n").map((l) => l.trim()).filter(Boolean);
    if (parsed.length > 0) return parsed;
    return DEFAULT_BRAND_LIST.split("\n").map((l) => l.trim()).filter(Boolean);
  })();

  const getCaptureNode = () => document.getElementById("video-preview-root");

  const getCaptureOptions = (bgColor, fontEmbedCSS) => ({
    backgroundColor: bgColor,
    pixelRatio: EXPORT_CAPTURE_PIXEL_RATIO,
    // html-to-image re-fetches every http(s) img when cacheBust is on ΓåÆ CORS failures.
    cacheBust: false,
    includeQueryParams: false,
    ...(fontEmbedCSS ? { fontEmbedCSS } : {}),
  });

  const captureSlideCanvas = async (bgColor, fontEmbedCSS) => {
    const el = getCaptureNode();
    if (!el) return null;

    await waitForPreviewPaint();
    await waitForFonts();
    await inlineRemoteImagesInElement(el, {
      strict: needsExportImageInlining(config),
    });
    await waitForImagesDecoded(el);
    return toCanvas(el, getCaptureOptions(bgColor, fontEmbedCSS));
  };

  const captureLivePreviewThumbnail = async () => {
    const el = getCaptureNode();
    if (!el) return null;
    const info = getSlideInfo(config, currentSlide);
    const bgColor =
      info.type === "collage"
        ? "#111111"
        : info.type === "fullBleed" || info.type === "imessage" || info.type === "starterPack" || info.type === "labelyShelfIntro"
        ? "#000000"
        : "#ffffff";

    try {
      await waitForPreviewPaint();
      await waitForFonts();
      await waitForImagesDecoded(el);
      const fontEmbedCSS = await getFontEmbedCSS(el);
      return toJpeg(el, {
        ...getCaptureOptions(bgColor, fontEmbedCSS),
        quality: 0.92,
      });
    } catch (err) {
      console.error("Preview thumbnail capture failed", err);
      return null;
    }
  };

  // Load reference images (brand-specific) on mount (client only)
  useEffect(() => {
    setMounted(true);
    fetch(`/api/references?appId=${encodeURIComponent(brand.appId)}`)
      .then((r) => r.json())
      .then((d) => setReferenceImages(d.images || []))
      .catch(() => setReferenceImages([]));
  }, [brand.appId]);

  const cancelGenRef = useRef(false);
  const jobPausedRef = useRef(false);
  const apiKeyWarnedRef = useRef(false);
  const abortRef = useRef(null); // AbortController for force-stopping in-flight requests
  const foodDbSuggestionCacheRef = useRef(new Map());
  /** Brave product URLs + content hashes reserved this generate run (unique-photo mode only). */
  const sessionBraveReservedRef = useRef(new Set());
  const sessionBraveContentHashesRef = useRef(new Set());
  /** Farm reuse mode: one Brave URL per product name for the whole batch run. */
  const productBraveUrlCacheRef = useRef(new Map());
  /** Server-side in-memory reservation scope for one slideshow. */
  const braveSlideshowTokenRef = useRef(null);

  const resetLabelyBraveSession = useCallback(() => {
    sessionBraveReservedRef.current = new Set();
    sessionBraveContentHashesRef.current = new Set();
    productBraveUrlCacheRef.current = new Map();
  }, []);

  const beginLabelySlideshowBraveRun = useCallback(() => {
    braveSlideshowTokenRef.current = randomExportHex(8);
  }, []);

  const ensureLabelyBraveSlideshowToken = useCallback(() => {
    if (!braveSlideshowTokenRef.current) {
      braveSlideshowTokenRef.current = randomExportHex(8);
    }
    return braveSlideshowTokenRef.current;
  }, []);

  const labelyBraveExcludePayload = useCallback((extraUrls = [], extraHashes = []) => {
    const urls = new Set(sessionBraveReservedRef.current);
    const hashes = new Set(sessionBraveContentHashesRef.current);
    for (const raw of extraUrls) {
      const u = String(raw || "").trim();
      if (u) urls.add(u);
    }
    for (const raw of extraHashes) {
      const h = String(raw || "").trim();
      if (h) hashes.add(h);
    }
    for (const slot of config.slots ?? []) {
      const u = String(slot?.labelyDbImageUrl || "").trim();
      if (u) urls.add(u);
    }
    for (const show of savedSlideshows ?? []) {
      if (!savedShowMatchesApp(show, "labely")) continue;
      for (const slot of show.slots ?? []) {
        const u = String(slot?.labelyDbImageUrl || "").trim();
        if (u) urls.add(u);
      }
    }
    return {
      excludeBraveImageUrls: [...urls],
      excludeBraveContentHashes: [...hashes],
      braveSlideshowToken: ensureLabelyBraveSlideshowToken(),
    };
  }, [config.slots, savedSlideshows, ensureLabelyBraveSlideshowToken]);

  const labelyBraveExcludeUrls = useCallback(() => {
    return labelyBraveExcludePayload().excludeBraveImageUrls;
  }, [labelyBraveExcludePayload]);

  const noteLabelyBravePicked = useCallback((ly) => {
    const u = String(ly?.labelyDbImageUrl || "").trim();
    if (u) sessionBraveReservedRef.current.add(u);
    const h = String(ly?.labelyBraveContentHash || "").trim();
    if (h) sessionBraveContentHashesRef.current.add(h);
  }, []);

  const foodDbKeyFor = useCallback((query) => String(query || "").trim().toLowerCase(), []);

  const foodImageLookupBody = useCallback(
    () => ({ useBraveImages: labelyUseBraveImages }),
    [labelyUseBraveImages],
  );

  const pickFoodDbBraveUrl = useCallback((matches, foodName, usedUrlSet) => {
    if (!matches || typeof matches !== "object") return "";
    const want = String(foodName || "").trim().toLowerCase();
    const key = Object.keys(matches).find((k) => k.toLowerCase() === want);
    const row = key ? matches[key] : null;
    const details = Array.isArray(row?.candidateDetails) ? row.candidateDetails : [];
    for (const d of details) {
      const u = String(d?.imageUrl || "").trim();
      if (u && !usedUrlSet.has(u)) return u;
    }
    return "";
  }, []);

  const pickFoodDbBraveCandidateUrls = useCallback((matches, foodName, usedUrlSet) => {
    if (!matches || typeof matches !== "object") return [];
    const want = String(foodName || "").trim().toLowerCase();
    const key = Object.keys(matches).find((k) => k.toLowerCase() === want);
    const row = key ? matches[key] : null;
    const details = Array.isArray(row?.candidateDetails) ? row.candidateDetails : [];
    const out = [];
    for (const d of details) {
      const u = String(d?.imageUrl || "").trim();
      if (u && !usedUrlSet.has(u) && !out.includes(u)) out.push(u);
    }
    return out;
  }, []);

  const seedPersistedBraveUsedFromGallery = useCallback(async () => {
    const urls = labelyBraveExcludeUrls();
    if (!urls.length) return;
    try {
      await fetch("/api/brave-used-images", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls }),
      });
    } catch (e) {
      console.warn("[labely] seed brave used urls", e);
    }
  }, [labelyBraveExcludeUrls]);

  const beginLabelyBraveGenerateRun = useCallback(async () => {
    resetLabelyBraveSession();
    beginLabelySlideshowBraveRun();
    if (config.labelyUseBraveImages !== false) {
      await seedPersistedBraveUsedFromGallery();
    }
  }, [config.labelyUseBraveImages, resetLabelyBraveSession, beginLabelySlideshowBraveRun, seedPersistedBraveUsedFromGallery]);

  const waitWhilePaused = useCallback(async () => {
    while (jobPausedRef.current && !cancelGenRef.current) {
      await new Promise((r) => setTimeout(r, 120));
    }
  }, []);

  const hardStop = useCallback(() => {
    cancelGenRef.current = true;
    jobPausedRef.current = false;
    try { abortRef.current?.abort("stopped"); } catch {}
    abortRef.current = null;
    if (farmUpload?.jobId) markFarmJobAutoRunCancelled(farmUpload.jobId);
    setGeneratingSlotRaw(null);
    onBusyChange?.(false);
    setIsExporting(false);
    setGenAllProgress((p) => (p ? { ...p, phase: "Stopped." } : null));
    clearJobHeartbeat();
    clearGlobalJob();
    setTimeout(() => setGenAllProgress(null), 2000);
  }, [farmUpload?.jobId, onBusyChange, setIsExporting, setGenAllProgress]);

  useEffect(() => {
    jobControls.pause = () => {
      jobPausedRef.current = true;
      const j = getGlobalJob();
      if (j) patchGlobalJob({ paused: true });
    };
    jobControls.resume = () => {
      jobPausedRef.current = false;
      const j = getGlobalJob();
      if (j) patchGlobalJob({ paused: false });
    };
    jobControls.stop = hardStop;
    return () => {
      jobControls.pause = () => {};
      jobControls.resume = () => {};
      jobControls.stop = () => {};
    };
  }, [hardStop]);

  useEffect(() => {
    const onMessage = (ev) => {
      if (ev?.data?.type !== "autoslideshow:stop") return;
      hardStop();
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [hardStop]);

  useEffect(() => {
    const active = generatingSlot !== null || isExporting;
    if (!active) {
      clearGlobalJob();
      clearJobHeartbeat();
      return;
    }
    let percent = 0;
    let phase = "";
    if (isExporting) {
      percent = typeof exportProgress === "number" ? exportProgress : 0;
      phase = exportStatus || "ExportingΓÇª";
    } else if (genAllProgress) {
      const t = Math.max(1, Number(genAllProgress.total) || 1);
      percent = Math.round(((Number(genAllProgress.done) || 0) / t) * 100);
      phase = genAllProgress.phase || "WorkingΓÇª";
    } else {
      phase = generatingSlot === "all" ? "Preparing batchΓÇª" : "WorkingΓÇª";
    }
    setGlobalJob({
      percent: Math.min(100, Math.max(0, percent)),
      phase,
      paused: jobPausedRef.current,
      hint: farmUpload?.jobId
        ? "Farm automation runs in this browser tab. Keep the tab open until upload completes."
        : "Runs in this browser tab only (not on a server). You can switch away or minimize; work keeps going but may be slower in the background. Refresh or closing the tab stops the job.",
    });
    writeJobHeartbeat({ percent, phase });
    if (farmUpload?.jobId && phase) {
      appendAutomationLog(phase);
    }
  }, [generatingSlot, genAllProgress, isExporting, exportProgress, exportStatus, farmUpload?.jobId]);

  /**
   * Valcoin: Wikimedia Commons US coin photos only ΓÇö never AI-generated images.
   * Pass `excludeSourceUrls` to avoid returning a coin already used in the
   * current slideshow (keeps the 6-coin collage visually distinct).
   * @param {Set<string> | string[] | undefined} excludeSourceUrls
   */
  const fetchValcoinNumistaSlot = async (excludeSourceUrls) => {
    const numista = await fetchRandomNumistaCoin(abortRef.current?.signal, {
      maxAttempts: 4,
      excludeSourceUrls,
    });
    if (!numista?.dataUrl?.startsWith("data:image/")) return null;
    return numista;
  };

  const generateImage = async (index, prompt, brandItem) => {
    try {
      let b64 = null;

      if (isValcoin) {
        const numista = await fetchValcoinNumistaSlot();
        if (numista) return numista.dataUrl;
        if (cancelGenRef.current) return null;
        setAiErrors((p) => ({
          ...p,
          [index]: "Could not load a Wikimedia Commons coin photo. Try again in a moment.",
        }));
        return null;
      }

      const outFmt = config.outputFormat ?? "standard";

      const isNonApparelScene = outFmt === "starterPack";

      const brandName = brandItem || prompt?.trim() || "a clothing brand";

      // Reference photos (Thrifty: cart look; Valcoin: coin/table look)
      const refs = referenceImages || [];
      const matchingRefs = refs;

      const poseList = config.poseReferenceImages || [];
      let referenceInline = null;
      if (poseList.length > 0) {
        const raw = poseList[index % poseList.length]?.dataUrl;
        const parsed = parseDataUrl(raw);
        if (parsed) referenceInline = { mimeType: parsed.mimeType, base64: parsed.base64 };
      }

      // Variation mode: reference photo drives the scene; just swap the item
      // Pose person format: hands/arms allowed on first slide (index 0) only; all other slides = no hands.
      const posePersonFirstSlide = outFmt === "posePerson" && index === 0;

      if (isNonApparelScene) {
        // Starter pack / POV vibe: generate an iPhone photo of the prompt itself (not clothing-only).
        const scenePrompt = (prompt || "").trim() || brandName;
        const fullPrompt = `
${iphoneRetailPhotoImperfectionPrompt()}

No text overlays, no captions, no watermarks.

Subject: ${scenePrompt}

If the subject is an object (like germ-x, a mask, receipt piles, shipping labels), center it and make it visually obvious what it is. If it is a scene (like goodwill bins line, people lining up), make it documentary-style and realistic.
`.trim();

        const refFile = referenceInline
          ? null
          : (matchingRefs.length > 0
            ? matchingRefs[Math.floor(Math.random() * matchingRefs.length)]
            : null);

        const res = await fetch("/api/generate-image", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompt: fullPrompt,
            referenceFile: refFile || null,
            referenceInline: undefined,
            referenceRoot:
              brand.appId === "labely" ? "labely/references" : "references",
            model: imageModel,
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data?.error || "Image generation failed");
        b64 = data.b64 ?? null;
        if (b64) return `data:image/png;base64,${b64}`;
        throw new Error("No image returned");
      }

      const SHARED_RULES_INTRO = iphoneRetailPhotoImperfectionPrompt("thrift");

      const SHARED_RULES_NO_HANDS_MID = `
No hands or people rule (critical): Do not show human hands, arms, fingers, wrists, or any partial limbs. Do not show people in the foreground or midground. Do not show gloves that imply a hand inside. The product must never be held or carried. If distant background shoppers are visible, they must be tiny and incidental ΓÇö still in focus with the rest of the scene (no extra blur on people); show no discernible hands or arms.

Clothing-only: The hero item must always be an article of clothing or wearable garment (jeans, jacket, hoodie, tee, coat, sweater, pants, shorts, dress, etc.) ΓÇö never furniture, housewares, bags-as-prop-only, or non-apparel hard goods.

Shopping-cart "buggy" composition (critical):
Use a slightly high POV looking down into a bright blue plastic retail shopping cart (thrift-store buggy) with the classic diamond-lattice grid pattern on the basket sides. Fill the cart with a messy, chaotic pile of secondhand clothes ΓÇö thrown in carelessly: overlapping layers, wadded fabric, random folds, denim mixed with knits and prints. Individual garments may be oriented any way in the pile ΓÇö upside down, inside-out, sideways, or crumpled ΓÇö as long as the hero piece is identifiable. The bottom / hem / waistband area of visible garments should consistently read as softly folded, cuffed, or rolled (never a stiff factory-flat presentation). The featured brand garment must read clearly in the heap with other anonymous thrift garments around it. The pile must look tossed-in and uncurated ΓÇö never a neat stack, never a boutique flat-lay.

The subject must behave according to real-world physics. Fabric drape, weight, shadows, and contact between garments must look natural.

The camera should feel like a casual phone snapshot aimed down into the cart ΓÇö the whole scene sharp: pile, cart, floor, and store background all clearly defined (same deep-focus rule as above).`.trim();

      const SHARED_RULES_POSE_FIRST_MID = `
Pose format ΓÇö slide 1 only: Hands and arms are allowed on this slide only. Show a natural in-thrift-store shot where the item may be held or presented by hands (anatomy must look real). Do not show full faces ΓÇö keep the frame focused on the product and hands. This exception does not apply to any other slide.

Handling rule:
For most items (clothing, shoes, accessories, small objects, etc.), the item may be held by a human hand in a physically believable way. The hand should grip the object where a person would naturally hold it, with fingers and thumb stabilizing it. The object must appear fully supported with correct balance and weight.

Clothing rule: If the item is a jacket, hoodie, shirt, pants, coat, or any garment that would hang on a hanger, the person may be holding it by the coat hanger ΓÇö fingers around the hook or neck, garment hanging with natural drape. The hanger should look like a standard thrift wire or plastic hanger.

Clothing-only: the hero item must be a garment by the requested brand ΓÇö not furniture or non-apparel.

Footwear: If the brand piece is shoes, they may sit on top of or within the clothing pile in the cart.

The camera perspective should look like a first-person smartphone photo when the item is handheld, as if a shopper lifted the item to inspect it. The item and the store interior behind it must both stay sharp ΓÇö same deep-focus requirement; no background blur.

The subject must behave according to real-world physics. Gravity, orientation, contact points, shadows, and balance should all appear natural.`.trim();

      const SHARED_RULES_APPAREL_AUTHENTICITY = `
Garment authenticity (clothing only): Size the hero piece as XXL adult ΓÇö visibly oversized, relaxed boxy fit, roomy sleeves and torso length where appropriate. Hem / bottom edge treatment: the lower edge of the garment (whichever end is visible given orientation) should always appear softly folded, cuffed, or stacked ΓÇö never a razor-sharp pressed hem. Color palette: prefer faded, washed-out, sun-softened tones ΓÇö avoid saturated brand-new dyes. Surface detail (vary subtly across generations): small cotton lint balls (pilled specs), a few stray dog or pet hairs caught in the pile, minor color unevenness or slight print imperfections on graphics (slightly misregistered ink, hairline cracks in screen prints, gently worn lettering ΓÇö still recognizable as the real brand graphic, not fake text). Include wrinkled fabric, uneven hems, stretched collars, softened cotton, worn denim, casual imperfect resale condition. Other garments in the pile stay anonymous with a non-coordinated mix. Avoid pristine catalog styling.`.trim();

      const SHARED_RULES_OUTRO = `
Background: inside a Goodwill or similar thrift store ΓÇö polished concrete floor, fluorescent overhead lighting, distant racks (e.g. media, housewares), glass display cases, and typical resale-aisle clutter visible behind the cart. The cart and messy clothing pile stay the hero of the frame.

Lighting should match typical thrift store lighting: bright overhead fluorescent retail lighting inside a large indoor store with a slightly warehouse-style layout.

Maintain realistic perspective, scale, lighting direction, shadows, and reflections so the object appears physically integrated into the environment.

The final result should look like a natural thrifting discovery photo taken casually inside a Goodwill or secondhand store with an iPhone ΓÇö full-scene sharpness, natural iPhone color (not oversaturated), optional subtle lens smear from bright lights as described above.

Text and logo rendering rule: Graphics and logos physically printed or embroidered on the garment should look authentically thrift-worn ΓÇö often slightly faded, with occasional subtle print flaws (minor cracking, soft edges, slight color variation) consistent with the authenticity rules above. The design must still read as the real brand artwork, not invented typography.

Do NOT add any external overlays: no captions, subtitles, price tags, watermarks, floating labels, or any text that is not physically part of the item itself.`.trim();

      const SHARED_RULES = `${SHARED_RULES_INTRO}

${posePersonFirstSlide ? SHARED_RULES_POSE_FIRST_MID : SHARED_RULES_NO_HANDS_MID}

${SHARED_RULES_APPAREL_AUTHENTICITY}

${SHARED_RULES_OUTRO}`;

      let fullPrompt;
      if (referenceInline) {
        fullPrompt = posePersonFirstSlide
          ? `Match the uploaded pose reference: same body pose, arm position, camera angle, distance, and framing. Replace only the main garment with a specific, real, well-known clothing item by ${brandName} ΓÇö choose an iconic apparel piece this brand actually made. Keep the scene, lighting, and how the item is held aligned with the reference.\n\n${SHARED_RULES}`
          : `Use the uploaded pose image for camera angle and framing. Replace the hero with a specific, real clothing item by ${brandName}. Do not copy people, hands, arms, or faces. No hands in the output.\n\n${SHARED_RULES}`;
      } else if (matchingRefs.length > 0) {
        fullPrompt = posePersonFirstSlide
          ? `Use the uploaded reference as the main subject; preserve pose and hands if shown. Replace the hero garment with a specific, real, well-known clothing item by ${brandName} ΓÇö iconic apparel this brand actually made. Keep setting, lighting, and composition similar to the reference photo.\n\n${SHARED_RULES}`
          : `Match the uploaded reference image closely: same blue plastic shopping cart, messy thrown-in clothing pile, POV angle, and thrift-store background. Replace the main visible hero garment with a specific, real, well-known clothing item by ${brandName} ΓÇö choose an iconic apparel piece this brand actually made and is known for. Keep the chaotic tossed-in pile; garments may be upside down or sideways; hems should look softly folded per the rules ΓÇö not catalog-flat. If the reference shows hands or people, omit them ΓÇö no hands or arms in the output.\n\n${SHARED_RULES}`;
      } else {
        fullPrompt = `Generate a hero garment: a specific, real, well-known clothing item by ${brandName} ΓÇö choose an iconic apparel piece this brand actually made and is known for. Show it in the messy blue thrift buggy as described in the rules.\n\n${SHARED_RULES}`;
      }

      const refFile = referenceInline
        ? null
        : (matchingRefs.length > 0
          ? matchingRefs[Math.floor(Math.random() * matchingRefs.length)]
          : null);

      // Proxy through /api/generate-image ΓÇö server reads file from disk, no self-fetch, no stack overflow
      const res = await fetch("/api/generate-image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortRef.current?.signal,
        body: JSON.stringify({
          prompt: fullPrompt,
          referenceFile: refFile || null,
          referenceInline: referenceInline || undefined,
          model: imageModel,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || "Image generation failed");
      b64 = data.b64 ?? null;

      if (b64) return `data:image/png;base64,${b64}`;
      throw new Error("No image returned");
    } catch (err) {
      const msg = err?.message || String(err);
      if (!apiKeyWarnedRef.current && /api key required|api key not set|OPENAI_API_KEY|GEMINI_API_KEY/i.test(msg)) {
        apiKeyWarnedRef.current = true;
        alert("AI generation needs an API key. Add OPENAI_API_KEY (or GEMINI_API_KEY) to a .env.local file, restart `npm run dev`, then try again.");
      }
      setAiErrors((p) => ({ ...p, [index]: msg }));
      return null;
    }
  };

  const generateLabelyShelfIntroImage = async (itemName, brandName = "") => {
    try {
      const res = await fetch("/api/generate-image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortRef.current?.signal,
        body: JSON.stringify({
          prompt: labelyShelfScenePrompt(itemName, brandName),
          model: imageModel,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.error || "Shelf intro image generation failed");
      return data?.b64 ? `data:image/png;base64,${data.b64}` : null;
    } catch (err) {
      if (err?.name === "AbortError") return null;
      console.error("Labely shelf intro generation failed", err);
      return null;
    }
  };

  /** Scan tour slide 0 ΓÇö prefer API shelf intro, else AI shelf/carousel scene. */
  const resolveLabelyShelfIntroUrl = async (ly, { includeShelfIntro, useSelfieForSlot = false }) => {
    if (!includeShelfIntro || !ly?.name) return null;
    if (ly.shelfIntroDataUrl) return ly.shelfIntroDataUrl;
    if (useSelfieForSlot) return null;
    return generateLabelyShelfIntroImage(ly.name, ly.brand ?? "");
  };

  const fillLabelyFromImage = async (imageDataUrl, opts = {}) => {
    const uploadHint =
      typeof opts.uploadHint === "string" && opts.uploadHint.trim()
        ? opts.uploadHint.trim().slice(0, 160)
        : "";
    try {
      const res = await fetch("/api/labely", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortRef.current?.signal,
        body: JSON.stringify({
          imageDataUrl,
          ...(uploadHint ? { uploadHint } : {}),
          ...(opts.includeShelfIntro ? { includeShelfIntro: true } : {}),
        }),
      });
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  };

  /** Re-run vision on preview slots 0ΓÇô5 so Labely copy matches batch photos after shuffle/reorder. */
  const runLabelyVisionForPreviewSlots = async (batchUrls) => {
    if (!isLabely || config.labelyAiProducts) return;
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    try {
      for (let i = 0; i < Math.min(6, batchUrls.length); i++) {
        const url = batchUrls[i];
        if (!url) continue;
        setGeneratingSlot(i);
        setAiErrors((p) => ({ ...p, [i]: null }));
        const ly = await fillLabelyFromImage(url, { includeShelfIntro: i === 0 && isLabelyScanTourFormat(config) });
        if (ly?.name) {
          updateSlot(i, {
            itemName: ly.name,
            labelyBrand: ly.brand ?? "",
            ...badLabelyPatch(ly.score),
            labelyAnalysis: ly.analysis ?? "",
            labelyAnalysisTitle: ly.analysisTitle ?? "Labely's Analysis",
            labelyLegalNote: ly.labelyLegalNote?.trim() || "No lawsuits found.",
            ...(ly.shelfIntroDataUrl ? { labelyShelfImageUrl: ly.shelfIntroDataUrl } : {}),
          });
        } else {
          setAiErrors((p) => ({ ...p, [i]: "Could not analyze this photo." }));
        }
      }
    } finally {
      setGeneratingSlot(null);
      abortRef.current = null;
    }
  };

  /** No photo ΓÇö GPT picks a real retail SKU + score + analysis (real ingredients) + optional pack image (same as POST /api/labely with no body image). */
  const fillLabelyFromAi = async (seedHint, errorSlotIdx = null, opts = {}) => {
    const useSelfieImage = opts.useSelfieImage === true;
    try {
      const res = await fetch("/api/labely", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortRef.current?.signal,
        body: JSON.stringify({
          ...(seedHint?.trim() ? { seedHint: seedHint.trim() } : {}),
          useSelfieImage,
          useBraveImages: config.labelyUseBraveImages !== false,
          ...(opts.allowBraveReuse
            ? { allowBraveReuse: true }
            : config.labelyUseBraveImages !== false
              ? labelyBraveExcludePayload(
                  opts.braveExcludeExtraUrls ?? [],
                  opts.braveExcludeExtraHashes ?? [],
                )
              : {}),
          ...(opts.includeShelfIntro ? { includeShelfIntro: true } : {}),
          ...(opts.presetBraveImageUrl ? { presetBraveImageUrl: opts.presetBraveImageUrl } : {}),
          ...(opts.deferBraveUsedPersist ? { deferBraveUsedPersist: true } : {}),
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = typeof body?.error === "string" ? body.error : `Labely request failed (${res.status})`;
        if (typeof errorSlotIdx === "number") {
          setAiErrors((p) => ({ ...p, [errorSlotIdx]: msg }));
        }
        return null;
      }
      if (config.labelyUseBraveImages !== false && !opts.allowBraveReuse) noteLabelyBravePicked(body);
      if (body?.braveUsage) dispatchBraveUsageUpdated(body.braveUsage);
      return body;
    } catch (e) {
      if (typeof errorSlotIdx === "number") {
        setAiErrors((p) => ({ ...p, [errorSlotIdx]: e?.message || "Network error" }));
      }
      return null;
    }
  };

  /** Row index across all shows: 0ΓÇª(qty├ùslotsPerShowΓêÆ1). Rows 0ΓÇô5 mirror live preview slots. */
  const runLabelySlotWithDataUrl = async (globalIdx, dataUrl, labelyHints = {}) => {
    if (config.labelyAiProducts) return;
    if (!dataUrl || typeof dataUrl !== "string") return;
    setAiErrors((p) => ({ ...p, [globalIdx]: null }));
    setGeneratingSlot(globalIdx);
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    try {
      setBatchImageDataUrls((prev) => {
        const need = Math.max(prev.length, globalIdx + 1);
        const next = Array.from({ length: need }, (_, i) => (i < prev.length ? prev[i] : null));
        next[globalIdx] = dataUrl;
        return next;
      });
      if (globalIdx < 6) {
        updateSlot(globalIdx, { imageUrl: dataUrl });
        const ly = await fillLabelyFromImage(dataUrl, {
          ...labelyHints,
          includeShelfIntro: globalIdx === 0 && isLabelyScanTourFormat(config),
        });
        if (ly?.name) {
          updateSlot(globalIdx, {
            itemName: ly.name,
            labelyBrand: ly.brand ?? "",
            ...badLabelyPatch(ly.score),
            labelyAnalysis: ly.analysis ?? "",
            labelyAnalysisTitle: ly.analysisTitle ?? "Labely's Analysis",
            labelyLegalNote: ly.labelyLegalNote?.trim() || "No lawsuits found.",
            ...(ly.shelfIntroDataUrl ? { labelyShelfImageUrl: ly.shelfIntroDataUrl } : {}),
          });
        } else {
          setAiErrors((p) => ({ ...p, [globalIdx]: "Could not analyze this photo." }));
        }
      }
      setConfig((prev) => ({ ...prev, jitterSeed: (Math.random() * 0xffff) | 0 }));
    } catch (e) {
      setAiErrors((p) => ({ ...p, [globalIdx]: e?.message || "Upload failed" }));
    } finally {
      setGeneratingSlot(null);
      abortRef.current = null;
    }
  };

  const handleLabelySlotUpload = async (globalIdx, file) => {
    if (!isLikelyRasterImageFile(file)) return;
    let dataUrl;
    try {
      dataUrl = await fileToDisplayableDataUrl(file);
    } catch {
      setAiErrors((p) => ({ ...p, [globalIdx]: "Could not read this photo (try JPEG or HEIC)." }));
      return;
    }
    await runLabelySlotWithDataUrl(globalIdx, dataUrl, { uploadHint: file.name });
  };

  /** User-uploaded photo for Thrifty / Valcoin (no AI image gen). globalIdx ΓëÑ 6 = batch-only row. */
  const handleThriftyValcoinSlotFile = async (globalIdx, file) => {
    if (!isLikelyRasterImageFile(file)) return;
    setAiErrors((p) => ({ ...p, [globalIdx]: null }));
    setGeneratingSlot(globalIdx);
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    try {
      const dataUrl = await fileToDisplayableDataUrl(file);
      setBatchImageDataUrls((prev) => {
        const need = Math.max(prev.length, globalIdx + 1);
        const next = Array.from({ length: need }, (_, i) => (i < prev.length ? prev[i] : null));
        next[globalIdx] = dataUrl;
        return next;
      });
      if (globalIdx >= 6) {
        setConfig((prev) => ({ ...prev, jitterSeed: (Math.random() * 0xffff) | 0 }));
        return;
      }
      const slot = config.slots[globalIdx];
      const weightedPool = buildWeightedPool(brandItems);
      const randomBrand = weightedPool.length > 0
        ? weightedPool[Math.floor(Math.random() * weightedPool.length)]
        : null;
      if (isValcoin) {
        const hint = pickValuableUSCoin();
        const patch = await buildValcoinSlotPatch(hint, slot, dataUrl);
        updateSlot(globalIdx, patch);
      } else {
        const priceUpdates =
          !slot.spentPrice && !slot.soldPrice ? autoRandomPrices() : {};
        updateSlot(globalIdx, { imageUrl: dataUrl, ...priceUpdates });
        const grail = await autoTitleFromImage(dataUrl);
        let resolvedName = slot.itemName;
        let resolvedPrice = priceUpdates.soldPrice ?? slot.soldPrice;
        if (grail?.title) {
          resolvedName = grail.title;
          resolvedPrice = grail.price ?? resolvedPrice;
          updateSlot(globalIdx, {
            itemName: resolvedName,
            ...(grail.price ? { soldPrice: resolvedPrice } : {}),
            matchItems: autoSoldListings(resolvedName, resolvedPrice),
          });
        }
      }
      if ((config.outputFormat ?? "standard") === "imessageMom") {
        const slotNow = config.slots[globalIdx];
        const thread = await generateImessageThread(slotNow.itemName, slotNow.soldPrice);
        if (thread) updateSlot(globalIdx, { imessageThread: thread });
      }
      setConfig((prev) => ({ ...prev, jitterSeed: (Math.random() * 0xffff) | 0 }));
    } catch (e) {
      setAiErrors((p) => ({ ...p, [globalIdx]: e?.message || "Upload failed" }));
    } finally {
      setGeneratingSlot(null);
      abortRef.current = null;
    }
  };

  const handleGenerateOne = async (index) => {
    setAiErrors((p) => ({ ...p, [index]: null }));
    setGeneratingSlot(index);
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    if (isLabely) {
      if (config.labelyUseBraveImages !== false) ensureLabelyBraveSlideshowToken();
      try {
        if (config.labelyAiProducts) {
          const weightedPool = buildWeightedPool(brandItems);
          const hint =
            weightedPool.length > 0
              ? weightedPool[Math.floor(Math.random() * weightedPool.length)]
              : null;
          const includeShelfIntro = index === 0 && isLabelyScanTourFormat(config);
          const useSelfieForSlot = labelyUseSelfieImage && index === 0;
          const extraBraveUrls = (config.slots ?? [])
            .map((s) => s?.labelyDbImageUrl)
            .filter(Boolean);
          const ly = await fillLabelyFromAi(hint, index, {
            includeShelfIntro,
            useSelfieImage: useSelfieForSlot,
            braveExcludeExtraUrls: extraBraveUrls,
          });
          if (ly?.name) {
            if (useSelfieForSlot && !ly.shelfIntroDataUrl) {
              setAiErrors((p) => ({
                ...p,
                [index]: "Pilates selfie intro was not generated. Try again.",
              }));
              return;
            }
            const shelfIntroUrl = await resolveLabelyShelfIntroUrl(ly, {
              includeShelfIntro,
              useSelfieForSlot,
            });
            updateSlot(index, {
              itemName: ly.name,
              labelyBrand: ly.brand ?? "",
              ...badLabelyPatch(ly.score),
              labelyAnalysis: ly.analysis ?? "",
              labelyAnalysisTitle: ly.analysisTitle ?? "Labely's Analysis",
              labelyLegalNote: ly.labelyLegalNote?.trim() || "No lawsuits found.",
              ...(ly.imageDataUrl ? labelyProductImagePatch(ly) : {}),
              ...(shelfIntroUrl ? { labelyShelfImageUrl: shelfIntroUrl } : {}),
            });
            setConfig((prev) => ({ ...prev, jitterSeed: (Math.random() * 0xffff) | 0 }));
          } else {
            setAiErrors((p) => ({ ...p, [index]: "AI product generation failed." }));
          }
        } else {
          const slot = config.slots[index];
          if (!slot.imageUrl?.trim()) {
            setAiErrors((p) => ({ ...p, [index]: "Upload a photo for this slot first (sidebar)." }));
          } else {
            const includeShelfIntro = index === 0 && isLabelyScanTourFormat(config);
            const ly = await fillLabelyFromImage(slot.imageUrl, { includeShelfIntro });
            if (ly?.name) {
              const shelfIntroUrl = ly.shelfIntroDataUrl || (includeShelfIntro
                ? await generateLabelyShelfIntroImage(ly.name, ly.brand ?? "")
                : null);
              updateSlot(index, {
                itemName: ly.name,
                labelyBrand: ly.brand ?? "",
                ...badLabelyPatch(ly.score),
                labelyAnalysis: ly.analysis ?? "",
                labelyAnalysisTitle: ly.analysisTitle ?? "Labely's Analysis",
                labelyLegalNote: ly.labelyLegalNote?.trim() || "No lawsuits found.",
                ...(shelfIntroUrl ? { labelyShelfImageUrl: shelfIntroUrl } : {}),
              });
              setConfig((prev) => ({ ...prev, jitterSeed: (Math.random() * 0xffff) | 0 }));
            } else {
              setAiErrors((p) => ({ ...p, [index]: "Could not analyze this photo." }));
            }
          }
        }
      } finally {
        setGeneratingSlot(null);
        abortRef.current = null;
      }
      return;
    }
    const weightedPool = buildWeightedPool(brandItems);
    const randomBrand = weightedPool.length > 0
      ? weightedPool[Math.floor(Math.random() * weightedPool.length)]
      : null;
    if (isValcoin) {
      const numista = await fetchValcoinNumistaSlot();
      if (!numista) {
        setAiErrors((p) => ({
          ...p,
          [index]: "Could not load a Wikimedia Commons coin photo. Try again in a moment.",
        }));
      } else {
        const slot = config.slots[index];
        const catalogTitle = numista.title?.trim() || pickValuableUSCoin();
        const patch = await buildValcoinSlotPatch(catalogTitle, slot, numista.dataUrl);
        updateSlot(index, patch);
      }
    } else {
      const basePrompt = config.slots[index].prompt || globalPrompt;
      const prompt = randomBrand ? `${basePrompt}\n\nSpecific item to depict: ${randomBrand}.` : basePrompt;
      const url = await generateImage(index, prompt, randomBrand);
      if (url) {
        const slot = config.slots[index];
        const priceUpdates = (!slot.spentPrice && !slot.soldPrice) ? autoRandomPrices() : {};
        updateSlot(index, { imageUrl: url, ...priceUpdates });
        const grail = await autoTitleFromImage(url);
        let resolvedName = slot.itemName;
        let resolvedPrice = priceUpdates.soldPrice ?? slot.soldPrice;
        if (grail?.title) {
          resolvedName = grail.title;
          resolvedPrice = grail.price ?? resolvedPrice;
          updateSlot(index, {
            itemName: resolvedName,
            ...(grail.price ? { soldPrice: resolvedPrice } : {}),
            matchItems: autoSoldListings(resolvedName, resolvedPrice),
          });
        }
        if ((config.outputFormat ?? "standard") === "imessageMom") {
          const thread = await generateImessageThread(resolvedName, resolvedPrice);
          if (thread) updateSlot(index, { imessageThread: thread });
        }
      }
    }
    // Refresh jitter seed so every generation produces unique pixel-level layout
    setConfig((prev) => ({ ...prev, jitterSeed: (Math.random() * 0xffff) | 0 }));
    setGeneratingSlot(null);
    abortRef.current = null;
  };

  // ΓöÇΓöÇ AI: generate iMessage thread for imessageMom format ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  const generateImessageThread = async (itemName, soldPrice) => {
    try {
      const res = await fetch("/api/generate-text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortRef.current?.signal,
        body: JSON.stringify({ type: "imessageThread", itemName, soldPrice, appId: config.appId }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      return data.thread ?? null;
    } catch { return null; }
  };

  const generateStarterPackText = async () => {
    try {
      const res = await fetch("/api/generate-text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortRef.current?.signal,
        body: JSON.stringify({ type: "starterPackThrifting" }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      const headline = typeof data.headline === "string" ? data.headline : "";
      const items = Array.isArray(data.items) ? data.items : [];
      const imagePrompts = Array.isArray(data.imagePrompts) ? data.imagePrompts : [];
      if (!headline || items.length !== 3) return null;
      return { headline, items, imagePrompts };
    } catch { return null; }
  };

  // Always regenerates fresh headline + titles + image prompts every call.
  // Returns the sp data so callers can pass prompts directly to ensureStarterPackImages.
  const ensureStarterPackAutofill = async () => {
    const sp = await generateStarterPackText();
    if (!sp) return null;

    updateConfig("starterPackHeadline", sp.headline);
    for (let i = 0; i < 3; i++) {
      updateSlot(i, {
        itemName: sp.items[i] ?? "",
        prompt: sp.imagePrompts[i] ?? sp.items[i] ?? "",
        imageUrl: null,
      });
    }
    return sp;
  };

  // Accepts explicit prompts array to avoid reading stale React state.
  // Falls back to cfgForSlots.slots (defaults to live config) when prompts are incomplete.
  const ensureStarterPackImages = async (prompts, cfgForSlots = null) => {
    const slotCfg = cfgForSlots ?? config;
    const valcoinSlots = getBrand(slotCfg).appId === "valcoin";
    for (let i = 0; i < 3; i++) {
      const p = (prompts?.[i] ?? "").trim()
        || (slotCfg.slots?.[i]?.prompt ?? "").trim()
        || (slotCfg.slots?.[i]?.itemName ?? "").trim();
      if (!p) continue;
      setExportStatus(valcoinSlots ? `Loading coin photo ${i + 1}/3ΓÇª` : `Generating starter pack image ${i + 1}/3ΓÇª`);
      if (valcoinSlots) {
        const numista = await fetchValcoinNumistaSlot();
        if (numista) updateSlot(i, { imageUrl: numista.dataUrl });
      } else {
        const url = await generateImage(i, p, null);
        if (url) updateSlot(i, { imageUrl: url });
      }
    }
  };

  // (removed POV format; starterPack covers POV vibe now)

  // ΓöÇΓöÇ GPT-4 Vision: generate item title from image ΓöÇΓöÇ
  // ΓöÇΓöÇ Grail Identifier: returns { title, price } from image ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  const autoTitleFromImage = async (imageUrl) => {
    try {
      const res = await fetch("/api/generate-image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortRef.current?.signal,
        body: JSON.stringify({
          action: "identify",
          imageUrl,
        }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      return {
        title: data.title || null,
        price: data.price || null,
      };
    } catch { return null; }
  };

  // ΓöÇΓöÇ Random thrift spent price + 40-50% markup sold price ΓöÇΓöÇ
  const autoRandomPrices = () => {
    const THRIFT_PRICES = [2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 15, 18, 20, 22, 25];
    const spent = THRIFT_PRICES[Math.floor(Math.random() * THRIFT_PRICES.length)];
    const multiplier = 1.40 + Math.random() * 0.10; // 40-50% more
    const sold = Math.round(spent * multiplier);
    return { spentPrice: String(spent), soldPrice: String(sold) };
  };

  /** Text-only: simplify a raw Wikimedia / filename title into a readable coin name. */
  const simplifyCoinTitle = async (rawTitle) => {
    const raw = String(rawTitle ?? "").trim();
    if (!raw) return null;
    try {
      const res = await fetch("/api/generate-image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortRef.current?.signal,
        body: JSON.stringify({ action: "coinTitle", text: raw }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      const title = String(data?.title ?? "").trim();
      return title && !/^\d+$/.test(title) ? title : null;
    } catch {
      return null;
    }
  };

  const coinPrices = async (coinName) => {
    const name = String(coinName ?? "").trim();
    if (!name) return null;
    try {
      const res = await fetch("/api/generate-image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortRef.current?.signal,
        body: JSON.stringify({ action: "coinPrices", text: name }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      if (!data?.buy || !data?.sell) return null;
      return { spentPrice: String(data.buy), soldPrice: String(data.sell) };
    } catch {
      return null;
    }
  };

  /**
   * Fill a Valcoin slot from a coin title (Wikimedia file title or brand-list
   * hint) ΓÇö never from vision on the photo. Raw titles are simplified via AI,
   * then prices come from coinPrices(simplified title).
   */
  const buildValcoinSlotPatch = async (catalogTitle, slot, imageUrl) => {
    const raw = String(catalogTitle ?? "").trim() || pickValuableUSCoin();
    const simplified = (await simplifyCoinTitle(raw)) ?? raw;
    const title = simplified.trim() || pickValuableUSCoin();
    const priceUpdates =
      !slot.spentPrice && !slot.soldPrice
        ? (await coinPrices(title)) ?? autoRandomPrices()
        : {};
    const soldPrice = priceUpdates.soldPrice ?? slot.soldPrice;
    return {
      ...(imageUrl ? { imageUrl } : {}),
      ...priceUpdates,
      itemName: title,
      matchItems: autoSoldListings(title, soldPrice),
    };
  };

  // ΓöÇΓöÇ Auto-generate 2 slightly-varied sold listing rows ΓöÇΓöÇ
  const autoSoldListings = (itemName, soldPrice) => {
    const PREFIXES = ["Pre-owned ", "Used ", "Vintage ", "Authentic "];
    const SUFFIXES = [" - Great Condition", " - Gently Used", " (Pre-loved)", " - Excellent"];
    const SOURCES  = ["eBay", "Poshmark", "Mercari", "Depop"];
    const price = parseFloat(soldPrice);
    const makeRow = (seed) => ({
      title:   `${PREFIXES[seed % PREFIXES.length]}${itemName}${SUFFIXES[(seed + 1) % SUFFIXES.length]}`,
      source:  SOURCES[seed % SOURCES.length],
      price:   isNaN(price) ? "" : String(Math.round(price * (seed % 2 === 0 ? 0.88 : 1.08))),
      inStock: false,
    });
    return [makeRow(0), makeRow(1)];
  };

  // ΓöÇΓöÇ Per-slot: auto-title button ΓöÇΓöÇ
  const handleAutoTitle = async (index) => {
    const slot = config.slots[index];
    if (!slot.imageUrl) { setAiErrors((p) => ({ ...p, [`title_${index}`]: "Upload an image first." })); return; }
    setAiErrors((p) => ({ ...p, [`title_${index}`]: null }));
    setGeneratingSlot(`title_${index}`);
    if (isLabely) {
      const ly = await fillLabelyFromImage(slot.imageUrl, { includeShelfIntro: index === 0 && isLabelyScanTourFormat(config) });
      if (ly?.name) {
        updateSlot(index, {
          itemName: ly.name,
          labelyBrand: ly.brand ?? "",
          ...badLabelyPatch(ly.score),
          labelyAnalysis: ly.analysis ?? "",
          labelyAnalysisTitle: ly.analysisTitle ?? "Labely's Analysis",
          labelyLegalNote: ly.labelyLegalNote?.trim() || "No lawsuits found.",
          ...(ly.shelfIntroDataUrl ? { labelyShelfImageUrl: ly.shelfIntroDataUrl } : {}),
        });
      } else {
        setAiErrors((p) => ({ ...p, [`title_${index}`]: "Could not analyze packaging." }));
      }
    } else if (isValcoin) {
      const existing = (slot.itemName ?? "").trim();
      const title =
        existing && !/^item\s+\d+$/i.test(existing) ? existing : pickValuableUSCoin();
      const priceUpdates = (await coinPrices(title)) ?? autoRandomPrices();
      updateSlot(index, {
        itemName: title,
        ...priceUpdates,
        matchItems: autoSoldListings(title, priceUpdates.soldPrice),
      });
    } else {
      const grail = await autoTitleFromImage(slot.imageUrl);
      if (grail?.title) {
        const resolvedPrice = grail.price ?? slot.soldPrice;
        updateSlot(index, {
          itemName: grail.title,
          ...(grail.price ? { soldPrice: grail.price } : {}),
          matchItems: autoSoldListings(grail.title, resolvedPrice),
        });
      } else {
        setAiErrors((p) => ({ ...p, [`title_${index}`]: "Could not identify item." }));
      }
    }
    setGeneratingSlot(null);
  };

  const handleGenerateAll = async () => {
    const generationJitterSeed = (Math.random() * 0xffff) | 0;
    setGeneratingSlot("all");
    setAiErrors({});
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    if (isLabely) await beginLabelyBraveGenerateRun();
    try {
      setConfig((prev) => ({ ...prev, jitterSeed: generationJitterSeed }));

      // iMessage mom / Labely single-slide only use slot 0
      const isMomFmt = (config.outputFormat ?? "standard") === "imessageMom";
      const allSlots = isMomFmt
        ? [config.slots[0]]
        : isLabelyScanTourFormat(config)
          ? config.slots.slice(0, scanTourSlotCount(config))
          : isLabelySingleSlideFormat(config)
            ? [config.slots[0]]
            : config.slots;

      // All slots are active if brand items list has items; otherwise filter by slot prompt
      const activeSlots = allSlots
        .map((s, i) => ({ slot: s, i: isMomFmt ? 0 : i }))
        .filter(({ slot, i }) =>
          isLabely
            ? config.labelyAiProducts
              ? true
              : Boolean((batchImageDataUrls[i] ?? slot.imageUrl)?.trim())
            : isValcoin
              ? true
              : brandItems.length > 0 || slot.prompt?.trim()
        );

      if (activeSlots.length === 0) {
        alert(
          isLabely
            ? config.labelyAiProducts
              ? "Could not determine slots to generate."
              : "Upload at least one slot photo under Product photos, then run Generate again."
            : isValcoin
              ? "Could not determine slots to generate."
              : "Add items to the Brand Items List or add a prompt to at least one slot."
        );
        return;
      }

      const total = activeSlots.length;
      const slotsDone = new Set();
      cancelGenRef.current = false;

      // Deduplicate brand items first, then shuffle so every slot gets a unique brand
      const uniqueBrands = [...new Set(brandItems)];
      const shuffledUnique = uniqueBrands.length > 0
        ? [...uniqueBrands].sort(() => Math.random() - 0.5)
        : [];
      // If more slots than unique brands, extend with a re-shuffled copy (no back-to-back repeats)
      while (shuffledUnique.length > 0 && shuffledUnique.length < activeSlots.length) {
        const extra = [...uniqueBrands].sort(() => Math.random() - 0.5);
        shuffledUnique.push(...extra);
      }

      let failedCount = 0;
      /** Labely Brave URLs already picked in this slideshow (sync exclude for deferred slot writes). */
      const currentSlideshowBraveUrls = [];
      const currentSlideshowBraveHashes = [];
      /** Labely ├ù3 AI + scan tour: merge all slot patches in one commit (avoids lost updates mid-loop). */
      const tourAiDeferredWrites = [];
      const valcoinUsedSourceUrls = isValcoin ? new Set() : null;
      setGenAllProgress({ total, done: 0, current: activeSlots[0].i, phase: `Starting ${total} image${total > 1 ? "s" : ""}ΓÇª`, slotsDone });

      for (let idx = 0; idx < activeSlots.length; idx++) {
        await waitWhilePaused();
        if (cancelGenRef.current) {
          if (tourAiDeferredWrites.length > 0) {
            flushSync(() => {
              setConfig((prev) => ({
                ...prev,
                slots: prev.slots.map((slot, idx) => {
                  const hit = tourAiDeferredWrites.find((x) => x.i === idx);
                  return hit ? { ...slot, ...hit.patch } : slot;
                }),
              }));
            });
            flushSync(() => setCurrentSlide(0));
          }
          setGenAllProgress((p) => (p ? { ...p, phase: "Stopped." } : null));
          setTimeout(() => setGenAllProgress(null), 2000);
          return;
        }
        const { i } = activeSlots[idx];
        const prompt = config.slots[i].prompt || globalPrompt;
        const stepLabel = `${idx + 1} of ${total}`;

        // Each slot gets its own unique brand item from the deduplicated shuffled list
        const brandItem = shuffledUnique.length > 0 ? shuffledUnique[idx] : null;
        const brandLabel = brandItem ? ` ΓÇö "${brandItem}"` : "";

        const hint = isValcoin ? pickValuableUSCoin() : brandItem;
        const p = hint ? `${prompt}\n\nSpecific item to depict: ${hint}.` : prompt;

        if (isLabely) {
          setGenAllProgress({
            total,
            done: slotsDone.size,
            current: i,
            phase: config.labelyAiProducts
              ? `Labely product ${stepLabel}${brandLabel}ΓÇª`
              : `Labely analysis ${stepLabel}ΓÇª`,
            slotsDone: new Set(slotsDone),
          });
          let ly;
          const includeShelfIntro = i === 0 && isLabelyScanTourFormat(config);
          if (config.labelyAiProducts) {
            const useSelfieForSlot = labelyUseSelfieImage && i === 0;
            ly = await fillLabelyFromAi(brandItem, i, {
              includeShelfIntro,
              useSelfieImage: useSelfieForSlot,
              braveExcludeExtraUrls: currentSlideshowBraveUrls,
              braveExcludeExtraHashes: currentSlideshowBraveHashes,
            });
          } else {
            const slot = config.slots[i];
            const url = (batchImageDataUrls[i] ?? slot.imageUrl)?.trim();
            ly = await fillLabelyFromImage(url, { includeShelfIntro });
          }
          if (ly?.name) {
            if (ly.labelyDbImageUrl) currentSlideshowBraveUrls.push(ly.labelyDbImageUrl);
            if (ly.labelyBraveContentHash) currentSlideshowBraveHashes.push(ly.labelyBraveContentHash);
            const useSelfieForSlot = config.labelyAiProducts && labelyUseSelfieImage && i === 0;
            if (useSelfieForSlot && includeShelfIntro && !ly.shelfIntroDataUrl) {
              failedCount++;
              setGenAllProgress({
                total,
                done: slotsDone.size,
                current: i,
                phase: `Slot ${stepLabel} failed: Pilates selfie intro was not generated. Try again.`,
                slotsDone: new Set(slotsDone),
              });
              await new Promise((r) => setTimeout(r, 2500));
              continue;
            }
            const shelfIntroUrl = await resolveLabelyShelfIntroUrl(ly, {
              includeShelfIntro,
              useSelfieForSlot,
            });
            const patch = {
              itemName: ly.name,
              labelyBrand: ly.brand ?? "",
              ...badLabelyPatch(ly.score),
              labelyAnalysis: ly.analysis ?? "",
              labelyAnalysisTitle: ly.analysisTitle ?? "Labely's Analysis",
              labelyLegalNote: ly.labelyLegalNote?.trim() || "No lawsuits found.",
              ...(config.labelyAiProducts && ly.imageDataUrl ? labelyProductImagePatch(ly) : {}),
              ...(shelfIntroUrl ? { labelyShelfImageUrl: shelfIntroUrl } : {}),
            };
            const batchTourAi = config.labelyAiProducts && isLabelyScanTourFormat(config);
            if (batchTourAi) {
              tourAiDeferredWrites.push({ i, patch });
            } else {
              flushSync(() => {
                updateSlot(i, patch);
                setConfig((prev) => ({ ...prev, jitterSeed: generationJitterSeed }));
              });
            }
            slotsDone.add(i);
            setGenAllProgress({ total, done: slotsDone.size, current: i, phase: `Slot ${stepLabel} complete`, slotsDone: new Set(slotsDone) });
          } else {
            failedCount++;
            const errMsg = aiErrors[i] || "analysis failed";
            setGenAllProgress({ total, done: slotsDone.size, current: i, phase: `Slot ${stepLabel} failed: ${errMsg}`, slotsDone: new Set(slotsDone) });
            await new Promise((r) => setTimeout(r, 2500));
          }
        } else {
          setGenAllProgress({
            total,
            done: slotsDone.size,
            current: i,
            phase: isValcoin
              ? `Random coin photo ${stepLabel}${brandLabel}ΓÇª`
              : `Generating image ${stepLabel}${brandLabel}ΓÇª`,
            slotsDone: new Set(slotsDone),
          });

          if (isValcoin) {
            const numista = await fetchValcoinNumistaSlot(valcoinUsedSourceUrls);
            if (numista) {
              const slot = config.slots[i];
              const catalogTitle = numista.title?.trim() || hint || pickValuableUSCoin();
              const patch = await buildValcoinSlotPatch(catalogTitle, slot, numista.dataUrl);
              updateSlot(i, patch);
              if (numista.sourceUrl) valcoinUsedSourceUrls.add(numista.sourceUrl);
              slotsDone.add(i);
              setGenAllProgress({ total, done: slotsDone.size, current: i, phase: `Slot ${stepLabel} complete`, slotsDone: new Set(slotsDone) });
            } else {
              failedCount++;
              setAiErrors((p) => ({ ...p, [i]: "Could not load a Wikimedia Commons coin photo." }));
              setGenAllProgress({ total, done: slotsDone.size, current: i, phase: `Slot ${stepLabel} failed: Wikimedia`, slotsDone: new Set(slotsDone) });
              await new Promise((r) => setTimeout(r, 2500));
            }
          } else {
          const url = await generateImage(i, p, hint);

          if (url) {
            const slot = config.slots[i];
            const priceUpdates = (!slot.spentPrice && !slot.soldPrice) ? autoRandomPrices() : {};
            updateSlot(i, { imageUrl: url, ...priceUpdates });

            setGenAllProgress({ total, done: slotsDone.size, current: i, phase: `Analyzing item ${stepLabel}ΓÇª`, slotsDone: new Set(slotsDone) });
            const grail = await autoTitleFromImage(url);
            if (grail?.title) {
              const resolvedPrice = grail.price ?? priceUpdates.soldPrice ?? slot.soldPrice;
              updateSlot(i, {
                itemName: grail.title,
                ...(grail.price ? { soldPrice: grail.price } : {}),
                matchItems: autoSoldListings(grail.title, resolvedPrice),
              });
            }

            slotsDone.add(i);
            setGenAllProgress({ total, done: slotsDone.size, current: i, phase: `Item ${stepLabel} complete`, slotsDone: new Set(slotsDone) });
          } else {
            failedCount++;
            const errMsg = aiErrors[i] || "unknown error";
            setGenAllProgress({ total, done: slotsDone.size, current: i, phase: `Slot ${stepLabel} failed: ${errMsg}`, slotsDone: new Set(slotsDone) });
            await new Promise((r) => setTimeout(r, 2500));
          }
          }
        }
      }

      if (tourAiDeferredWrites.length > 0) {
        flushSync(() => {
          setConfig((prev) => ({
            ...prev,
            jitterSeed: generationJitterSeed,
            slots: prev.slots.map((slot, idx) => {
              const hit = tourAiDeferredWrites.find((x) => x.i === idx);
              return hit ? { ...slot, ...hit.patch } : slot;
            }),
          }));
        });
        flushSync(() => setCurrentSlide(0));
      }

      const doneCount = slotsDone.size;
      const missingPackShots =
        config.labelyAiProducts &&
        tourAiDeferredWrites.length > 0 &&
        tourAiDeferredWrites.some(({ patch }) => !String(patch.imageUrl || "").trim());
      const summary = failedCount > 0
        ? `Done ΓÇö ${doneCount} succeeded, ${failedCount} failed`
        : missingPackShots
          ? "All done ΓÇö text & scores saved, but no product photos. Check BRAVE_SEARCH_API_KEY in .env.local and your food list."
        : "All done! Γ£ô";
      setGenAllProgress((p) => p ? { ...p, phase: summary, done: doneCount } : null);
      setTimeout(() => setGenAllProgress(null), missingPackShots ? 12000 : 4000);
    } catch (err) {
      console.error("Generate 1 slideshow failed:", err);
      setGenAllProgress((p) => p ? { ...p, phase: "Generation failed ΓÇö check console for details." } : null);
      setTimeout(() => setGenAllProgress(null), 5000);
    } finally {
      setGeneratingSlot(null);
      abortRef.current = null;
    }
  };

  // ΓöÇΓöÇ Batch generation: produce N complete slideshows sequentially ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  /** Data URLs in play order: show 1 slots 1ΓÇª6 (or 1 for iMessage mom), then show 2, ΓÇª Row count = length. */
  const [bulkDropHover, setBulkDropHover] = useState(false);
  const bulkFileInputRef = useRef(null);

  const batchSlotCount =
    (config.outputFormat ?? "standard") === "imessageMom"
      ? 1
      : isLabelyScanTourFormat(config)
        ? scanTourSlotCount(config)
        : isLabelySingleSlideFormat(config)
          ? 1
          : 6;
  const effectiveNumSlideshows = isValcoinIphonePackBatchMode
    ? VALCOIN_IPHONE_PACK_TOTAL
    : numSlideshows;
  const batchImagesNeeded = effectiveNumSlideshows * batchSlotCount;

  const hasWorkspacePhotos = useMemo(
    () =>
      batchImageDataUrls.some(Boolean) ||
      config.slots.some((s) => Boolean(s.imageUrl?.trim())),
    [batchImageDataUrls, config.slots]
  );

  const clearAllWorkspacePhotos = useCallback(() => {
    if (labelyUploadsLocked || generatingSlot !== null) return;
    setBatchImageDataUrls(Array.from({ length: batchImagesNeeded }, () => null));
    setConfig((prev) => ({
      ...prev,
      slots: prev.slots.map((s, i) =>
        isLabely ? labelySlotAfterImageSwap(s, null, i) : { ...s, imageUrl: null }
      ),
    }));
    setAiErrors({});
  }, [batchImagesNeeded, isLabely, labelyUploadsLocked, generatingSlot, setConfig, setBatchImageDataUrls]);

  useEffect(() => {
    const need = effectiveNumSlideshows * batchSlotCount;
    if (need <= 0) return;
    setBatchImageDataUrls((prev) => {
      if (prev.length === need) return prev;
      return Array.from({ length: need }, (_, i) => (i < prev.length ? prev[i] ?? null : null));
    });
  }, [effectiveNumSlideshows, batchSlotCount, setBatchImageDataUrls]);

  const reorderBatchRows = (fromIndex, toIndex) => {
    if (fromIndex === toIndex) return;
    if (generatingSlot !== null) return;
    setBatchImageDataUrls((prev) => {
      if (fromIndex < 0 || toIndex < 0 || fromIndex >= prev.length || toIndex >= prev.length) return prev;
      const next = [...prev];
      const [moved] = next.splice(fromIndex, 1);
      next.splice(toIndex, 0, moved);
      setConfig((p) => ({
        ...p,
        slots: p.slots.map((s, i) => {
          if (!(i < 6 && i < next.length)) return s;
          const url = next[i] ?? null;
          return isLabely && !labelyUploadsLocked
            ? labelySlotAfterImageSwap(s, url, i)
            : { ...s, imageUrl: url };
        }),
      }));
      if (isLabely && !labelyUploadsLocked) {
        void runLabelyVisionForPreviewSlots(next);
      }
      return next;
    });
  };

  /**
   * @param {File[]} fileList
   * @param {{ replace?: boolean }} opts replace: fill batch slots from decoded images placed randomly across slideshows (square drop); false = merge into existing rows (file picker).
   */
  const handleBulkImageFiles = async (fileList, opts = { replace: true }) => {
    if (generatingSlot !== null) return;
    if (isLabely && config.labelyAiProducts) return;
    const imageFiles = [...fileList].filter((f) => isLikelyRasterImageFile(f));
    if (!imageFiles.length) return;
    const showsBefore = numSlideshows;
    const perShow = batchSlotCount;
    try {
      const results = await Promise.all(imageFiles.map((f) => tryFileToDisplayableDataUrl(f)));
      const urls = results.map((r) => (r.ok ? r.dataUrl : null));
      const failedNames = results
        .map((r, i) => (!r.ok ? imageFiles[i]?.name || `#${i + 1}` : null))
        .filter(Boolean);
      if (!urls.some(Boolean)) {
        alert(
          `Could not read any images.${failedNames.length ? `\n\n(${failedNames.slice(0, 6).join(", ")})` : ""}`
        );
        return;
      }
      if (failedNames.length) {
        console.warn("[bulk] skipped unreadable files:", failedNames);
      }
      const minShows = Math.max(1, Math.ceil(imageFiles.length / perShow));
      if (opts.replace) {
        const newShows = Math.max(showsBefore, minShows);
        const need = newShows * perShow;
        const goodUrls = urls.filter(Boolean);
        const shuffledUrls = shuffleArray(goodUrls);
        const slotOrder = shuffleArray(Array.from({ length: need }, (_, i) => i));
        const nextBatch = Array.from({ length: need }, () => null);
        for (let i = 0; i < shuffledUrls.length; i++) {
          nextBatch[slotOrder[i]] = shuffledUrls[i];
        }
        setNumSlideshows(newShows);
        setBatchImageDataUrls(nextBatch);
        setConfig((prev) => ({
          ...prev,
          slots: prev.slots.map((s, i) => {
            if (!(i < 6 && i < nextBatch.length)) return s;
            const url = nextBatch[i] ?? null;
            return isLabely && !config.labelyAiProducts
              ? labelySlotAfterImageSwap(s, url, i)
              : { ...s, imageUrl: url };
          }),
        }));

        if (isLabely && !config.labelyAiProducts) {
          void runLabelyVisionForPreviewSlots(nextBatch);
        }
      } else {
        const need = showsBefore * perShow;
        setBatchImageDataUrls((prev) =>
          Array.from({ length: need }, (_, i) => urls[i] ?? prev[i] ?? null)
        );
      }
    } catch {
      alert("Could not read one or more images.");
    }
  };

  // Generate one complete slideshow into a local slots array, save via callback.
  const generateOneSlideshow = async (showIndex, totalShows, options = {}) => {
    const isMomFmt = (config.outputFormat ?? "standard") === "imessageMom";
    const sourceBrandItems = Array.isArray(options.brandItemsOverride) && options.brandItemsOverride.length > 0
      ? options.brandItemsOverride
      : brandItems;
    const scanSlotOverride = Math.floor(Number(options.scanSlotCountOverride));
    const labelyScanSlotsForShow =
      isLabely && isLabelyScanTourFormat(config) && Number.isFinite(scanSlotOverride) && scanSlotOverride > 0
        ? scanSlotOverride
        : scanTourSlotCount(config);
    const slotCount = isMomFmt
      ? 1
      : isLabelyScanTourFormat(config)
        ? labelyScanSlotsForShow
        : isLabelySingleSlideFormat(config)
          ? 1
          : 6;
    const base = showIndex * slotCount;
    const useBatchUploads = !isValcoin && !(isLabely && config.labelyAiProducts);
    const slice =
      useBatchUploads && batchImageDataUrls.length > base
        ? Array.from({ length: slotCount }, (_, si) =>
            base + si < batchImageDataUrls.length ? batchImageDataUrls[base + si] ?? null : null
          )
        : null;

    const uniqueBrands = [...new Set(sourceBrandItems)];
    const shuffled = [...uniqueBrands].sort(() => Math.random() - 0.5);
    while (shuffled.length > 0 && shuffled.length < slotCount)
      shuffled.push(...[...uniqueBrands].sort(() => Math.random() - 0.5));
    const useOrderedBatchItems = Array.isArray(options.brandItemsOverride) && options.brandItemsOverride.length > 0;
    const deferBraveUsedPersist = useOrderedBatchItems || isFarmAutomation;

    const foodDbMatchesOverride =
      options.foodDbMatchesOverride && typeof options.foodDbMatchesOverride === "object"
        ? options.foodDbMatchesOverride
        : null;
    const localSlots = Array.from({ length: Math.max(6, slotCount) }, (_, i) => freshSlot(i));
    const showJitterSeed = (Math.random() * 0xffff) | 0;
    const usedFoodDbUrls = labelyBraveReusePhotos
      ? new Set(localSlots.map((s) => s?.labelyDbImageUrl).filter(Boolean))
      : new Set([
          ...sessionBraveReservedRef.current,
          ...localSlots.map((s) => s?.labelyDbImageUrl).filter(Boolean),
        ]);

    if (isLabely) {
      if (config.labelyUseBraveImages !== false && !useOrderedBatchItems) beginLabelySlideshowBraveRun();
      if (config.labelyAiProducts) {
        for (let si = 0; si < slotCount; si++) {
          await waitWhilePaused();
          if (cancelGenRef.current) break;
          const brandItem = useOrderedBatchItems
            ? (sourceBrandItems[si] ?? null)
            : (shuffled.length > 0 ? shuffled[si] : null);
          setGenAllProgress({
            total: slotCount,
            done: si,
            current: si,
            phase: `Show ${showIndex + 1}/${totalShows} ┬╖ Product ${si + 1}/${slotCount}${brandItem ? ` ΓÇö "${brandItem}"` : ""}ΓÇª`,
            slotsDone: new Set(Array.from({ length: si }, (_, k) => k)),
          });
          const includeShelfIntro = si === 0 && isLabelyScanTourFormat(config);
          const useSelfieForSlot = labelyUseSelfieImage && si === 0;
          const extraBraveUrls = labelyBraveReusePhotos
            ? []
            : localSlots.map((s) => s?.labelyDbImageUrl).filter(Boolean);
          const urlExcludeForPick = labelyBraveReusePhotos ? new Set() : usedFoodDbUrls;
          const cachedPreset = labelyBraveReusePhotos
            ? productBraveUrlCacheRef.current.get(foodDbKeyFor(brandItem))
            : "";
          const presetCandidates = foodDbMatchesOverride
            ? [
                ...(cachedPreset ? [cachedPreset] : []),
                ...pickFoodDbBraveCandidateUrls(foodDbMatchesOverride, brandItem, urlExcludeForPick),
              ].filter((u, i, arr) => u && arr.indexOf(u) === i)
            : cachedPreset
              ? [cachedPreset]
              : [];
          const fillOpts = {
            includeShelfIntro,
            useSelfieImage: useSelfieForSlot,
            allowBraveReuse: labelyBraveReusePhotos,
            ...(labelyBraveReusePhotos ? {} : { braveExcludeExtraUrls: extraBraveUrls }),
            deferBraveUsedPersist,
          };
          let lyResolved = null;
          for (const presetBraveImageUrl of presetCandidates) {
            lyResolved = await fillLabelyFromAi(brandItem, si, {
              ...fillOpts,
              presetBraveImageUrl,
            });
            if (lyResolved?.name && lyResolved?.imageDataUrl) break;
          }
          if (!lyResolved?.name || !lyResolved?.imageDataUrl) {
            lyResolved = await fillLabelyFromAi(brandItem, si, fillOpts);
          }
          if (labelyBraveReusePhotos && lyResolved?.labelyDbImageUrl && brandItem) {
            productBraveUrlCacheRef.current.set(
              foodDbKeyFor(brandItem),
              lyResolved.labelyDbImageUrl,
            );
          } else if (lyResolved?.labelyDbImageUrl) {
            usedFoodDbUrls.add(lyResolved.labelyDbImageUrl);
          }
          if (lyResolved?.name) {
            const shelfIntroUrl = await resolveLabelyShelfIntroUrl(lyResolved, {
              includeShelfIntro,
              useSelfieForSlot,
            });
            localSlots[si] = {
              ...localSlots[si],
              itemName: lyResolved.name,
              labelyBrand: lyResolved.brand ?? "",
              ...badLabelyPatch(lyResolved.score),
              labelyAnalysis: lyResolved.analysis ?? "",
              labelyAnalysisTitle: lyResolved.analysisTitle ?? "Labely's Analysis",
              labelyLegalNote: lyResolved.labelyLegalNote?.trim() || "No lawsuits found.",
              ...(lyResolved.imageDataUrl ? labelyProductImagePatch(lyResolved) : {}),
              ...(shelfIntroUrl ? { labelyShelfImageUrl: shelfIntroUrl } : {}),
            };
          }
          updateConfig("slots", [...localSlots]);
        }
      } else {
      for (let si = 0; si < slotCount; si++) {
        await waitWhilePaused();
        if (cancelGenRef.current) break;
        const pre = slice?.[si] ?? null;
        setGenAllProgress({
          total: slotCount,
          done: si,
          current: si,
          phase: `Show ${showIndex + 1}/${totalShows} ┬╖ Photo ${si + 1}/${slotCount}${pre ? "" : " (skipped ΓÇö no queued image)"}ΓÇª`,
          slotsDone: new Set(Array.from({ length: si }, (_, k) => k)),
        });
        if (!pre) continue;
        localSlots[si] = { ...localSlots[si], imageUrl: pre };
        const includeShelfIntro = si === 0 && isLabelyScanTourFormat(config);
        const ly = await fillLabelyFromImage(pre, { includeShelfIntro });
        if (ly?.name) {
          const shelfIntroUrl = ly.shelfIntroDataUrl || (includeShelfIntro
            ? await generateLabelyShelfIntroImage(ly.name, ly.brand ?? "")
            : null);
          localSlots[si] = {
            ...localSlots[si],
            itemName: ly.name,
            labelyBrand: ly.brand ?? "",
            ...badLabelyPatch(ly.score),
            labelyAnalysis: ly.analysis ?? "",
            labelyAnalysisTitle: ly.analysisTitle ?? "Labely's Analysis",
            labelyLegalNote: ly.labelyLegalNote?.trim() || "No lawsuits found.",
            ...(shelfIntroUrl ? { labelyShelfImageUrl: shelfIntroUrl } : {}),
          };
        }
        updateConfig("slots", [...localSlots]);
      }
      }
      const hasAny = localSlots.some((s) => s.itemName?.trim() || s.imageUrl?.trim());
      if (!hasAny) return null;
      flushSync(() => {
        setConfig((prev) => ({
          ...prev,
          slots: [...localSlots],
          captionText: "",
          jitterSeed: showJitterSeed,
          ...(isLabelyScanTourFormat(config) ? { labelyScanSlotCount: slotCount } : {}),
        }));
      });
      await waitForPreviewPaint();
      const previewScreenshot = await captureLivePreviewThumbnail();
      const savedShow = {
        slots: [...localSlots],
        captionText: "",
        previewScreenshot,
        outputFormat: config.outputFormat,
        appId: config.appId,
        jitterSeed: showJitterSeed,
        ...(isLabelyScanTourFormat(config) ? { labelyScanSlotCount: slotCount } : {}),
        ...(config.labelyOutroText ? { labelyOutroText: config.labelyOutroText } : {}),
        ...(options.batchMeta || {}),
      };
      onSlideshowSaved?.(savedShow);
      return savedShow;
    }

    if (isValcoin && isLabelyScanTourFormat(config)) {
      const usedSourceUrls = new Set();
      for (let si = 0; si < slotCount; si++) {
        await waitWhilePaused();
        if (cancelGenRef.current) break;
        setGenAllProgress({
          total: slotCount,
          done: si,
          current: si,
          phase: `Show ${showIndex + 1}/${totalShows} ┬╖ Random US coin photo ${si + 1}/${slotCount}ΓÇª`,
          slotsDone: new Set(Array.from({ length: si }, (_, k) => k)),
        });
        let url = null;
        let coinTitle = "";
        const numista = await fetchValcoinNumistaSlot(usedSourceUrls);
        if (numista) {
          url = numista.dataUrl;
          coinTitle = numista.title || coinTitle;
          if (numista.sourceUrl) usedSourceUrls.add(numista.sourceUrl);
        }
        if (url) {
          const title = coinTitle.trim() || pickValuableUSCoin();
          const patch = await buildValcoinSlotPatch(title, localSlots[si], url);
          let nextSlot = { ...localSlots[si], ...patch };
          if (si === 0) nextSlot.labelyShelfImageUrl = url;
          localSlots[si] = nextSlot;
        }
        updateConfig("slots", [...localSlots]);
      }
      const hasAny = localSlots.slice(0, slotCount).some((s) => s.imageUrl?.trim());
      if (!hasAny) return null;
      flushSync(() => {
        setConfig((prev) => ({
          ...prev,
          slots: [...localSlots],
          captionText: "",
          jitterSeed: showJitterSeed,
        }));
      });
      await waitForPreviewPaint();
      const previewScreenshot = await captureLivePreviewThumbnail();
      const savedShow = {
        slots: [...localSlots],
        captionText: "",
        previewScreenshot,
        outputFormat: config.outputFormat,
        appId: config.appId,
        jitterSeed: showJitterSeed,
        ...(config.labelyOutroText ? { labelyOutroText: config.labelyOutroText } : {}),
        ...(options.batchMeta || {}),
      };
      onSlideshowSaved?.(savedShow);
      return savedShow;
    }

    const valcoinUsedSourceUrls = isValcoin ? new Set() : null;
    for (let si = 0; si < slotCount; si++) {
      await waitWhilePaused();
      if (cancelGenRef.current) break;
      const brandItem = shuffled.length > 0 ? shuffled[si] : null;
      const pre = useBatchUploads ? (slice?.[si] ?? null) : null;
      setGenAllProgress({
        total: slotCount,
        done: si,
        current: si,
        phase: pre
          ? `Show ${showIndex + 1}/${totalShows} ┬╖ Upload ${si + 1}/${slotCount}ΓÇª`
          : isValcoin
            ? `Show ${showIndex + 1}/${totalShows} ┬╖ Random coin photo ${si + 1}/${slotCount}ΓÇª`
            : `Show ${showIndex + 1}/${totalShows} ┬╖ Image ${si + 1}/${slotCount}${brandItem ? ` ΓÇö "${brandItem}"` : ""}ΓÇª`,
        slotsDone: new Set(Array.from({ length: si }, (_, k) => k)),
      });
      const hintGen = isValcoin ? (brandItem ?? pickValuableUSCoin()) : brandItem;
      const p = hintGen ? `${globalPrompt}\n\nSpecific item to depict: ${hintGen}.` : globalPrompt;
      let url = pre;
      let catalogTitle = "";
      if (!url && isValcoin) {
        const numista = await fetchValcoinNumistaSlot(valcoinUsedSourceUrls);
        if (numista) {
          url = numista.dataUrl;
          catalogTitle = numista.title?.trim() || "";
          if (numista.sourceUrl) valcoinUsedSourceUrls.add(numista.sourceUrl);
        }
      } else if (!url) {
        url = await generateImage(si, p, hintGen);
      }
      if (url) {
        if (isValcoin) {
          const title = catalogTitle.trim() || hintGen || pickValuableUSCoin();
          const patch = await buildValcoinSlotPatch(title, localSlots[si], url);
          localSlots[si] = { ...localSlots[si], ...patch };
        } else {
          const prices = pre ? autoRandomPrices() : autoRandomPrices();
          localSlots[si] = {
            ...localSlots[si],
            imageUrl: url,
            ...prices,
          };
          setGenAllProgress({
            total: slotCount,
            done: si,
            current: si,
            phase: `Show ${showIndex + 1}/${totalShows} ┬╖ Analyzing item ${si + 1}/${slotCount}ΓÇª`,
            slotsDone: new Set(Array.from({ length: si }, (_, k) => k)),
          });
          const grail = await autoTitleFromImage(url);
          if (grail?.title) {
            const rp = grail.price ?? prices.soldPrice;
            localSlots[si] = {
              ...localSlots[si],
              itemName: grail.title,
              ...(grail.price ? { soldPrice: grail.price } : {}),
              matchItems: autoSoldListings(grail.title, rp),
            };
          }
        }
        if ((config.outputFormat ?? "standard") === "imessageMom") {
          const slotNow = localSlots[si];
          const thread = await generateImessageThread(slotNow.itemName, slotNow.soldPrice);
          if (thread) localSlots[si] = { ...localSlots[si], imessageThread: thread };
        }
      }
      updateConfig("slots", [...localSlots]);
    }
    updateConfig("jitterSeed", showJitterSeed);
    await waitForPreviewPaint();
    const previewScreenshot = await captureLivePreviewThumbnail();
    const savedShow = {
      slots: [...localSlots],
      captionText: "",
      previewScreenshot,
      outputFormat: config.outputFormat,
      appId: config.appId,
      jitterSeed: showJitterSeed,
      ...(config.labelyOutroText ? { labelyOutroText: config.labelyOutroText } : {}),
      ...(options.batchMeta || {}),
    };
    onSlideshowSaved?.(savedShow);
    return savedShow;
  };

  const handleGenerateBatch = async () => {
    if (isFarmAutomation && farmUpload?.jobId) {
      markFarmJobAutoRunStarted(farmUpload.jobId);
    }
    if (isLabelyFoodDbBatchMode) {
      const scanSlots = scanTourSlotCount(config);
      let plans = labelyFoodDbBatchRows
        .map((b, idx) => ({
          batchNumber: idx + 1,
          batchName: String(b.name || "").trim(),
          items: String(b.itemsRaw || "")
            .split("\n")
            .map((x) => x.trim())
            .filter(Boolean)
            .slice(0, scanSlots),
          slideshowCount: Math.max(0, Math.min(200, Number(b.slideshowCount) || 0)),
          foodDbMatches: b.foodDbMatches && typeof b.foodDbMatches === "object" ? b.foodDbMatches : {},
        }))
        .filter((b) => b.slideshowCount > 0 && b.items.length > 0);
      if (isFarmAutomation && numSlideshows > 0) {
        plans = plans.slice(0, numSlideshows);
      }
      if (labelyUseBraveImages && plans.length > 0) {
        setGenAllProgress({
          phase: labelyBraveReusePhotos
            ? "Resolving Brave photos (once per product name)ΓÇª"
            : "Resolving unhealthy foods from BraveΓÇª",
          done: 0,
        });
        const sharedMatches = {};
        for (const plan of plans) {
          const existing = plan.foodDbMatches && typeof plan.foodDbMatches === "object"
            ? plan.foodDbMatches
            : {};
          Object.assign(sharedMatches, existing);
        }
        const allUniqueItems = [
          ...new Set(plans.flatMap((p) => p.items).map((x) => String(x || "").trim()).filter(Boolean)),
        ];
        const missing = allUniqueItems.filter((item) => {
          const cached = foodDbSuggestionCacheRef.current.get(foodDbKeyFor(item));
          if (cached?.candidateDetails?.some((d) => String(d?.imageUrl || "").trim())) {
            sharedMatches[item] = cached;
            return false;
          }
          const row = sharedMatches[item];
          const details = Array.isArray(row?.candidateDetails) ? row.candidateDetails : [];
          return !details.some((d) => String(d?.imageUrl || "").trim());
        });
        for (let i = 0; i < missing.length; i += 20) {
          const chunk = missing.slice(i, i + 20);
          if (!chunk.length) continue;
          try {
            const res = await fetch("/api/labely-food-suggestions", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ items: chunk, ...foodImageLookupBody() }),
            });
            const body = await res.json().catch(() => ({}));
            for (const row of Array.isArray(body.results) ? body.results : []) {
              if (row?.query) {
                sharedMatches[row.query] = row;
                foodDbSuggestionCacheRef.current.set(foodDbKeyFor(row.query), row);
              }
            }
            if (body?.braveUsage) dispatchBraveUsageUpdated(body.braveUsage);
          } catch (err) {
            console.error("Brave food resolve failed:", err);
          }
        }
        plans = plans.map((plan) => ({
          ...plan,
          foodDbMatches: { ...sharedMatches, ...(plan.foodDbMatches || {}) },
        }));
      }
      const totalShows = plans.reduce((sum, p) => sum + p.slideshowCount, 0);
      if (totalShows <= 0) {
        alert("Set at least one batch slideshow count above 0.");
        return;
      }
      if (plans.some((p) => p.items.length === 0)) {
        alert("Each batch with a non-zero slideshow count needs at least one food item.");
        return;
      }
      setGeneratingSlot("all");
      setAiErrors({});
      cancelGenRef.current = false;
      abortRef.current?.abort();
      abortRef.current = new AbortController();
      if (isLabely) await beginLabelyBraveGenerateRun();
      try {
        let globalShowIdx = 0;
        const generatedShows = [];
        for (const plan of plans) {
          for (let i = 0; i < plan.slideshowCount; i++) {
            await waitWhilePaused();
            if (cancelGenRef.current) break;
            const savedShow = await generateOneSlideshow(globalShowIdx, totalShows, {
              brandItemsOverride: plan.items,
              foodDbMatchesOverride: plan.foodDbMatches,
              scanSlotCountOverride: plan.items.length,
              batchMeta: {
                batchNumber: plan.batchNumber,
                batchSlideshowIndex: i + 1,
                batchFoodName: plan.foodGenre || plan.batchName || plan.items[0] || "food",
                phoneIndex: plan.phoneIndex,
                videoOnPhone: plan.videoOnPhone,
                foodGenre: plan.foodGenre,
                foodTypes: plan.foodTypes,
              },
            });
            if (savedShow) generatedShows.push(savedShow);
            globalShowIdx++;
          }
          if (cancelGenRef.current) break;
        }
        if (!cancelGenRef.current) {
          setGenAllProgress((p) => p
            ? {
                ...p,
                phase: isFarmAutomation
                  ? `Γ£ô ${generatedShows.length} saved. Uploading to farmΓÇª`
                  : `Γ£ô ${generatedShows.length} slideshow${generatedShows.length > 1 ? "s" : ""} saved. Auto-exporting iPhone ZIPsΓÇª`,
                done: 6,
              }
            : null
          );
          const restoreConfig = {
            ...config,
            slots: (config.slots ?? []).map((s) => ({ ...s })),
          };
          if (isFarmAutomation && generatedShows.length > 0) {
            await exportShowsToFarm(generatedShows, restoreConfig, { auto: true });
          } else {
            await exportIphoneMp4ZipPlans(generatedShows, restoreConfig, { auto: true, farmUpload });
          }
        } else {
          setGenAllProgress((p) => p
            ? { ...p, phase: `Stopped after ${generatedShows.length} slideshow${generatedShows.length === 1 ? "" : "s"}.`, done: 6 }
            : null
          );
        }
        setTimeout(() => setGenAllProgress(null), 4000);
      } catch (err) {
        console.error("Generate batch failed:", err);
        if (farmUpload?.jobId) markFarmJobFailed(err?.message || String(err), farmUpload.jobId);
        setGenAllProgress((p) => p ? { ...p, phase: "Batch failed ΓÇö check console for details." } : null);
        setTimeout(() => setGenAllProgress(null), 5000);
      } finally {
        setGeneratingSlot(null);
        abortRef.current = null;
      }
      return;
    }

    if (isValcoinIphonePackBatchMode) {
      const plans = Array.from({ length: LABELY_DB_BATCH_COUNT }, (_, idx) => ({
        batchNumber: idx + 1,
        batchName: `coins-batch-${idx + 1}`,
        slideshowCount: VALCOIN_IPHONE_SLIDESHOWS_PER_BATCH,
      }));
      const totalShows = VALCOIN_IPHONE_PACK_TOTAL;
      setGeneratingSlot("all");
      setAiErrors({});
      cancelGenRef.current = false;
      abortRef.current?.abort();
      abortRef.current = new AbortController();
      try {
        let globalShowIdx = 0;
        const generatedShows = [];
        for (const plan of plans) {
          for (let i = 0; i < plan.slideshowCount; i++) {
            await waitWhilePaused();
            if (cancelGenRef.current) break;
            const savedShow = await generateOneSlideshow(globalShowIdx, totalShows, {
              batchMeta: {
                batchNumber: plan.batchNumber,
                batchSlideshowIndex: i + 1,
                batchFoodName: plan.batchName,
              },
            });
            if (savedShow) generatedShows.push(savedShow);
            globalShowIdx++;
          }
          if (cancelGenRef.current) break;
        }
        if (!cancelGenRef.current) {
          setGenAllProgress((p) => p
            ? { ...p, phase: `Γ£ô ${generatedShows.length} slideshow${generatedShows.length > 1 ? "s" : ""} saved. Auto-exporting iPhone ZIPsΓÇª`, done: 6 }
            : null
          );
          const restoreConfig = {
            ...config,
            slots: (config.slots ?? []).map((s) => ({ ...s })),
          };
          await exportIphoneMp4ZipPlans(generatedShows, restoreConfig, { auto: true, farmUpload });
        } else {
          setGenAllProgress((p) => p
            ? { ...p, phase: `Stopped after ${generatedShows.length} slideshow${generatedShows.length === 1 ? "" : "s"}.`, done: 6 }
            : null
          );
        }
        setTimeout(() => setGenAllProgress(null), 4000);
      } catch (err) {
        console.error("Valcoin iPhone pack batch failed:", err);
        if (farmUpload?.jobId) markFarmJobFailed(err?.message || String(err), farmUpload.jobId);
        setGenAllProgress((p) => p ? { ...p, phase: "Batch failed ΓÇö check console for details." } : null);
        setTimeout(() => setGenAllProgress(null), 5000);
      } finally {
        setGeneratingSlot(null);
        abortRef.current = null;
      }
      return;
    }

    if (isLabely) {
      // AI products mode ΓÇö no manual uploads required
    } else if (!isValcoin && brandItems.length === 0 && !batchImageDataUrls.some(Boolean)) {
      alert("Add brand items for AI images, or queue batch uploads ΓÇö or both (uploads fill first, AI fills gaps).");
      return;
    }
    setGeneratingSlot("all");
    setAiErrors({});
    cancelGenRef.current = false;
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    if (isLabely) await beginLabelyBraveGenerateRun();
    try {
      let savedCount = 0;
      const generatedShows = [];
      for (let i = 0; i < numSlideshows; i++) {
        await waitWhilePaused();
        if (cancelGenRef.current) break;
        const saved = await generateOneSlideshow(i, numSlideshows);
        if (saved) {
          savedCount++;
          generatedShows.push(saved);
        }
      }
      if (isFarmAutomation && generatedShows.length > 0 && !cancelGenRef.current) {
        setGenAllProgress((p) => p
          ? { ...p, phase: `Γ£ô ${generatedShows.length} saved. Uploading to farmΓÇª`, done: 6 }
          : null
        );
        const restoreConfig = {
          ...config,
          slots: (config.slots ?? []).map((s) => ({ ...s })),
        };
        await exportShowsToFarm(generatedShows, restoreConfig, { auto: true });
      } else {
        const phase = cancelGenRef.current
          ? `Stopped ΓÇö ${savedCount} saved before cancel.`
          : savedCount === numSlideshows
            ? `Γ£ô ${savedCount} slideshow${savedCount > 1 ? "s" : ""} saved to gallery!`
            : savedCount > 0
              ? `ΓÜá Saved ${savedCount}/${numSlideshows}. Others had no coin photo loaded (Wikimedia API hiccup).`
              : "Γ£ù Nothing saved ΓÇö no coin photos loaded. Wikimedia Commons may be temporarily unavailable.";
        setGenAllProgress((p) => (p ? { ...p, phase, done: 6 } : null));
        setTimeout(() => setGenAllProgress(null), savedCount === numSlideshows ? 4000 : 8000);
      }
    } catch (err) {
      console.error("Generate batch failed:", err);
      if (farmUpload?.jobId) markFarmJobFailed(err?.message || String(err), farmUpload.jobId);
      setGenAllProgress((p) => p ? { ...p, phase: "Batch failed ΓÇö check console for details." } : null);
      setTimeout(() => setGenAllProgress(null), 5000);
    } finally {
      setGeneratingSlot(null);
      abortRef.current = null;
    }
  };

  useEffect(() => {
    if (!autoRunBatch || !farmUpload?.jobId) return;

    const jobId = farmUpload.jobId;
    if (!shouldAutoRunFarmJob(jobId)) {
      const state = getFarmJobAutoRunState(jobId);
      setFarmJobStatus(
        state === "started"
          ? "This job already ran in this browser tab ΓÇö refresh will not restart it. Start a new job from the farm dashboard."
          : `Farm job already ${state || "finished"} in this tab ΓÇö start a new job from the farm dashboard.`,
      );
      return;
    }

    let timer = null;
    let cancelled = false;

    (async () => {
      try {
        const remote = await fetchFarmJobStatus(farmUpload);
        if (cancelled) return;
        const status = String(remote?.status || "").toLowerCase();
        if (status === "completed") {
          markFarmJobDone(jobId);
          setFarmJobStatus("Farm job is completed ΓÇö not starting automation again.");
          return;
        }
        if (status === "failed") {
          markFarmJobAutoRunCancelled(jobId);
          setFarmJobStatus("Farm job failed on the server ΓÇö start a new job from the farm dashboard.");
          return;
        }
      } catch {
        /* farm unreachable ΓÇö still allow embedded runner to proceed */
      }

      if (cancelled) return;
      setFarmJobStatus("Starting slideshow batchΓÇª");
      timer = window.setTimeout(() => {
        void handleGenerateBatch();
      }, 800);
    })();

    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [autoRunBatch, farmUpload?.jobId]);

  // ΓöÇΓöÇ Video export: capture each slide, then animate ΓöÇΓöÇ
  const encodeWorkspaceVideoToBlob = async (exportCfg) => {
    setExportProgress(0);
    await waitWhilePaused();
    if (cancelGenRef.current) return null;

    let cfg = exportCfg;
    if (needsExportImageInlining(cfg)) {
      setExportStatus("Preparing images for exportΓÇª");
      cfg = await ensureExportImageUrls(cfg);
      flushSync(() => setConfig((prev) => ({ ...prev, slots: cfg.slots })));
      await waitForPreviewPaint();
      await new Promise((r) => {
        requestAnimationFrame(() => requestAnimationFrame(r));
      });
      await waitForImagesDecoded(getCaptureNode());
    }

    if ((cfg.outputFormat ?? "standard") === "starterPack") {
      setExportStatus("Generating starter pack textΓÇª");
      const sp = await ensureStarterPackAutofill();
      await waitWhilePaused();
      if (cancelGenRef.current) return null;
      setExportStatus("Generating starter pack imagesΓÇª");
      await ensureStarterPackImages(sp?.imagePrompts ?? sp?.items, cfg);
      await waitWhilePaused();
      if (cancelGenRef.current) return null;
      setExportStatus("Capturing slidesΓÇª");
    }

    const slidesCount = getTotalSlides(cfg);
    const allSlideFrames = [];
    const previewNode = getCaptureNode();
    const fontEmbedCSS = previewNode ? await getFontEmbedCSS(previewNode) : undefined;
    const fps = 30;

    for (let i = 0; i < slidesCount; i++) {
      await waitWhilePaused();
      if (cancelGenRef.current) return null;
      flushSync(() => {
        setCurrentSlide(i);
      });
      await waitForPreviewPaint();

      const info = getSlideInfo(cfg, i);
      const bg =
        info.type === "collage"
          ? "#111111"
          : info.type === "fullBleed" || info.type === "imessage" || info.type === "starterPack" || info.type === "labelyShelfIntro"
          ? "#000000"
          : "#ffffff";

      if (info.type === "starterPack") {
        // Capture 4 phases (each ~1.25s) so items dissolve in over 5 seconds
        const SP_PHASES = 4;
        const SP_PHASE_DURATION = 5 / SP_PHASES; // seconds per phase
        for (let phase = 1; phase <= SP_PHASES; phase++) {
          await waitWhilePaused();
          if (cancelGenRef.current) {
            setConfig((prev) => ({ ...prev, _spPhase: -1 }));
            return null;
          }
          setConfig((prev) => ({ ...prev, _spPhase: phase }));
          await new Promise((r) => setTimeout(r, 120));
          try {
            const canvas = await captureSlideCanvas(bg, fontEmbedCSS);
            if (!canvas) throw new Error("Preview node not found");
            allSlideFrames.push([canvas, SP_PHASE_DURATION]);
          } catch (err) {
            console.error("Capture error starterPack phase", phase, err);
            allSlideFrames.push([]);
          }
        }
        // Reset phase
        setConfig((prev) => ({ ...prev, _spPhase: -1 }));
      } else if (info.type === "labelyShelfIntro" && isLabelyScanTourFormat(cfg)) {
        await new Promise((r) => setTimeout(r, 80));
        try {
          const slotNow = info.slot ?? cfg.slots?.[0];
          const productDataUrl = String(
            slotNow?.labelyShelfImageUrl
              || ((cfg.appId ?? "thrifty") === "valcoin" ? slotNow?.imageUrl : "")
              || "",
          ).trim();
          const introCanvas = await captureShelfIntroCanvas(
            productDataUrl,
            (cfg.jitterSeed ?? 0) + (info.itemIndex ?? 0) * 9973,
          );
          allSlideFrames.push([introCanvas]);
        } catch (err) {
          console.error("Capture error scan tour intro", err);
          try {
            const fallback = await captureSlideCanvas(bg, fontEmbedCSS);
            if (fallback) allSlideFrames.push([fallback]);
            else allSlideFrames.push([]);
          } catch {
            allSlideFrames.push([]);
          }
        }
      } else if (
        (cfg.outputFormat ?? "standard") === "labelyScan" &&
        ["labely", "valcoin"].includes(cfg.appId ?? "thrifty") &&
        (info.type === "labely" || (info.type === "thrifty" && (cfg.appId ?? "thrifty") === "valcoin"))
      ) {
        await new Promise((r) => setTimeout(r, 80));
        try {
          const labelyCanvas = await captureSlideCanvas(bg, fontEmbedCSS);
          if (!labelyCanvas) throw new Error("Preview node not found");
          const slotNow = info.slot ?? cfg.slots?.[info.itemIndex ?? 0];
          const productDataUrl =
            typeof slotNow?.imageUrl === "string" ? slotNow.imageUrl.trim() : "";
          const seq = await buildLabelyScanFrameSequence({
            productDataUrl,
            labelyCanvas,
            scanSec: 1.35,
            revealSec: 0.52,
            holdSec: cfg.slideDuration,
            fps,
            imageVariationSeed: (cfg.jitterSeed ?? 0) + (info.itemIndex ?? i) * 9973,
          });
          if (!seq?.length) throw new Error("Scan frame sequence empty");
          allSlideFrames.push([labelyCanvas, seq]);
        } catch (err) {
          console.error("Capture error Labely scan intro", err);
          try {
            const labelyCanvas = await captureSlideCanvas(bg, fontEmbedCSS);
            if (labelyCanvas) allSlideFrames.push([labelyCanvas]);
            else allSlideFrames.push([]);
          } catch {
            allSlideFrames.push([]);
          }
        }
      } else {
        await new Promise((r) => setTimeout(r, 80));
        try {
          const canvas = await captureSlideCanvas(bg, fontEmbedCSS);
          if (!canvas) throw new Error("Preview node not found");
          allSlideFrames.push([canvas]);
        } catch (err) {
          console.error("Capture error slide", i, err);
          const msg = err?.message ? String(err.message) : "";
          if (msg && needsExportImageInlining(cfg)) setExportStatus(msg);
          allSlideFrames.push([]);
        }
      }

      setExportProgress(Math.round((i + 1) / slidesCount * 40));
      setExportStatus(`Captured slide ${i + 1} of ${slidesCount}ΓÇª`);
    }

    // Filter to slides that have at least one captured frame
    const validSlides = allSlideFrames
      .map((snapshots, i) => ({ snapshots, origIndex: i }))
      .filter(({ snapshots }) => snapshots.length > 0);

    if (validSlides.length === 0) {
      setExportStatus("Export failed ΓÇö no frames captured.");
      return null;
    }

    await waitWhilePaused();
    if (cancelGenRef.current) return null;

    // ΓöÇΓöÇ PHASE 2: Encode with native WebCodecs + mp4-muxer (no WASM, no CDN) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    setExportStatus("Preparing encoderΓÇª");
    setExportProgress(42);

    // WebCodecs availability check
    if (typeof VideoEncoder === "undefined") {
      setExportStatus("WebCodecs not available ΓÇö please use Chrome or Safari 16+.");
      return null;
    }

    const OUT_W = 1080;
    const OUT_H = 1920;
    const transitionFrames = Math.round((cfg.transitionMs / 1000) * fps);
    const frameDurationUs  = Math.round(1_000_000 / fps); // microseconds per frame

    // Per-slide hold duration in frames.
    // Labely scan intro: snapshots[1] is HTMLCanvasElement[] (one frame per entry).
    // StarterPack phases: snapshots[1] is duration in seconds (number).
    const perSlideHoldFrames = validSlides.map(({ snapshots }) => {
      if (Array.isArray(snapshots) && snapshots.length >= 2 && Array.isArray(snapshots[1])) {
        return snapshots[1].length;
      }
      const overrideSec = snapshots[1];
      const baseSec = typeof overrideSec === "number" ? overrideSec : cfg.slideDuration;
      const jitterMs = typeof overrideSec === "number" ? 0 : Math.floor(Math.random() * 500);
      return Math.round((baseSec + jitterMs / 1000) * fps);
    });

    // Total frame count for progress
    let totalFrames = 0;
    for (let i = 0; i < validSlides.length; i++) {
      totalFrames += perSlideHoldFrames[i];
      if (i < validSlides.length - 1) totalFrames += transitionFrames;
    }

    // Scale canvas: renders each frame at exact 1080├ù1920
    const scaleCanvas = document.createElement("canvas");
    scaleCanvas.width  = OUT_W;
    scaleCanvas.height = OUT_H;
    const sctx = scaleCanvas.getContext("2d");

    // ΓöÇΓöÇ Optional audio: fetch, decode, prepare ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    let decodedAudio = null;   // AudioBuffer | null
    let audioSampleRate = 44100;
    let audioChannels = 2;

    if (cfg.useRandomAudio && typeof AudioEncoder !== "undefined") {
      try {
        setExportStatus("Loading audioΓÇª");
        const { files: audioFiles } = await fetch("/api/audio").then((r) => r.json());
        if (audioFiles?.length > 0) {
          const pick = audioFiles[Math.floor(Math.random() * audioFiles.length)];
          const ab = await fetch(pick).then((r) => r.arrayBuffer());
          const ac = new AudioContext();
          decodedAudio = await ac.decodeAudioData(ab);
          audioSampleRate = decodedAudio.sampleRate;
          audioChannels = Math.min(decodedAudio.numberOfChannels, 2);
          await ac.close();
        }
      } catch (e) {
        console.warn("Audio load failed, exporting without audio:", e);
        decodedAudio = null;
      }
    }

    // mp4-muxer setup (pure JS, in-memory)
    const { Muxer, ArrayBufferTarget } = await import("mp4-muxer");
    const target = new ArrayBufferTarget();
    const muxerOpts = {
      target,
      video: { codec: "avc", width: OUT_W, height: OUT_H },
      fastStart: "in-memory",
    };
    if (decodedAudio) {
      muxerOpts.audio = { codec: "aac", numberOfChannels: audioChannels, sampleRate: audioSampleRate };
    }
    const muxer = new Muxer(muxerOpts);

    // VideoEncoder (browser-native H.264)
    let encoderError = null;
    const encoder = new VideoEncoder({
      output: (chunk, meta) => muxer.addVideoChunk(chunk, meta),
      error:  (e) => { encoderError = e; console.error("VideoEncoder:", e); },
    });
    encoder.configure({
      codec:        "avc1.640028",   // H.264 High Profile Level 4.0
      width:        OUT_W,
      height:       OUT_H,
      bitrate:      12_000_000,
      framerate:    fps,
      bitrateMode:  "constant",
      latencyMode:  "quality",
    });

    // ΓöÇΓöÇ Encode every frame ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    let pts = 0;           // presentation timestamp in microseconds
    let encoded = 0;

    const slideRepresentativeCanvas = (snaps) => {
      if (Array.isArray(snaps?.[1]) && snaps[1].length > 0) return snaps[1][snaps[1].length - 1];
      return snaps[0];
    };
    const slideFirstCanvas = (snaps) => {
      if (Array.isArray(snaps?.[1]) && snaps[1].length > 0) return snaps[1][0];
      return snaps[0];
    };

    for (let si = 0; si < validSlides.length; si++) {
      await waitWhilePaused();
      if (cancelGenRef.current) {
        try { encoder.close(); } catch {}
        setExportStatus("Export cancelled.");
        return null;
      }
      const curSnaps = validSlides[si].snapshots;
      const frameSeq = Array.isArray(curSnaps?.[1]) ? curSnaps[1] : null;
      const holdFrames = perSlideHoldFrames[si];

      for (let f = 0; f < holdFrames; f++) {
        if (encoderError) break;
        await waitWhilePaused();
        if (cancelGenRef.current) {
          try { encoder.close(); } catch {}
          setExportStatus("Export cancelled.");
          return null;
        }
        sctx.clearRect(0, 0, OUT_W, OUT_H);
        const src = frameSeq ? frameSeq[f] : curSnaps[0];
        sctx.drawImage(src, 0, 0, OUT_W, OUT_H);

        const vf = new VideoFrame(scaleCanvas, { timestamp: pts, duration: frameDurationUs });
        encoder.encode(vf, { keyFrame: encoded % fps === 0 });
        vf.close();
        pts += frameDurationUs;
        encoded++;

        // Yield periodically to keep the UI responsive
        if (encoded % 20 === 0) {
          await new Promise((r) => setTimeout(r, 0));
          setExportProgress(42 + Math.round((encoded / totalFrames) * 55));
          setExportStatus(`Encoding frame ${encoded} / ${totalFrames}ΓÇª`);
        }
        // Throttle if the encoder queue is building up
        while (encoder.encodeQueueSize > 12) {
          await new Promise((r) => setTimeout(r, 5));
          if (cancelGenRef.current) {
            try { encoder.close(); } catch {}
            setExportStatus("Export cancelled.");
            return null;
          }
        }
      }

      // Transition phase ΓÇö iPhone cubic ease-out swipe
      if (si < validSlides.length - 1) {
        const nxtSnaps = validSlides[si + 1].snapshots;
        const curCv = slideRepresentativeCanvas(curSnaps);
        const nxtCv = slideFirstCanvas(nxtSnaps);
        for (let f = 0; f < transitionFrames; f++) {
          if (encoderError) break;
          await waitWhilePaused();
          if (cancelGenRef.current) {
            try { encoder.close(); } catch {}
            setExportStatus("Export cancelled.");
            return null;
          }
          const t      = f / transitionFrames;
          const eased  = 1 - Math.pow(1 - t, 3);
          const offset = Math.round(eased * OUT_W);
          sctx.clearRect(0, 0, OUT_W, OUT_H);
          sctx.drawImage(curCv, -offset,        0, OUT_W, OUT_H);
          sctx.drawImage(nxtCv,                   OUT_W - offset, 0, OUT_W, OUT_H);

          const vf = new VideoFrame(scaleCanvas, { timestamp: pts, duration: frameDurationUs });
          encoder.encode(vf, { keyFrame: false });
          vf.close();
          pts += frameDurationUs;
          encoded++;
        }
      }
    }

    if (encoderError) {
      setExportStatus(`Encoding failed: ${encoderError.message}`);
      return null;
    }

    await waitWhilePaused();
    if (cancelGenRef.current) {
      try { encoder.close(); } catch {}
      setExportStatus("Export cancelled.");
      return null;
    }

    setExportStatus("Finalizing MP4ΓÇª");
    setExportProgress(97);
    await encoder.flush();

    await waitWhilePaused();
    if (cancelGenRef.current) {
      setExportStatus("Export cancelled.");
      return null;
    }

    // ΓöÇΓöÇ Encode audio track (if loaded) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    if (decodedAudio) {
      try {
        setExportStatus("Encoding audioΓÇª");
        const totalVideoDurationSec = (pts) / 1_000_000;
        const totalAudioSamples = Math.ceil(totalVideoDurationSec * audioSampleRate);
        const CHUNK = 4096;

        const channelData = Array.from({ length: audioChannels }, (_, ch) =>
          decodedAudio.getChannelData(ch)
        );
        const srcLen = channelData[0].length;

        let audioError = null;
        const audioEncoder = new AudioEncoder({
          output: (chunk, meta) => muxer.addAudioChunk(chunk, meta),
          error:  (e) => { audioError = e; console.error("AudioEncoder:", e); },
        });
        await audioEncoder.configure({
          codec:            "mp4a.40.2",   // AAC-LC
          sampleRate:       audioSampleRate,
          numberOfChannels: audioChannels,
          bitrate:          192_000,
        });

        let audioOffset = 0;
        while (audioOffset < totalAudioSamples && !audioError) {
          await waitWhilePaused();
          if (cancelGenRef.current) {
            try { await audioEncoder.flush(); } catch {}
            try { audioEncoder.close(); } catch {}
            setExportStatus("Export cancelled.");
            return null;
          }
          const size = Math.min(CHUNK, totalAudioSamples - audioOffset);
          // Build planar float32 buffer: [ch0 samples ΓÇª ch1 samples ΓÇª]
          const buf = new Float32Array(size * audioChannels);
          for (let ch = 0; ch < audioChannels; ch++) {
            for (let i = 0; i < size; i++) {
              buf[ch * size + i] = channelData[ch][(audioOffset + i) % srcLen];
            }
          }
          const timestampUs = Math.round((audioOffset / audioSampleRate) * 1_000_000);
          const audioData = new AudioData({
            format:           "f32-planar",
            sampleRate:       audioSampleRate,
            numberOfChannels: audioChannels,
            numberOfFrames:   size,
            timestamp:        timestampUs,
            data:             buf,
          });
          audioEncoder.encode(audioData);
          audioData.close();
          audioOffset += size;
        }
        await audioEncoder.flush();
      } catch (e) {
        console.warn("Audio encode failed, video will be silent:", e);
      }
    }

    muxer.finalize();

    return new Blob([target.buffer], { type: "video/mp4" });
  };

  const handleExportVideo = async () => {
    cancelGenRef.current = false;
    setIsExporting(true);
    setExportProgress(0);
    setExportStatus("Capturing slidesΓÇª");
    try {
      const blob = await encodeWorkspaceVideoToBlob(config);
      if (blob) {
        triggerMp4Download(blob, `${randomExportHex(14)}.mp4`);
        if (isLabely && config.labelyUseBraveImages !== false) {
          await markExportedBraveImagesUsed({ ...config, labelyUseBraveImages: true });
        }
        setExportProgress(100);
        setExportStatus("Done! Video downloaded.");
      }
    } finally {
      setIsExporting(false);
      setTimeout(() => {
        setExportStatus("");
        setExportProgress(0);
      }, 3000);
    }
  };

  /** Batch + gallery iPhone packs: one H.264 .mp4 per slideshow inside each ZIP (never PNG). */
  /** Farm /automation: encode each saved show and upload MP4(s) to gallery slot(s). */
  const exportShowsToFarm = async (shows, restoreConfig, { auto = false } = {}) => {
    const activeFarm = farmUpload;
    if (!activeFarm?.farmUrl || !activeFarm?.jobId || !shows?.length) return false;

    cancelGenRef.current = false;
    setIsExporting(true);
    setExportProgress(0);
    let encodedMp4Count = 0;
    const uploadedSlots = new Set();
    const statusPrefix = auto ? "Auto-export: " : "Farm upload: ";

    try {
      const videosPerPhone = Math.max(1, Number(activeFarm.videosPerPhone) || 3);
      for (let i = 0; i < shows.length; i++) {
        await waitWhilePaused();
        if (cancelGenRef.current) break;
        const show = shows[i];
        const phoneIndex = Math.floor(i / videosPerPhone);
        const videoOnPhone = (i % videosPerPhone) + 1;
        const farmSlot = activeFarm.slots?.[phoneIndex] ?? activeFarm.slots?.[0];
        if (!farmSlot) {
          console.warn("No farm slot mapped for slideshow", i + 1);
          continue;
        }
        setExportStatus(`${statusPrefix}Encoding MP4 ${i + 1} / ${shows.length} (phone ${farmSlot} video ${videoOnPhone})ΓÇª`);
        const exportCfg = galleryShowToExportConfig(restoreConfig, show);
        flushSync(() => setConfig(exportCfg));
        flushSync(() => setCurrentSlide(0));
        await waitForPreviewPaint();
        const blob = await encodeWorkspaceVideoToBlob(exportCfg);
        if (cancelGenRef.current) break;
        if (!blob) continue;
        const arr = new Uint8Array(await blob.arrayBuffer());
        if (isPngBytes(arr) || !isMp4Bytes(arr)) {
          setExportStatus(`Skipped video ${i + 1} ΓÇö invalid MP4 payload.`);
          continue;
        }
        const filename = farmGalleryMp4Filename(farmSlot, videoOnPhone, show);
        const clearSlot = videoOnPhone === 1;
        uploadedSlots.add(String(farmSlot));
        setFarmJobStatus(`Uploading ${filename} ΓåÆ slot ${farmSlot}ΓÇª`);
        await uploadMp4ToFarm({
          farmUrl: activeFarm.farmUrl,
          jobId: activeFarm.jobId,
          secret: activeFarm.secret,
          slot: farmSlot,
          file: blob,
          filename,
          clear: clearSlot,
        });
        encodedMp4Count++;
        setExportProgress(Math.round(((i + 1) / shows.length) * 100));
      }

      if (encodedMp4Count === 0) {
        const msg = "No MP4 videos uploaded to farm.";
        setExportStatus(msg);
        markFarmJobFailed(msg, activeFarm.jobId);
        return false;
      }

      setFarmJobStatus("Farm ingest complete.");
      await notifyAutomationDone({
        farmUrl: activeFarm.farmUrl,
        jobId: activeFarm.jobId,
        secret: activeFarm.secret,
      });
      if (restoreConfig?.labelyUseBraveImages !== false) {
        await markExportedBraveImagesUsed(
          shows.map((show) => ({
            appId: show.appId ?? restoreConfig.appId,
            labelyUseBraveImages: true,
            slots: show.slots ?? [],
          })),
        );
      }
      setExportProgress(100);
      setExportStatus(`Done! Uploaded ${encodedMp4Count} MP4(s) to farm.`);
      markFarmJobDone(activeFarm.jobId);
      setTimeout(() => setGenAllProgress(null), 4000);
      return true;
    } catch (e) {
      console.error(e);
      const msg = e?.message || String(e);
      markFarmJobFailed(msg, activeFarm.jobId);
      setExportStatus(`Farm upload failed: ${msg}`);
      return false;
    } finally {
      flushSync(() => setConfig(restoreConfig));
      flushSync(() => setCurrentSlide(0));
      setIsExporting(false);
      setTimeout(() => {
        setExportStatus("");
        setExportProgress(0);
      }, 5000);
    }
  };

  const exportIphoneMp4ZipPlans = async (shows, restoreConfig, { auto = false, farmUpload: farmCtx = null } = {}) => {
    const activeFarm = farmCtx || farmUpload;
    const zipPlan = tryBuildIphoneBatchZipPlan(shows);
    if (zipPlan?.error) {
      if (auto) setExportStatus(zipPlan.error);
      else alert(zipPlan.error);
      return false;
    }

    if (zipPlan?.zipPlans?.length) {
      const zipPlans = zipPlan.zipPlans;
      const zipFilePrefix =
        String(shows[0]?.appId || "").trim() === "valcoin"
          ? "valcoin-iphone-mp4-"
          : "labely-iphone-mp4-";
      const totalJobs = zipPlans.reduce((sum, plan) => sum + plan.jobs.length, 0);
      let completedJobs = 0;
      let encodedMp4Count = 0;
      cancelGenRef.current = false;
      setIsExporting(true);
      setExportProgress(0);
      setExportStatus(`${auto ? "Auto-export: " : ""}Encoding ${totalJobs} MP4 videos into ${zipPlans.length} ZIPsΓÇª`);
      try {
        const { zipSync } = await import("fflate");
        let downloadedZipCount = 0;
        const uploadedSlots = new Set();
        const farmMode = !!(activeFarm?.farmUrl && activeFarm?.jobId);

        for (const plan of zipPlans) {
          if (cancelGenRef.current) break;
          const zipEntries = {};
          const farmSlot = farmMode ? activeFarm.slots?.[plan.iphoneNumber - 1] : null;
          for (let i = 0; i < plan.jobs.length; i++) {
            await waitWhilePaused();
            if (cancelGenRef.current) break;
            const { zipRelPath, show } = plan.jobs[i];
            const mp4Path = String(zipRelPath || "").toLowerCase().endsWith(".mp4")
              ? zipRelPath
              : `${zipRelPath}.mp4`;
            const statusPrefix = auto ? "Auto-export: " : farmMode ? "Farm upload: " : "";
            setExportStatus(`${statusPrefix}iPhone ${plan.iphoneNumber}: encoding MP4 ${i + 1} / ${plan.jobs.length}ΓÇª`);
            const exportCfg = galleryShowToExportConfig(restoreConfig, show);
            flushSync(() => setConfig(exportCfg));
            flushSync(() => setCurrentSlide(0));
            await waitForPreviewPaint();
            const blob = await encodeWorkspaceVideoToBlob(exportCfg);
            if (cancelGenRef.current) break;
            if (blob) {
              const arr = new Uint8Array(await blob.arrayBuffer());
              if (isPngBytes(arr)) {
                console.error("Refusing PNG bytes in MP4 ZIP entry", mp4Path);
                setExportStatus(`Skipped ${mp4Path} ΓÇö got PNG instead of MP4 (stale build or encoder bug). Hard-refresh and retry.`);
              } else if (!isMp4Bytes(arr)) {
                console.error("Invalid MP4 payload for ZIP entry", mp4Path, arr.slice(0, 16));
                setExportStatus(`Skipped ${mp4Path} ΓÇö file is not a valid MP4. Use Chrome or Safari 16+.`);
              } else if (farmMode) {
                if (!farmSlot) {
                  console.warn("No farm slot mapped for iPhone pack", plan.iphoneNumber);
                } else {
                  const filename = String(mp4Path || "").split("/").pop() || "slideshow.mp4";
                  const clearSlot = !uploadedSlots.has(farmSlot);
                  uploadedSlots.add(farmSlot);
                  setFarmJobStatus(`Uploading ${filename} ΓåÆ slot ${farmSlot}ΓÇª`);
                  await uploadMp4ToFarm({
                    farmUrl: activeFarm.farmUrl,
                    jobId: activeFarm.jobId,
                    secret: activeFarm.secret,
                    slot: farmSlot,
                    file: blob,
                    filename,
                    clear: clearSlot,
                  });
                  encodedMp4Count++;
                }
              } else {
                zipEntries[mp4Path] = [arr, randomZipEntryOptions()];
                encodedMp4Count++;
              }
            }
            completedJobs++;
            setExportProgress(Math.round((completedJobs / totalJobs) * 95));
            await new Promise((r) => setTimeout(r, 120));
          }

          if (cancelGenRef.current) break;

          if (farmMode) continue;

          if (Object.keys(zipEntries).length === 0) continue;

          setExportStatus(`${auto ? "Auto-export: " : ""}Building MP4 ZIP ${plan.iphoneNumber} / ${zipPlans.length}ΓÇª`);
          const zipData = zipSync(zipEntries, { level: 1 });
          const blob = new Blob([zipData], { type: "application/zip" });
          triggerZipDownload(blob, `${zipFilePrefix}${String(plan.iphoneNumber).padStart(2, "0")}-${randomExportHex(10)}.zip`);
          downloadedZipCount++;
          await new Promise((r) => setTimeout(r, 650));
        }

        if (farmMode) {
          if (encodedMp4Count === 0) {
            const msg = "No MP4 videos uploaded to farm.";
            setExportStatus(msg);
            markFarmJobFailed(msg, activeFarm.jobId);
          } else {
            setFarmJobStatus("Starting farm batchΓÇª");
            await notifyAutomationDone({
              farmUrl: activeFarm.farmUrl,
              jobId: activeFarm.jobId,
              secret: activeFarm.secret,
            });
            setExportProgress(100);
            setExportStatus(`Done! Uploaded ${encodedMp4Count} MP4(s) to farm.`);
            markFarmJobDone(activeFarm.jobId);
          }
          return encodedMp4Count > 0;
        }

        if (downloadedZipCount === 0) {
          setExportStatus(
            encodedMp4Count === 0
              ? "No MP4 videos encoded ΓÇö use Chrome or Safari 16+ with WebCodecs, then run export again."
              : "Nothing encoded ΓÇö ZIP export cancelled.",
          );
        } else {
          setExportProgress(100);
          setExportStatus(`Done! Downloaded ${downloadedZipCount} iPhone ZIPs (${encodedMp4Count} MP4 videos).`);
        }
        return downloadedZipCount > 0;
      } catch (e) {
        console.error(e);
        if (activeFarm?.farmUrl && activeFarm?.jobId) {
          markFarmJobFailed(e?.message || String(e), activeFarm.jobId);
        }
        setExportStatus("iPhone ZIP export failed ΓÇö see console.");
        return false;
      } finally {
        flushSync(() => setConfig(restoreConfig));
        flushSync(() => setCurrentSlide(0));
        setIsExporting(false);
        setTimeout(() => {
          setExportStatus("");
          setExportProgress(0);
        }, 5000);
      }
    }
    return false;
  };

  const handleExportAllVideos = async () => {
    const restoreConfig = {
      ...config,
      slots: (config.slots ?? []).map((s) => ({ ...s })),
    };

    const aid = config.appId ?? "thrifty";
    if (aid === "labely") {
      const labelyGallery = savedSlideshows.filter((s) => savedShowMatchesApp(s, "labely"));
      if (await exportIphoneMp4ZipPlans(labelyGallery, restoreConfig)) return;
    }
    if (aid === "valcoin") {
      const valcoinGallery = savedSlideshows.filter((s) => savedShowMatchesApp(s, "valcoin"));
      if (await exportIphoneMp4ZipPlans(valcoinGallery, restoreConfig)) return;
    }

    const videos = savedSlideshows.filter((s) => savedShowMatchesApp(s, aid));
    if (videos.length < 2) return;

    cancelGenRef.current = false;
    setIsExporting(true);
    setExportProgress(0);
    setExportStatus("Preparing batch exportΓÇª");
    try {
      for (let i = 0; i < videos.length; i++) {
        await waitWhilePaused();
        if (cancelGenRef.current) break;
        const show = videos[i];
        setExportStatus(`Exporting video ${i + 1} of ${videos.length}ΓÇª`);
        const exportCfg = galleryShowToExportConfig(restoreConfig, show);
        flushSync(() => setConfig(exportCfg));
        flushSync(() => setCurrentSlide(0));
        await waitForPreviewPaint();
        const blob = await encodeWorkspaceVideoToBlob(exportCfg);
        if (cancelGenRef.current) break;
        if (blob) {
          triggerMp4Download(blob, sequentialRandomMp4Name(i, show));
          await new Promise((r) => setTimeout(r, 400));
        }
        setExportProgress(Math.round(((i + 1) / videos.length) * 100));
      }
      if (cancelGenRef.current) {
        setExportStatus("Export cancelled.");
      } else {
        setExportProgress(100);
        setExportStatus(`Done! ${videos.length} videos downloaded.`);
      }
    } catch (e) {
      console.error(e);
      setExportStatus("Batch video export failed ΓÇö see console.");
    } finally {
      flushSync(() => setConfig(restoreConfig));
      flushSync(() => setCurrentSlide(0));
      setIsExporting(false);
      setTimeout(() => {
        setExportStatus("");
        setExportProgress(0);
      }, 4000);
    }
  };

  const handleExportPNG = async () => {
    const el = getCaptureNode();
    if (!el) return;
    setIsExporting(true);
    setExportProgress(20);
    try {
      if (needsExportImageInlining(config)) {
        setExportStatus("Preparing images for exportΓÇª");
        const cfg = await ensureExportImageUrls(config);
        flushSync(() => setConfig((prev) => ({ ...prev, slots: cfg.slots })));
        await waitForPreviewPaint();
        await waitForImagesDecoded(el);
      }
      if ((config.outputFormat ?? "standard") === "starterPack") {
        setExportStatus("Generating starter pack textΓÇª");
        const sp = await ensureStarterPackAutofill();
        setExportStatus("Generating starter pack imagesΓÇª");
        await ensureStarterPackImages(sp?.imagePrompts ?? sp?.items);
      }
      const fontEmbedCSS = await getFontEmbedCSS(el);
      const capInfo = getSlideInfo(config, currentSlide);
      const capBg =
        capInfo.type === "collage"
          ? "#111111"
          : capInfo.type === "fullBleed" || capInfo.type === "imessage" || capInfo.type === "starterPack"
          ? "#000000"
          : capInfo.type === "voicemail"
          ? "#ffffff"
          : "#ffffff";
      const canvas = await captureSlideCanvas(capBg, fontEmbedCSS);
      if (!canvas) throw new Error("Preview node not found");
      setExportProgress(80);
      const blob = await new Promise((res) => canvas.toBlob(res, "image/png"));
      if (!blob) {
        setIsExporting(false);
        setExportProgress(0);
        return;
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `slide-${currentSlide + 1}.png`;
      a.click();
      URL.revokeObjectURL(url);
      setExportProgress(100);
      setTimeout(() => { setIsExporting(false); setExportProgress(0); }, 600);
    } catch (err) {
      setIsExporting(false);
      setExportProgress(0);
    }
  };

  const addCanvasPngEntry = async (pngEntries, usedZipEntryNames, canvas, dir, orderIndex) => {
    const blob = await new Promise((res) => canvas.toBlob(res, "image/png"));
    if (!blob) throw new Error("no PNG blob");
    const arr = new Uint8Array(await blob.arrayBuffer());
    pngEntries[uniqueZipPngPath(usedZipEntryNames, dir, orderIndex)] = [arr, randomZipEntryOptions()];
  };

  const capturePngEntriesForConfig = async (
    exportCfg,
    {
      pngEntries,
      usedZipEntryNames,
      baseDir = "",
      statusPrefix = "",
      progressBase = 0,
      progressSpan = 85,
    } = {},
  ) => {
    let cfg = exportCfg;
    flushSync(() => setConfig(cfg));
    flushSync(() => setCurrentSlide(0));
    await waitForPreviewPaint();

    if (needsExportImageInlining(cfg)) {
      setExportStatus(`${statusPrefix}Preparing images for exportΓÇª`);
      cfg = await ensureExportImageUrls(cfg);
      flushSync(() => setConfig(cfg));
      await waitForPreviewPaint();
      await waitForImagesDecoded(getCaptureNode());
    }

    if ((cfg.outputFormat ?? "standard") === "starterPack") {
      setExportStatus(`${statusPrefix}Generating starter pack textΓÇª`);
      const sp = await ensureStarterPackAutofill();
      setExportStatus(`${statusPrefix}Generating starter pack imagesΓÇª`);
      await ensureStarterPackImages(sp?.imagePrompts ?? sp?.items, cfg);
      setExportStatus(`${statusPrefix}Capturing slidesΓÇª`);
    }

    const slidesCount = getTotalSlides(cfg);
    const previewNode = getCaptureNode();
    const fontEmbedCSS = previewNode ? await getFontEmbedCSS(previewNode) : undefined;
    let entryIndex = 0;

    for (let i = 0; i < slidesCount; i++) {
      await waitWhilePaused();
      if (cancelGenRef.current) break;
      flushSync(() => {
        setCurrentSlide(i);
      });
      await waitForPreviewPaint();
      await new Promise((r) => setTimeout(r, 80));

      const info = getSlideInfo(cfg, i);
      const bg =
        info.type === "collage"    ? "#111111"
        : info.type === "fullBleed" || info.type === "imessage" || info.type === "starterPack" || info.type === "labelyShelfIntro" ? "#000000"
        : "#ffffff";
      const shouldIncludeScanSourcePng =
        (cfg.outputFormat ?? "standard") === "labelyScan" &&
        ["labely", "valcoin"].includes(cfg.appId ?? "thrifty") &&
        (info.type === "labely" || (info.type === "thrifty" && (cfg.appId ?? "thrifty") === "valcoin"));

      if (shouldIncludeScanSourcePng) {
        try {
          const slotNow = info.slot ?? cfg.slots?.[info.itemIndex ?? 0];
          const productDataUrl =
            typeof slotNow?.imageUrl === "string" ? slotNow.imageUrl.trim() : "";
          const scanCanvas = await captureScanSourceCanvas(
            productDataUrl,
            (cfg.jitterSeed ?? 0) + (info.itemIndex ?? i) * 9973,
          );
          await addCanvasPngEntry(pngEntries, usedZipEntryNames, scanCanvas, baseDir, entryIndex++);
        } catch (e) {
          console.warn("Skipping scan source PNG", i, e);
        }
      }

      if (info.type === "starterPack") {
        setConfig((prev) => ({ ...prev, _spPhase: 4 }));
        await new Promise((r) => setTimeout(r, 120));
        try {
          const canvas = await captureSlideCanvas(bg, fontEmbedCSS);
          if (!canvas) throw new Error("no canvas");
          await addCanvasPngEntry(pngEntries, usedZipEntryNames, canvas, baseDir, entryIndex++);
        } catch (e) { console.warn("Skipping starterPack slide", e); }
        setConfig((prev) => ({ ...prev, _spPhase: -1 }));
      } else {
        try {
          const canvas = await captureSlideCanvas(bg, fontEmbedCSS);
          if (!canvas) throw new Error("no canvas");
          await addCanvasPngEntry(pngEntries, usedZipEntryNames, canvas, baseDir, entryIndex++);
        } catch (e) {
          console.warn("Skipping slide", i, e);
        }
      }

      setExportProgress(Math.round(progressBase + ((i + 1) / slidesCount) * progressSpan));
      setExportStatus(`${statusPrefix}Captured ${i + 1} / ${slidesCount}ΓÇª`);
    }
  };

  /** Manual export only (Export ΓåÆ ΓÇ£All slides ΓåÆ ZIP (PNG)ΓÇ¥). Never used after batch generate. */
  const exportIphonePngZipPlans = async (shows, restoreConfig) => {
    const zipPlan = tryBuildIphoneBatchZipPlan(shows);
    if (zipPlan?.error) {
      alert(zipPlan.error);
      return true;
    }
    if (!zipPlan?.zipPlans?.length) return false;

    const zipPlans = zipPlan.zipPlans;
    const zipFilePrefix =
      String(shows[0]?.appId || "").trim() === "valcoin" ? "valcoin-iphone-png-" : "labely-iphone-png-";
    const totalJobs = zipPlans.reduce((sum, plan) => sum + plan.jobs.length, 0);
    let completedJobs = 0;
    cancelGenRef.current = false;
    setIsExporting(true);
    setExportProgress(0);
    setExportStatus(`Exporting PNG folders for ${zipPlans.length} iPhonesΓÇª`);

    try {
      const { zipSync } = await import("fflate");
      let downloadedZipCount = 0;

      for (const plan of zipPlans) {
        if (cancelGenRef.current) break;
        const zipEntries = {};
        const usedZipEntryNames = new Set();
        const iphoneDir = iphoneFolderName(plan.iphoneNumber);

        for (let i = 0; i < plan.jobs.length; i++) {
          await waitWhilePaused();
          if (cancelGenRef.current) break;
          const { zipRelPath, show } = plan.jobs[i];
          const showDir = `${iphoneDir}/${slideshowFolderName(i, show, zipRelPath)}`;
          const exportCfg = galleryShowToExportConfig(restoreConfig, show);
          setExportStatus(`iPhone ${plan.iphoneNumber}: capturing slideshow ${i + 1} / ${plan.jobs.length}ΓÇª`);
          await capturePngEntriesForConfig(exportCfg, {
            pngEntries: zipEntries,
            usedZipEntryNames,
            baseDir: showDir,
            statusPrefix: `iPhone ${plan.iphoneNumber} ┬╖ Slideshow ${i + 1}: `,
            progressBase: Math.round((completedJobs / totalJobs) * 85),
            progressSpan: Math.max(1, 85 / totalJobs),
          });
          completedJobs++;
          setExportProgress(Math.round((completedJobs / totalJobs) * 90));
        }

        if (cancelGenRef.current) break;
        if (Object.keys(zipEntries).length === 0) continue;

        setExportStatus(`Building PNG ZIP ${plan.iphoneNumber} / ${zipPlans.length}ΓÇª`);
        const zipData = zipSync(zipEntries, { level: 1 });
        const blob = new Blob([zipData], { type: "application/zip" });
        triggerZipDownload(blob, `${zipFilePrefix}${String(plan.iphoneNumber).padStart(2, "0")}-${randomExportHex(10)}.zip`);
        downloadedZipCount++;
        await new Promise((r) => setTimeout(r, 650));
      }

      if (downloadedZipCount === 0) {
        setExportStatus("Nothing exported ΓÇö PNG ZIP export cancelled.");
      } else {
        setExportProgress(100);
        setExportStatus(`Done! Downloaded ${downloadedZipCount} iPhone PNG ZIPs.`);
      }
      return downloadedZipCount > 0;
    } catch (e) {
      console.error(e);
      setExportStatus("iPhone PNG ZIP export failed ΓÇö see console.");
      return true;
    } finally {
      flushSync(() => setConfig(restoreConfig));
      flushSync(() => setCurrentSlide(0));
      setIsExporting(false);
      setTimeout(() => {
        setExportStatus("");
        setExportProgress(0);
      }, 5000);
    }
  };

  const handleExportAllPNGs = async () => {
    const restoreConfig = {
      ...config,
      slots: (config.slots ?? []).map((s) => ({ ...s })),
    };
    const aid = config.appId ?? "thrifty";
    if (aid === "labely" || aid === "valcoin") {
      const gallery = savedSlideshows.filter((s) => savedShowMatchesApp(s, aid));
      if (await exportIphonePngZipPlans(gallery, restoreConfig)) return;
    }

    setIsExporting(true);
    setExportProgress(0);
    setExportStatus("Capturing slidesΓÇª");

    const pngEntries = {};
    const usedZipEntryNames = new Set();
    await capturePngEntriesForConfig(config, { pngEntries, usedZipEntryNames });

    if (Object.keys(pngEntries).length === 0) {
      setIsExporting(false);
      setExportStatus("Nothing to export.");
      return;
    }

    setExportStatus("Building ZIPΓÇª");
    setExportProgress(90);

    const { zipSync } = await import("fflate");
    const zipData = zipSync(pngEntries, { level: 1 });
    const blob = new Blob([zipData], { type: "application/zip" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `${randomExportHex(12)}.zip`;
    a.click();
    URL.revokeObjectURL(url);

    setIsExporting(false);
    setExportProgress(100);
    setExportStatus("Done! ZIP downloaded.");
    setTimeout(() => { setExportStatus(""); setExportProgress(0); }, 3000);
  };

  const runChosenExport = async () => {
    await handleExportVideo();
  };

  // Register the per-slide refresh handler so VideoPreview can trigger generation
  // No deps ΓÇö runs after every render to keep the latest closure registered
  useEffect(() => {
    registerRefreshSlide?.((slideIdx) => {
      const fmt = config.outputFormat ?? "standard";
      if (isLabelySingleSlideFormat(config)) {
        handleGenerateOne(0);
        return;
      }
      if (
        slideIdx === 0 &&
        fmt !== "posePerson" &&
        fmt !== "imessageMom" &&
        !isLabelyScanTourFormat(config)
      ) {
        handleGenerateAll();
      } else {
        const itemIdx = slideIndexToSlotIndex(slideIdx, config);
        if (itemIdx != null) handleGenerateOne(itemIdx);
      }
    });
  });

  return (
    <div className="space-y-5">

      <div className="space-y-3 -mt-1">
        <span className="text-muted-foreground text-xs font-semibold uppercase tracking-wider">Output format</span>
        {isLabely ? (
          <div className="callout px-3 py-2.5 text-[11px]">
            <div className="font-semibold text-foreground">Grocery intro + scan</div>
            <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
              {`Shelf intro, scan beam, then ${scanTourSlotCount(config)} Labely slides per video. Farm runs use the auto food plan (3 types ├ù unique Brave photos).`}
            </p>
          </div>
        ) : isValcoin ? (
          <div className="callout px-3 py-2.5 text-[11px]">
            <div className="font-semibold text-foreground">6-coin collage ΓåÆ scan ├ù6 ΓåÆ Valcoin slide-up</div>
            <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
              {`Opens on a 6-coin collage, then each coin gets a scan animation and the Valcoin app slides up ΓÇö same slide-up choreography as Labely. Coin photos come from Wikimedia Commons (public domain). Batch generate builds ${VALCOIN_IPHONE_PACK_TOTAL} slideshows (6 batches ├ù ${VALCOIN_IPHONE_SLIDESHOWS_PER_BATCH}) and auto-exports ${GALLERY_IPHONE_DEVICE_COUNT} iPhone ZIPs (${LABELY_DB_BATCH_COUNT} videos each), same folder layout as Labely.`}
            </p>
          </div>
        ) : (
        <div className="flex flex-col gap-2">
          {[
            { id: "standard", label: "Standard", sub: "Collage, then reveal + app per item" },
            { id: "appOnly", label: "App only", sub: "Collage, then app screenshots only (no reveal)" },
            { id: "imessageMom", label: "iMessage mom", sub: `iMessage ΓåÆ Voicemail ΓåÆ ${brand.appName} (3 slides, slot 1 only)` },
            { id: "posePerson", label: "Pose person", sub: "Six full-frame shots; hands OK on slide 1 only" },
            { id: "starterPack", label: "Starter pack", sub: `POV: you thrift full time ΓÇö 3 struggles + ${brand.appName} (5 sec)` },
          ].map(({ id, label, sub }) => (
            <button
              key={id}
              type="button"
              onClick={() => updateConfig("outputFormat", id)}
              className={`text-left rounded-xl border px-3 py-2 transition-all ${
                (config.outputFormat ?? "standard") === id
                  ? "choice-selected"
                  : "choice-default hover:border-foreground/20"
              }`}
            >
              <div className="text-xs font-semibold">{label}</div>
              <div className="text-[10px] text-muted-foreground/80 mt-0.5">{sub}</div>
            </button>
          ))}
        </div>
        )}

        {/* ΓöÇΓöÇ Starter Pack config ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
        {!isLabely && !isValcoin && (config.outputFormat ?? "standard") === "starterPack" && (
          <div className="callout p-3 flex flex-col gap-2">
            <div className="text-muted-foreground text-xs font-semibold">Starter Pack</div>
            <p className="text-muted-foreground/70 text-[10px] leading-relaxed">
              Headline stays static. Each of the 3 items + {brand.appName} dissolves in over 5 seconds.
              Use the image slots below to generate/upload photos for items 1ΓÇô3.
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={async () => {
                  setIsExporting(true);
                  setExportStatus("Generating starter pack textΓÇª");
                  const sp = await ensureStarterPackAutofill();
                  setExportStatus("Generating starter pack imagesΓÇª");
                  await ensureStarterPackImages(sp?.imagePrompts ?? sp?.items);
                  setIsExporting(false);
                  setExportStatus("");
                }}
                className="btn-ghost btn-primary-outline text-[11px] font-semibold"
              >
                Auto-generate (AI)
              </button>
              <span className="text-muted-foreground/70 text-[10px]">Generates a fresh headline, titles, and card images every time.</span>
            </div>
            {/* Headline */}
            <label className="text-muted-foreground text-[10px] font-semibold">Headline text</label>
            <textarea
              rows={2}
              value={config.starterPackHeadline ?? ""}
              onChange={(e) => updateConfig("starterPackHeadline", e.target.value)}
              placeholder="e.g. people with these hobbies have more aura than they know what to do with"
              className="w-full bg-background border border-border rounded-lg px-2 py-1.5 text-foreground text-xs placeholder:text-muted-foreground/60 resize-none focus:outline-none focus:border-ring"
            />
            {/* Item name overrides */}
            <label className="text-muted-foreground text-[10px] font-semibold mt-1">Item card titles (uses slot name if left blank)</label>
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex items-center gap-2">
                <span className="text-muted-foreground/70 text-[10px] w-10 shrink-0">Card {i + 1}</span>
                <input
                  type="text"
                  value={config.slots?.[i]?.itemName ?? ""}
                  onChange={(e) => updateSlot(i, { itemName: e.target.value })}
                  placeholder={`Item ${i + 1} name`}
                  className="flex-1 bg-background border border-border rounded-lg px-2 py-1 text-foreground text-xs placeholder:text-muted-foreground/60 focus:outline-none focus:border-ring"
                />
              </div>
            ))}
            <p className="text-muted-foreground/70 text-[10px]">Card 4 is always <span className="text-muted-foreground">{brand.appName}</span> (auto).</p>
          </div>
        )}

        {!isLabely && !isValcoin && (
        <div className="bg-muted/50 border border-border rounded-xl p-3">
          <div className="text-muted-foreground text-xs font-semibold mb-1">Pose format (optional)</div>
          <p className="text-muted-foreground/70 text-[10px] mb-2 leading-relaxed">
            Upload your own reference photos. The model matches pose and framing, then swaps in each item. Images are cycled by slot (1ΓåÆ2ΓåÆ3ΓÇªΓåÆ1). With <span className="text-muted-foreground">Pose person</span> selected, hands/arms are only allowed on the first generated slide; other slides stay hands-free.
          </p>
          <input
            type="file"
            accept={IMAGE_FILE_ACCEPT}
            multiple
            className="text-muted-foreground text-[11px] w-full file:mr-2 file:py-1.5 file:px-2 file:rounded-lg file:border-0 file:bg-muted file:text-foreground/80"
            onChange={(e) => {
              const files = [...e.target.files];
              e.target.value = "";
              if (!files.length) return;
              void (async () => {
                const results = await Promise.all(files.map((f) => tryFileToDisplayableDataUrl(f)));
                const list = results
                  .filter((r) => r.ok)
                  .map((r) => ({ id: `${Date.now()}-${Math.random()}`, dataUrl: r.dataUrl }));
                const bad = results.length - list.length;
                if (!list.length) {
                  alert("Could not read any of those images (try JPEG, PNG, or HEIC).");
                  return;
                }
                updateConfig("poseReferenceImages", [...(config.poseReferenceImages || []), ...list]);
                if (bad) console.warn("[pose refs] skipped", bad, "file(s)");
              })();
            }}
          />
          {(config.poseReferenceImages?.length ?? 0) > 0 && (
            <div className="mt-2 flex flex-wrap gap-2 items-center justify-between">
              <span className="text-muted-foreground text-[10px] font-medium">{config.poseReferenceImages.length} loaded</span>
              <button
                type="button"
                onClick={() => updateConfig("poseReferenceImages", [])}
                className="text-[10px] status-error hover:opacity-80 font-medium"
              >
                Clear all
              </button>
            </div>
          )}
        </div>
        )}

      </div>

      {/* ΓöÇΓöÇ iMessage Mom (Thrifty) ΓöÇΓöÇ */}
      {!isLabely && !isValcoin ? (
      <Section title="iMessage Mom" icon="≡ƒÆ¼">
        <div>
          <label className="text-muted-foreground/70 text-[10px] block mb-1">TikTok @ watermark</label>
          <input
            type="text"
            value={config.tiktokWatermark ?? ""}
            onChange={(e) => updateConfig("tiktokWatermark", e.target.value)}
            placeholder="@mom"
            className="w-full bg-muted/50 border border-border rounded-lg px-2.5 py-1.5 text-foreground text-xs focus:outline-none focus:border-ring placeholder:text-muted-foreground/40"
          />
        </div>
        <div className="mt-2">
          <label className="text-muted-foreground/70 text-[10px] block mb-1">Voicemail caller ID</label>
          <input
            type="text"
            value={config.voicemailDisplayNumber ?? ""}
            onChange={(e) => updateConfig("voicemailDisplayNumber", e.target.value)}
            placeholder="+1 (225) 427-8071"
            className="w-full bg-muted/50 border border-border rounded-lg px-2.5 py-1.5 text-foreground text-xs focus:outline-none focus:border-ring placeholder:text-muted-foreground/40"
          />
        </div>
      </Section>
      ) : null}

      {/* ΓöÇΓöÇ AI GENERATION (Thrifty/Labely) / Numista (Valcoin) ΓöÇΓöÇ */}
      <Section title={isValcoin ? "Coin photos" : "AI Generation"} icon={isValcoin ? "≡ƒ¬Ö" : "Γ£¿"}>
        {!isLabely && !isValcoin && (
        <div className="flex gap-2 mb-3">
          {[
            { id: "gpt-image-1", label: "GPT-Image-1.5", color: "choice-selected" },
            { id: "gemini",      label: "Gemini Flash",  color: "choice-selected" },
          ].map(({ id, label, color }) => {
            const isMom = (config.outputFormat ?? "standard") === "imessageMom";
            const imgs = isMom
              ? 1
              : isValcoin
                ? scanTourSlotCount(config)
                : 6;
            const sub = id === "gpt-image-1"
              ? `$${(0.015 * imgs).toFixed(2)}/slideshow`
              : `$${(0.07  * imgs).toFixed(2)}/slideshow`;
            return (
            <button
              key={id}
              onClick={() => setImageModel(id)}
              className={`flex-1 py-2 px-3 rounded-xl border text-xs font-semibold transition-all text-left ${
                imageModel === id ? color : "border-border bg-muted/50 text-muted-foreground/80 hover:text-muted-foreground"
              }`}
            >
              <span className="flex items-center gap-1.5">
                {imageModel === id && <span className="w-2 h-2 rounded-full bg-current inline-block" />}
                {label}
              </span>
              <span className={`block text-[10px] mt-0.5 font-normal ${imageModel === id ? "opacity-70" : "opacity-40"}`}>{sub} ┬╖ low quality</span>
            </button>
            );
          })}
        </div>
        )}

        <div className="callout px-3 py-2.5 text-xs">
          <div className="font-semibold">{isValcoin ? "Wikimedia Commons (no API key)" : "AI keys are managed on the server."}</div>
          <div className="mt-1 text-muted-foreground">
            {isLabely
              ? "Brave pack photos + GPT ingredient analysis. Shelf intro is AI-generated per video. Foods come from the built-in farm plan, not a manual list."
              : isValcoin
                ? "Free public-domain coin photos from Wikimedia Commons ΓÇö no API key required, no AI coin images."
                : "This deployment uses the Vercel environment variables for image generation and auto-title, so teammates can use the app without entering API keys here."}
          </div>
        </div>

        {isLabely ? (
          <div className="adv-section mt-3">
            <Label className="!mb-1">Farm food plan</Label>
            <p className="text-muted-foreground/70 text-[10px] mb-2 leading-relaxed">
              Each phone gets 3 videos ΓÇö one genre per video (e.g. chips, cereal, soda). All 3 scan slides in a video use brands from that same genre. Genres rotate daily from {`unhealthyAmericanFoods.js`}. Brave photos reuse per product name across phones.
            </p>
            {isLabely && config.labelyUseBraveImages !== false ? (
              <BraveSearchUsageBar enabled className="mb-2" />
            ) : null}
            {farmVideoGenrePlan.length > 0 ? (
              <ul className="text-[11px] text-foreground space-y-1 mb-2">
                {farmVideoGenrePlan.map(({ video, genre }) => (
                  <li key={video}>
                    <span className="text-muted-foreground">Video {video} ┬╖</span> {genre}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground text-[10px] mb-2">
                Video genres load when the farm job starts (Activity log shows them).
              </p>
            )}
            {isFarmAutomation && farmVideoGenrePlan.length > 0 ? (
              <p className="text-muted-foreground/60 text-[10px]">
                Est.{" "}
                <strong className="text-foreground/80">
                  ~{estimateBraveSearchesForFarm({
                    videoCount: numSlideshows,
                    scansPerVideo: config.labelyScanSlotCount || 3,
                    reuseByProduct: labelyBraveReusePhotos,
                    uniqueProductCount: farmUniqueProductCount,
                  }).toLocaleString()}
                </strong>{" "}
                Brave searches
                {labelyBraveReusePhotos && farmUniqueProductCount
                  ? ` (${farmUniqueProductCount} unique products ΓÇö same photo when a name repeats)`
                  : ` (${numSlideshows} videos ├ù ${config.labelyScanSlotCount || 3} scans)`}
                .
              </p>
            ) : null}
          </div>
        ) : null}

        {mounted && !isLabely && !isValcoin && (
        <div className={`mt-3 flex items-center gap-2 rounded-lg px-3 py-2 text-xs ${
          referenceImages === null ? "callout text-muted-foreground/70"
          : referenceImages.length > 0 ? "callout status-success"
          : "callout text-muted-foreground/70"
        }`}>
          <span>{referenceImages === null ? "ΓÅ│" : referenceImages.length > 0 ? "≡ƒû╝∩╕Å" : "≡ƒôé"}</span>
          {referenceImages === null ? (
            <span>Loading reference photosΓÇª</span>
          ) : referenceImages.length > 0 ? (
            <span>
              <strong>{referenceImages.length}</strong> reference photo{referenceImages.length > 1 ? "s" : ""} in{" "}
              <code className="text-muted-foreground">{referencesDirLabel}</code>
              {" "}ΓÇö used as the style reference for AI generations.
            </span>
          ) : (
            <span>
              Add a PNG/JPEG to{" "}
              <code className="text-muted-foreground">{referencesDirLabel}</code>
              {" "}(e.g. messy clothes in a blue cart) to lock the buggy aesthetic.
            </span>
          )}
        </div>
        )}

        {!isLabely && !isValcoin ? (
          <div className="adv-section mt-3">
            <div className="flex items-center justify-between gap-2 mb-1">
              <Label className="!mb-0">Brand items list</Label>
              {mounted && brandItems.length > 0 ? (
                <span className="text-muted-foreground text-[10px] font-medium">
                  {brandItems.length} item{brandItems.length > 1 ? "s" : ""}
                </span>
              ) : null}
            </div>
            <p className="text-muted-foreground/70 text-[10px] mb-2 leading-relaxed">
              One garment per line. Generate picks from this list for each AI slot.
            </p>
            <textarea
              value={brandItemsRaw}
              onChange={(e) => {
                setBrandItemsRaw(e.target.value);
                localStorage.setItem(storeKey("ts_brand_items"), e.target.value);
              }}
              placeholder={"vintage Carhartt double-knee pants\nSupreme box logo hoodie\nvintage Levi's 501\nKapital boro jacket\nvintage Nike windbreaker"}
              rows={5}
              className="w-full rounded-lg border bg-background px-2.5 py-2 text-foreground text-xs focus:outline-none focus:border-ring placeholder:text-muted-foreground/40 resize-none"
            />
          </div>
        ) : null}

        <div className="mt-4">
          <div className="mb-2 flex items-center gap-2">
            <span className="flex-1 text-xs font-semibold text-foreground">Generate slideshows</span>
            {!isValcoinIphonePackBatchMode ? (
            <div className="flex items-center gap-1.5">
              <span className="text-muted-foreground/70 text-[11px]">Qty</span>
              <input
                type="number" min={1} max={120}
                value={numSlideshows}
                onChange={(e) => setNumSlideshows(Math.max(1, Math.min(120, Number(e.target.value))))}
                className="w-14 rounded-lg border bg-background px-2 py-1 text-foreground text-sm text-center focus:outline-none focus:border-ring"
              />
            </div>
            ) : (
              <span className="text-[11px] font-semibold text-foreground">
                {effectiveNumSlideshows} total
                {isValcoinIphonePackBatchMode ? ` ┬╖ ${LABELY_DB_BATCH_COUNT}├ù${VALCOIN_IPHONE_SLIDESHOWS_PER_BATCH} iPhone pack` : ""}
              </span>
            )}
          </div>
          <button
            onClick={handleGenerateBatch}
            disabled={
              generatingSlot !== null
              || (!isLabely && !isValcoin && brandItems.length === 0)
            }
            className="btn-primary w-full disabled:opacity-40"
          >
            {generatingSlot === "all" ? "GeneratingΓÇª" : `Generate ${effectiveNumSlideshows} slideshow${effectiveNumSlideshows > 1 ? "s" : ""}`}
          </button>
          {!isLabely && !isValcoin ? (
          <p className="mt-1.5 text-center text-[10px] text-muted-foreground/60">
            {(() => {
              const isMom = (config.outputFormat ?? "standard") === "imessageMom";
              const imgs = isMom ? 1 : 6;
              const cost = imageModel === "gpt-image-1" ? 0.015 * imgs : 0.07 * imgs;
              return `Est. $${(effectiveNumSlideshows * cost).toFixed(2)} ┬╖ each saved to the gallery on the right`;
            })()}
          </p>
          ) : null}
        </div>

        {/* Progress tracker */}
        {genAllProgress && (
          <div className="adv-section mt-3 space-y-2">
            {genAllProgress.slotsDone && (
              <div className="flex gap-1.5 justify-center">
                {Array.from({ length: config.slots.length }).map((_, i) => {
                  const done = genAllProgress.slotsDone.has(i);
                  const active = !done && i === genAllProgress.current;
                  return (
                    <div key={i} className={`relative flex items-center justify-center rounded-full transition-all
                      ${done ? "w-7 h-7 bg-foreground" : active ? "w-7 h-7 bg-foreground/50 ring-2 ring-foreground" : "w-7 h-7 bg-muted"}`}>
                      {done ? (
                        <svg className="w-3.5 h-3.5 text-background" fill="none" viewBox="0 0 10 10" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M1.5 5l2.5 2.5 4.5-5" />
                        </svg>
                      ) : active ? (
                        <div className="w-2.5 h-2.5 border-2 border-muted-foreground border-t-transparent rounded-full animate-spin" />
                      ) : (
                        <span className="text-muted-foreground/70 text-[10px] font-bold">{i + 1}</span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Progress bar */}
            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-foreground rounded-full transition-all duration-500"
                style={{
                  width: `${Math.min(100, ((Number(genAllProgress.done) || 0) / Math.max(1, Number(genAllProgress.total) || 1)) * 100)}%`,
                }}
              />
            </div>

            {/* Status text */}
            <p className="text-muted-foreground text-xs text-center">{genAllProgress.phase}</p>
          </div>
        )}
      </Section>

      {/* ΓöÇΓöÇ VIDEO SETTINGS ΓöÇΓöÇ */}
      <Section title="Video Settings" icon="≡ƒÄ¼">
        <div className="flex items-center gap-3">
          <Label className="shrink-0">Slide duration</Label>
          <input type="range" min={1} max={8} step={0.5} value={config.slideDuration}
            onChange={(e) => updateConfig("slideDuration", Number(e.target.value))}
            className="flex-1 accent-foreground" />
          <span className="text-foreground text-sm w-8 text-right shrink-0">{config.slideDuration}s</span>
        </div>
      </Section>

      {/* ΓöÇΓöÇ EXPORT ΓöÇΓöÇ */}
      <div className="space-y-2 pb-8">
        <h3 className="text-muted-foreground text-xs uppercase tracking-widest font-bold mb-3">Export</h3>

        {(isExporting || exportStatus) && (
          <div className="mb-3">
            <div className="flex justify-between text-xs text-muted-foreground mb-1">
              <span>{exportStatus || "ExportingΓÇª"}</span>
              <span>{exportProgress}%</span>
            </div>
            <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
              <div className="h-full bg-foreground rounded-full transition-all duration-200" style={{ width: `${exportProgress}%` }} />
            </div>
          </div>
        )}

        <button
          type="button"
          onClick={() => void runChosenExport()}
          disabled={isExporting}
          className="btn-primary w-full disabled:opacity-40"
        >
          {isExporting ? "ExportingΓÇª" : "Export MP4"}
        </button>

        <p className="text-center text-xs text-muted-foreground/60">
          {totalSlides} slides ┬╖ {(config.slideDuration * totalSlides).toFixed(0)}s+ ┬╖ 1080├ù1920
        </p>
      </div>
    </div>
  );
}

// ΓöÇΓöÇ Shared UI ΓöÇΓöÇ
function Section({ title, icon, children }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <span>{icon}</span>
        <h3 className="text-foreground font-semibold text-sm">{title}</h3>
      </div>
      {children}
      <div className="mt-5 border-b border-border" />
    </div>
  );
}
function Label({ children, className = "" }) {
  return <label className={`block text-muted-foreground text-xs mb-1 ${className}`}>{children}</label>;
}
function Input({ value, onChange, placeholder }) {
  return (
    <input type="text" value={value} onChange={onChange} placeholder={placeholder}
      className="w-full bg-background border border-border rounded-lg px-2.5 py-1.5 text-foreground text-xs focus:outline-none focus:border-ring placeholder:text-muted-foreground/40" />
  );
}
function Textarea({ value, onChange, placeholder, rows = 2 }) {
  return (
    <textarea value={value} onChange={onChange} placeholder={placeholder} rows={rows}
      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground text-sm focus:outline-none focus:border-ring placeholder:text-muted-foreground/40 resize-none" />
  );
}
