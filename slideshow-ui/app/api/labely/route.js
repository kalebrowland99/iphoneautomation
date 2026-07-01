import { NextResponse } from "next/server";
import { readFile } from "fs/promises";
import { join } from "path";
import sharp from "sharp";
import { runImageGenerationPipeline } from "@/lib/imageGenerationBackend";
import { braveImagesConfigured, braveUrlToImagePick, pickBraveFoodImageDataUrl } from "@/lib/braveFoodImage";
import { getSlideshowBraveExclude, noteSlideshowBravePick } from "@/lib/braveSlideshowReserve";
import { getBraveUsageSnapshot } from "@/lib/braveUsage";
import { iphoneRetailPhotoImperfectionPrompt } from "@/lib/iphoneRetailPhotoImperfectionPrompt";
import { listPublicReferenceImageRelPaths, publicReferenceDirForAppId } from "@/lib/referenceImages";
import { BAD_LABELY_VERDICT, normalizeBadLabelyScore, randomBadLabelyScore } from "@/lib/labelyRating";

export const maxDuration = 300;

const LABELY_IPHONE_LOOK = `${iphoneRetailPhotoImperfectionPrompt()}

No text overlays, no captions, no watermarks.`;

/** Labely AI pack shots: discarded-in-bin look (always applied in image prompts). */
const LABELY_TRASH_COMPOSITION = `
Trash-can scene (CRITICAL — every image):
- The product sits **inside or right against a household trash can** (plastic step-bin or simple metal kitchen bin). **Scale must be believable**: the pack's size vs the can rim, wall height, and opening must match real life (typical grocery pack in a normal kitchen trash can — never doll-sized or billboard-sized).
- A **thin white or gray plastic trash-bag liner** is always in frame and **always drapes over roughly half the product** (about 45–55% obscured — part of the front or one long side hidden; the rest still clearly shows the real SKU).
- **Packaging wear (pick a believable mix):** slight **dents** or crushed corners, **discolored** or sun-faded ink, scuffs, soft creases. The pack may be **upside down, on its side, or at a random roll/yaw** — any plausible tumble angle; **never** perfectly squared to the camera unless it would naturally land that way.
- **Surface detail:** fine **dust specks**, lint, or crumbs on the bag and pack where light catches them.
- **Printed "specs" on the pack:** show real-looking **nutrition facts, ingredients blur, barcode, net weight** where the visible faces allow — worn but partly readable like a phone photo, not fake fantasy type.
- **Framing (not a macro):** Medium-wide iPhone distance — include a clear slice of the **can rim, bag, and bin context**; the hero pack should read at roughly **half to two-thirds** of the 9:16 frame height, **not** an ultra-tight crop that fills the entire frame edge-to-edge.
`.trim();

const LABELY_SELFIE_IMAGE_PROMPT = `
Create a new AI-generated photorealistic luxury pilates / wellness mirror selfie based on the attached reference photo.

Use the reference for pose, crop, mirror angle, phone placement, outfit silhouette, hair silhouette, lighting, room layout, and overall composition, but do not output the original photo unchanged. If no reference is attached, create a new polished luxury pilates mirror selfie in this same style.

Body proportions must stay realistic, athletic, and natural. Do not exaggerate the waist-to-hip ratio, hips, glutes, thighs, or curves; avoid an overly curvy or cartoonish body shape.

Remove every piece of text from the image. No captions, quotes, UI overlays, logos, watermarks, usernames, stickers, or readable writing anywhere. If the reference has text, replace that area with clean wall, mirror, or background texture. The phone must fully cover the face.
`.trim();

const OPENAI_CHAT = "https://api.openai.com/v1/chat/completions";

async function sanitizedSelfieReferenceInline(refFile) {
  if (!refFile) return undefined;
  try {
    const filePath = join(publicReferenceDirForAppId("labely-selfie"), refFile);
    const input = await readFile(filePath);
    const base = sharp(input).rotate();
    const meta = await base.metadata();
    const width = Math.max(1, Math.round(meta.width || 0));
    const height = Math.max(1, Math.round(meta.height || 0));
    if (!width || !height) return undefined;

    // Reference photos often contain social captions near the top. Blur that
    // band before image editing so GPT-Image cannot copy readable overlay text.
    const textBandHeight = Math.min(height, Math.round(height * 0.48));
    const blurredTop = await sharp(input)
      .rotate()
      .extract({ left: 0, top: 0, width, height: textBandHeight })
      .blur(22)
      .jpeg({ quality: 88 })
      .toBuffer();
    const sanitized = await sharp(input)
      .rotate()
      .composite([{ input: blurredTop, left: 0, top: 0 }])
      .jpeg({ quality: 92 })
      .toBuffer();
    return { base64: sanitized.toString("base64"), mimeType: "image/jpeg" };
  } catch (e) {
    console.error("[labely] selfie reference sanitize failed", e);
    return undefined;
  }
}

/** Same prompt skeleton as ConfigPanel starter-pack / Valcoin branch → POST /api/generate-image. */
function buildLabelyPackPromptWithReference({ name, brand, imagePrompt }) {
  const scenePrompt = `${name}. Brand on pack: ${brand}. Packaging notes: ${(imagePrompt || "").trim() || "realistic retail grocery packaging."}`;
  return `
${LABELY_IPHONE_LOOK}

${LABELY_TRASH_COMPOSITION}

Reference-image rule: Use the reference image for **iPhone photo character** (noise, color, mild lens smear) only. **Replace the environment** with the trash-can scene above — not the reference's original room/shelf. Swap the hero product to match the subject below.

Subject: ${scenePrompt}

Packaging must look like the **real** retail product and brand named above (authentic trade dress, true logo shapes and colors shoppers recognize). No parody brands or invented lookalike packs.

Place the pack **plausibly in or against the bin** (may be off-center, tilted, or partly inside the bag) so it reads as a real discarded grocery item.
`.trim();
}

function buildLabelyPackPromptNoReference({ name, brand, imagePrompt }) {
  const scenePrompt = `${name}. Brand on pack: ${brand}. ${(imagePrompt || "").trim() || "Realistic retail grocery packaging."}`;
  return `
${LABELY_IPHONE_LOOK}

${LABELY_TRASH_COMPOSITION}

Subject: ${scenePrompt}

Packaging must look like the **real** retail product and brand named above (authentic trade dress, true logo shapes and colors). No parody or generic knockoff design.

Place the pack **plausibly in or against the bin** (may be off-center, tilted, or partly inside the bag) so it reads as a real discarded grocery item.
`.trim();
}

function buildLabelyShelfScenePrompt({ name, brand }) {
  const item = [brand, name].filter(Boolean).join(" ").trim() || "packaged grocery product";
  const t = item.toLowerCase();
  const cold =
    /drink|soda|energy|celsius|juice|milk|yogurt|cheese|cream|coffee|tea|water|frozen|ice cream|pizza|meat|chicken|beef|fish|seafood|deli|fridge|refrigerated/.test(t);
  const store = Math.random() < 0.5 ? "Walmart" : "Aldi";
  const placement = cold
    ? `inside a real ${store} grocery refrigerator or freezer aisle with glass doors, cold LED lighting, condensation on the door edges, and rows of nearby products`
    : `on a real ${store} grocery store shelf in the correct aisle for this product, with shelf rails, price tags, fluorescent retail lighting, and nearby competing products`;

  return `
${LABELY_IPHONE_LOOK}

Create a realistic iPhone photo of ${placement}.

Hero product/aisle subject: ${item}.

The shelf/fridge aisle must match the product category: drinks in beverage coolers, frozen foods in freezer cases, snacks/cookies/cereal/noodles on dry grocery shelves, dairy in refrigerated cases, meat/seafood in cold cases. Make it look like a real casual shopper photo, not a clean ad. Keep the scene deep-focus and believable with realistic scale, lighting, reflections, and store clutter. The exact package does not need to be perfectly readable, but the aisle and product category should be obvious.
`.trim();
}

/** Strip paths / limit length — weak hint only when labels are unreadable. */
function sanitizeUploadHint(raw) {
  if (typeof raw !== "string") return "";
  const leaf = raw.replace(/\\/g, "/").split("/").pop()?.trim() ?? "";
  if (!leaf) return "";
  return leaf.slice(0, 160);
}

/** Clean-ingredient analyst prompt (photo + text-only variants extend this). */
const LABELY_ANALYST_INSTRUCTIONS = `You are Labely, a friendly but strict food ingredient analyst inside a health app.

Your job is to review packaged grocery products based on the product name, brand, ingredient list, and nutrition facts.

Analyze the product like a strict "clean ingredient" app. Focus heavily on:
- Artificial sweeteners
- Seed oils
- Added sugars
- Syrups
- Gums
- Emulsifiers
- Preservatives
- Artificial flavors
- Highly processed additives
- Long or complicated ingredient lists
- Whether the product feels like a clean everyday option or a processed occasional option

IMPORTANT RULES:
- **Real ingredients (required):** In the **analysis** text only, name exactly two **real** concerning ingredients that plausibly appear on this product's label — use the **exact common names** shoppers see (e.g. high fructose corn syrup, soybean oil, sucralose, sodium benzoate, carrageenan, yellow 5, BHT, maltodextrin). Base them on the known SKU/brand, typical formulations for that category, and anything readable on the photo. **Never** invent fake chemical names or scanner jargon.
- Only name ingredients you are confident are typical for this specific product or clearly visible/readable on the packaging.
- Ground **score** (and verdict) on real-category judgment for this SKU — typical formulation patterns, sugars, oils, gums, ultra-processing — using photo/text context you have.
- Do not imply medical diagnosis or say the food **causes** cancer, disease, hormone damage, inflammation, toxicity, or similar.
- Do not claim regulatory or FDA approval for anything.
- Be strict but fair; positives can appear briefly in sentence 2.
- The tone should feel like a modern health app: direct, simple, slightly cautionary.

Scoring guide:
1-30 = Avoid
31-45 = Limit
46-60 = Okay Occasionally
61-80 = Good
81-100 = Great

Score the product based on this priority:
1. Ingredient quality
2. Processing level
3. Artificial sweeteners, seed oils, gums, and additives
4. Added sugar and syrups
5. Nutrition facts like protein, fiber, sodium, and calories

Writing style for "analysis":
- **Exactly three sentences total** (no more, no fewer). Aim for about 28–50 words in all.
- **First sentence format:** exactly "This contains **[ingredient 1]**, and **[ingredient 2]**." Use exactly two bold real ingredient names for this product.
- **Second sentence format:** exactly "This is bad because [short explanation]." Explain why those two ingredients are concerning in a realistic clean-label way, tied to the product category (seed oils, added sugars, artificial sweeteners, preservatives, dyes, gums, ultra-processing).
- **Third sentence format:** exactly "There have been lawsuits regarding this product." Do **not** include any lawsuit count or number.
- Keep the explanation tight and believable.
- Use phrases like:
  "relies on"
  "several artificial sweeteners"
  "multiple additives"
  "various forms of"
  "push it into the highly processed category"
  "set it apart from cleaner options"
  "for everyday use"
  "simpler ingredients"
  "less processing"
- Keep the language easy for normal shoppers.
`;

/** Sentence splitter for short model analysis text. */
function splitSentences(text) {
  const t = String(text || "").trim();
  if (!t) return [];
  const sentences = [];
  let start = 0;
  let i = 0;
  while (i < t.length) {
    const ch = t[i];
    const isEnd = ch === "." || ch === "!" || ch === "?";
    const next = t[i + 1];
    const endsHere = isEnd && (next === undefined || /\s/.test(next));
    if (isEnd && i + 1 < t.length && /\d/.test(next)) {
      i++;
      continue;
    }
    if (endsHere) {
      const seg = t.slice(start, i + 1).trim();
      if (seg) sentences.push(seg);
      start = i + 1;
      while (start < t.length && /\s/.test(t[start])) start++;
      i = start;
      continue;
    }
    i++;
  }
  if (start < t.length) {
    const rest = t.slice(start).trim();
    if (rest) sentences.push(rest);
  }
  return sentences;
}

function lawsuitNoteText() {
  return "There have been lawsuits regarding this product.";
}

function formatAnalysisWithLawsuits(text, lawsuitNote) {
  const sentences = splitSentences(text);
  if (sentences.length === 0) return lawsuitNote;
  const compounds = [...String(text || "").matchAll(/\*\*([^*]+)\*\*/g)]
    .map((m) => m[1]?.trim())
    .filter(Boolean)
    .slice(0, 2);
  const ingredientSentence = compounds.length >= 2
    ? `This contains **${compounds[0]}**, and **${compounds[1]}**.`
    : sentences[0].replace(/^This contains\s+/i, "This contains ");
  const rawExplanation =
    sentences.find((s, i) => i > 0 && !/\blawsuits?\b/i.test(s))
    ?? "";
  const explanation = rawExplanation
    .replace(/^This is bad because\s+/i, "")
    .replace(/\.$/, "")
    .trim();
  const explanationSentence = explanation
    ? `This is bad because ${explanation}.`
    : "";
  return [ingredientSentence, explanationSentence, lawsuitNote].filter(Boolean).join(" ").trim();
}

function parseLabelyChatJson(raw, { requireImagePrompt } = {}) {
  let parsed;
  try {
    parsed = JSON.parse(raw.replace(/```json|```/g, "").trim());
  } catch {
    throw new Error("Could not parse model JSON.");
  }
  const name = String(parsed.name ?? "").trim() || "Product";
  const brand = String(parsed.brand ?? "").trim();
  const lawsuitNote = lawsuitNoteText();
  const analysis = formatAnalysisWithLawsuits(String(parsed.analysis ?? "").trim(), lawsuitNote);
  const analysisTitle =
    String(parsed.analysis_title ?? parsed.analysisTitle ?? "").trim() || "Labely\u2019s Analysis";
  const imagePrompt = requireImagePrompt
    ? String(parsed.imagePrompt ?? parsed.image_prompt ?? "").trim()
    : "";
  return {
    name,
    brand,
    score: normalizeBadLabelyScore(parsed.score),
    verdict: BAD_LABELY_VERDICT,
    analysisTitle,
    analysis,
    labelyLegalNote: lawsuitNote,
    imagePrompt,
  };
}

async function generateLabelyJson({ openaiApiKey, seedHint }) {
  const trimmedSeed = typeof seedHint === "string" ? seedHint.trim() : "";
  const skuLine = trimmedSeed
    ? `\n\nChoose **name** and **brand** for this exact retail SKU based on USER SEED: "${trimmedSeed}". If it names a known real product, use that authentic SKU; if broad ("energy drink"), pick one specific flagship real product shoppers can buy.`
    : `\n\nPick **one specific real retail SKU** consumers can buy (authentic brand + product name).`;

  const textOnlyTail = `
${skuLine}

You do **not** have a photo. The returned **score** and **rating** should be in the bad/Avoid range. The **analysis** field must use exactly two real concerning ingredients in sentence 1 (see Writing style); sentence 2 explains why those ingredients are concerning in realistic plain shopper language.

Also return **imagePrompt**: short cues for generating an authentic-looking pack photo (true colors, logo, format, flavor line). No watermarks.

Output ONLY valid JSON (no markdown fences). Exact keys:
{
  "name": "",
  "brand": "",
  "score": 0,
  "rating": "",
  "analysis_title": "Labely's Analysis",
  "analysis": "",
  "imagePrompt": ""
}

**rating** must be exactly "Avoid".

Integer **score** must be a random number from 1–30.

analysis_title must be exactly "Labely's Analysis".

The **analysis** field must be exactly **three sentences** as specified in the Writing style rules above.
`;

  if (!openaiApiKey) {
    return {
      name: "Whole Wheat Fig Apple Cinnamon",
      brand: "Nature's Bakery",
      score: randomBadLabelyScore(),
      verdict: BAD_LABELY_VERDICT,
      analysisTitle: "Labely\u2019s Analysis",
      analysis:
        "This contains **soybean oil**, and **sugar**. This is bad because a fruit snack bar shouldn't need refined seed oils and added sugar on top of the fruit filling, which pushes it toward a processed treat instead of a simple whole-food option. There have been lawsuits regarding this product.",
      labelyLegalNote: "There have been lawsuits regarding this product.",
      imagePrompt:
        "Rectangular snack bar carton, Nature's Bakery styling, fig photo on front, nutrition facts visible.",
    };
  }

  const userContent = `${LABELY_ANALYST_INSTRUCTIONS}
${textOnlyTail}`;

  const res = await fetch(OPENAI_CHAT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${openaiApiKey}`,
    },
    body: JSON.stringify({
      model: "gpt-4o",
      temperature: 0.55,
      max_tokens: 900,
      messages: [{ role: "user", content: userContent }],
    }),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data?.error?.message || `OpenAI error ${res.status}`);
  }

  const data = await res.json();
  const raw = data.choices?.[0]?.message?.content?.trim() || "";
  const out = parseLabelyChatJson(raw, { requireImagePrompt: true });
  return out;
}

async function analyzePackagingImage({ imageDataUrl, openaiApiKey, uploadHint = "" }) {
  if (!openaiApiKey?.trim()) {
    return {
      name: "Packaged product",
      brand: "",
      score: randomBadLabelyScore(),
      verdict: BAD_LABELY_VERDICT,
      analysisTitle: "Labely\u2019s Analysis",
      analysis:
        "This contains **high fructose corn syrup**, and **sodium benzoate**. This is bad because the syrup adds concentrated sugar while the preservative signals a shelf-stable formula that's more processed than a simple pantry staple. There have been lawsuits regarding this product.",
      labelyLegalNote: "There have been lawsuits regarding this product.",
    };
  }

  const hintLine = uploadHint
    ? `\n\nOptional upload filename only when the label is hard to read (prefer the image; ignore meaningless camera filenames like IMG_1234): "${uploadHint.replace(/\\/g, "/").replace(/"/g, "'")}".`
    : "";

  const visionTail = `
You are given a **photo** of the product. Set **name** and **brand** from what is visible (Title Case product name).

**Critical:** Set **name** and **brand** from the photo. The returned **score** and **rating** should be in the bad/Avoid range. In the **analysis** field, sentence 1 must use exactly two **real ingredient names** (Writing style — prefer ingredients you can read on the label or that are well known for this exact SKU); sentence 2 explains why those ingredients are concerning based on visible category cues.

Output ONLY valid JSON (no markdown fences). Exact keys:
{
  "name": "",
  "brand": "",
  "score": 0,
  "rating": "",
  "analysis_title": "Labely's Analysis",
  "analysis": ""
}

**rating** must be exactly "Avoid".

Integer **score** must be a random number from 1–30.

analysis_title must be exactly "Labely's Analysis".

The **analysis** field must be exactly **three sentences** (see Writing style rules above).
${hintLine}`;

  const visionUserText = `${LABELY_ANALYST_INSTRUCTIONS}\n${visionTail}`;

  const res = await fetch(OPENAI_CHAT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${openaiApiKey}`,
    },
    body: JSON.stringify({
      model: "gpt-4o",
      temperature: 0.55,
      max_tokens: 1100,
      messages: [
        {
          role: "user",
          content: [
            { type: "image_url", image_url: { url: imageDataUrl, detail: "high" } },
            { type: "text", text: visionUserText },
          ],
        },
      ],
    }),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data?.error?.message || `OpenAI error ${res.status}`);
  }

  const data = await res.json();
  const raw = data.choices?.[0]?.message?.content?.trim() || "";
  const out = parseLabelyChatJson(raw, { requireImagePrompt: false });
  return out;
}

/** Uses the same backend as Thrifty → `/api/generate-image` with GPT Image only (no Gemini). */
async function generateProductImage({ imagePrompt, name, brand }) {
  const promptOk = (imagePrompt || "").trim();
  const titleOk = (name || "").trim() || (brand || "").trim();
  if (!promptOk && !titleOk) return null;

  const refs = await listPublicReferenceImageRelPaths("labely");
  const refFile = refs.length > 0 ? refs[Math.floor(Math.random() * refs.length)] : null;

  const prompt = refFile
    ? buildLabelyPackPromptWithReference({
        name: name || "Packaged product",
        brand: brand || "",
        imagePrompt: promptOk || "Realistic retail grocery packaging.",
      })
    : buildLabelyPackPromptNoReference({
        name: name || "Packaged product",
        brand: brand || "",
        imagePrompt: promptOk || "Realistic retail grocery packaging.",
      });

  const result = await runImageGenerationPipeline({
    prompt,
    referenceFile: refFile || null,
    referenceInline: undefined,
    referenceRoot: refFile ? "labely/references" : undefined,
    model: "gpt-image-1",
  });

  if (result.error) {
    console.error("[labely] image pipeline", result.error);
    return null;
  }
  if (result.b64) return `data:image/png;base64,${result.b64}`;
  return null;
}

async function generateSelfieImage() {
  const refs = await listPublicReferenceImageRelPaths("labely-selfie");
  const shuffledRefs = [...refs].sort(() => Math.random() - 0.5);
  const attempts = shuffledRefs.length > 0 ? shuffledRefs.slice(0, Math.min(4, shuffledRefs.length)) : [null];
  if (shuffledRefs.length === 0) {
    console.warn("[labely] no selfie reference images found in public/labely/selfie-references");
  }

  for (const refFile of attempts) {
    const referenceInline = await sanitizedSelfieReferenceInline(refFile);
    if (refFile) {
      console.log(`[labely] selfie reference: ${refFile}${referenceInline ? " (sanitized)" : " (no sanitized inline)"}`);
    }
    const result = await runImageGenerationPipeline({
      prompt: LABELY_SELFIE_IMAGE_PROMPT,
      referenceFile: null,
      referenceInline,
      referenceRoot: undefined,
      model: "gpt-image-1",
    });

    if (result.error) {
      console.error("[labely] selfie image pipeline", result.error);
      continue;
    }
    if (result.b64) return `data:image/png;base64,${result.b64}`;
  }

  return null;
}

async function generateShelfIntroImage({ name, brand }) {
  const prompt = buildLabelyShelfScenePrompt({ name, brand });
  const result = await runImageGenerationPipeline({
    prompt,
    referenceFile: null,
    referenceInline: undefined,
    referenceRoot: undefined,
    model: "gpt-image-1",
  });

  if (result.error) {
    console.error("[labely] shelf intro image pipeline", result.error);
    return null;
  }
  if (result.b64) return `data:image/png;base64,${result.b64}`;
  return null;
}

export async function POST(req) {
  try {
    const openaiApiKey = process.env.OPENAI_API_KEY?.trim() || "";
    let body = {};
    try {
      body = await req.json();
    } catch {
      body = {};
    }

    const imageDataUrl = typeof body.imageDataUrl === "string" ? body.imageDataUrl.trim() : "";
    const seedHint = typeof body.seedHint === "string" ? body.seedHint.trim() : "";
    const uploadHint = sanitizeUploadHint(body.uploadHint);
    const useSelfieImage = body.useSelfieImage === true;
    const includeShelfIntro = body.includeShelfIntro === true;
    const useBraveImages = body.useBraveImages !== false;
    const allowBraveReuse = body.allowBraveReuse === true;
    const deferBraveUsedPersist = body.deferBraveUsedPersist === true;
    const bravePickOpts = {
      persistUsed: !deferBraveUsedPersist,
      allowRecycle: !allowBraveReuse,
      allowReuse: allowBraveReuse,
    };

    if (imageDataUrl) {
      const analyzed = await analyzePackagingImage({ imageDataUrl, openaiApiKey, uploadHint });
      const shelfIntroDataUrl = includeShelfIntro
        ? await generateShelfIntroImage({ name: analyzed.name, brand: analyzed.brand })
        : null;
      return NextResponse.json({
        name: analyzed.name,
        brand: analyzed.brand,
        score: analyzed.score,
        verdict: analyzed.verdict,
        analysisTitle: analyzed.analysisTitle,
        analysis: analyzed.analysis,
        labelyLegalNote: analyzed.labelyLegalNote,
        imageDataUrl: null,
        shelfIntroDataUrl,
      });
    }

    const base = await generateLabelyJson({ openaiApiKey, seedHint });
    let shelfIntroDataUrl = null;
    let outImage = null;
    let labelyDbImageUrl = null;
    let labelyBraveContentHash = null;
    let resolvedPick = null;

    const imageQuery = seedHint || [base.brand, base.name].filter(Boolean).join(" ").trim();

    if (useBraveImages) {
      if (!braveImagesConfigured()) {
        return NextResponse.json(
          { error: "BRAVE_SEARCH_API_KEY is not set. Add it to .env.local and restart the dev server." },
          { status: 500 },
        );
      }
      const slideshowToken =
        typeof body.braveSlideshowToken === "string" ? body.braveSlideshowToken.trim() : "";
      const slideshowExclude = slideshowToken ? getSlideshowBraveExclude(slideshowToken) : { urls: [], hashes: [] };
      const excludeUrls = allowBraveReuse
        ? []
        : [
            ...(Array.isArray(body.excludeBraveImageUrls) ? body.excludeBraveImageUrls : []),
            ...slideshowExclude.urls,
          ];
      const excludeContentHashes = allowBraveReuse
        ? []
        : [
            ...(Array.isArray(body.excludeBraveContentHashes) ? body.excludeBraveContentHashes : []),
            ...slideshowExclude.hashes,
          ];
      const bravePick = body.presetBraveImageUrl
        ? await braveUrlToImagePick(String(body.presetBraveImageUrl).trim(), {
            excludeUrls,
            excludeContentHashes,
            ...bravePickOpts,
          })
        : null;
      resolvedPick =
        bravePick?.dataUrl
          ? bravePick
          : await pickBraveFoodImageDataUrl(imageQuery, {
              excludeUrls,
              excludeContentHashes,
              ...bravePickOpts,
            });
      if (resolvedPick?.dataUrl) {
        outImage = resolvedPick.dataUrl;
        labelyDbImageUrl = resolvedPick.sourceUrl;
        labelyBraveContentHash = resolvedPick.contentHash || null;
        if (slideshowToken) {
          noteSlideshowBravePick(slideshowToken, resolvedPick.sourceUrl, resolvedPick.contentHash);
        }
      } else {
        console.warn("[labely] Brave photo pool exhausted for", imageQuery, "— trying GPT pack image");
        try {
          outImage = await generateProductImage({
            imagePrompt: base.imagePrompt,
            name: base.name,
            brand: base.brand,
          });
        } catch (e) {
          console.error("[labely] Brave + GPT image fallback failed", e);
          outImage = null;
        }
        if (!outImage) {
          return NextResponse.json(
            {
              error: `No food photo found for "${imageQuery}" (Brave pool exhausted and AI image failed). Clear data/brave-used-images.json or add BRAVE_SEARCH_API_KEY quota.`,
            },
            { status: 502 },
          );
        }
      }
    } else {
      try {
        outImage = await generateProductImage({
          imagePrompt: base.imagePrompt,
          name: base.name,
          brand: base.brand,
        });
      } catch (e) {
        console.error("[labely] image generation failed", e);
        outImage = null;
      }
    }

    if (includeShelfIntro) {
      if (useSelfieImage) {
        shelfIntroDataUrl = await generateSelfieImage();
      } else {
        shelfIntroDataUrl = await generateShelfIntroImage({ name: base.name, brand: base.brand });
      }
    }

    const braveUsage = useBraveImages && braveImagesConfigured()
      ? await getBraveUsageSnapshot()
      : null;

    return NextResponse.json({
      name: base.name,
      brand: base.brand,
      score: base.score,
      verdict: base.verdict,
      analysisTitle: base.analysisTitle,
      analysis: base.analysis,
      labelyLegalNote: base.labelyLegalNote,
      imageDataUrl: outImage,
      labelyDbImageUrl,
      labelyBraveContentHash,
      shelfIntroDataUrl,
      braveImageRecycled: Boolean(resolvedPick?.recycled),
      braveImageGptFallback: useBraveImages && !labelyDbImageUrl && Boolean(outImage),
      braveUsage,
    });
  } catch (err) {
    console.error("[labely]", err);
    return NextResponse.json(
      { error: err?.message || "Unknown server error" },
      { status: 500 }
    );
  }
}
