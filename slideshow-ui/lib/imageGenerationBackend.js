import { readFile } from "fs/promises";
import { join } from "path";

export const GEMINI_ENDPOINT =
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image-preview:generateContent";
const OPENAI_GENERATIONS = "https://api.openai.com/v1/images/generations";
const OPENAI_EDITS = "https://api.openai.com/v1/images/edits";

export function mimeFromPath(filePath) {
  const ext = filePath.split(".").pop()?.toLowerCase();
  return { jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp", gif: "image/gif" }[ext] ?? "image/jpeg";
}

export function resolveReferenceRoot(referenceRoot) {
  if (referenceRoot === "valcoin/references") return "valcoin/references";
  if (referenceRoot === "labely/selfie-references") return "labely/selfie-references";
  if (referenceRoot === "labely/references") return "labely/references";
  return "references";
}

export async function generateWithGemini({ prompt, referenceFile, referenceInline, referenceRoot, geminiApiKey }) {
  if (!geminiApiKey?.trim()) {
    return { error: "Google AI API key required.", status: 400 };
  }

  let parts;
  if (referenceInline?.base64 && referenceInline?.mimeType) {
    parts = [{ text: prompt }, { inlineData: { mimeType: referenceInline.mimeType, data: referenceInline.base64 } }];
  } else if (referenceFile) {
    const root = resolveReferenceRoot(referenceRoot);
    const filePath = join(process.cwd(), "public", ...root.split("/"), referenceFile);
    let fileBuffer;
    try {
      fileBuffer = await readFile(filePath);
    } catch {
      return { error: `Reference file not found: ${referenceFile}`, status: 400 };
    }
    const base64 = fileBuffer.toString("base64");
    const mimeType = mimeFromPath(referenceFile);
    parts = [{ text: prompt }, { inlineData: { mimeType, data: base64 } }];
  } else {
    parts = [{ text: prompt }];
  }

  const body = JSON.stringify({
    contents: [{ parts }],
    generationConfig: { responseModalities: ["TEXT", "IMAGE"] },
  });

  let res, data;
  for (let attempt = 0; attempt <= 2; attempt++) {
    res = await fetch(GEMINI_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-goog-api-key": geminiApiKey },
      body,
    });
    data = await res.json();
    if (res.status === 429) {
      const retryMatch = data?.error?.message?.match(/retry in ([\d.]+)s/i);
      const waitMs = retryMatch ? Math.ceil(parseFloat(retryMatch[1]) * 1000) + 500 : 30000;
      if (attempt < 2) {
        await new Promise((r) => setTimeout(r, waitMs));
        continue;
      }
    }
    break;
  }

  if (!res.ok) {
    const msg = data?.error?.message || data?.error?.status || `Gemini error ${res.status}`;
    return { error: msg, status: res.status };
  }

  const b64 = data.candidates?.[0]?.content?.parts?.find((p) => p.inlineData)?.inlineData?.data;
  if (!b64) {
    const text = data.candidates?.[0]?.content?.parts?.find((p) => p.text)?.text || "";
    const reason = data.candidates?.[0]?.finishReason || "";
    return {
      error: `No image returned.${reason ? ` Finish reason: ${reason}.` : ""}${text ? ` Model: "${text.slice(0, 120)}"` : ""}`,
      status: 502,
    };
  }
  return { b64 };
}

/** Same pipeline Thrifty/Valcoin use via POST /api/generate-image (GPT image 1.5 + edits). */
export async function generateWithGptImage1({ prompt, referenceFile, referenceInline, referenceRoot, openaiApiKey }) {
  if (!openaiApiKey?.trim()) {
    return { error: "OpenAI API key required.", status: 400 };
  }

  const headers = { Authorization: `Bearer ${openaiApiKey}` };

  let res, data;

  if (referenceInline?.base64 && referenceInline?.mimeType) {
    const buf = Buffer.from(referenceInline.base64, "base64");
    const mimeType = referenceInline.mimeType;
    const blob = new Blob([buf], { type: mimeType });
    const ext = mimeType.includes("png") ? "png" : mimeType.includes("webp") ? "webp" : "jpg";
    const fileName = `reference.${ext}`;

    const form = new FormData();
    form.append("image", blob, fileName);
    form.append("prompt", prompt);
    form.append("model", "gpt-image-1.5");
    form.append("size", "1024x1536");
    form.append("quality", "low");
    form.append("n", "1");

    res = await fetch(OPENAI_EDITS, { method: "POST", headers, body: form });
    data = await res.json();
  } else if (referenceFile) {
    const root = resolveReferenceRoot(referenceRoot);
    const filePath = join(process.cwd(), "public", ...root.split("/"), referenceFile);
    let fileBuffer;
    try {
      fileBuffer = await readFile(filePath);
    } catch {
      return { error: `Reference file not found: ${referenceFile}`, status: 400 };
    }

    const mimeType = mimeFromPath(referenceFile);
    const blob = new Blob([fileBuffer], { type: mimeType });
    const ext = referenceFile.split(".").pop()?.toLowerCase() || "png";
    const fileName = `reference.${ext}`;

    const form = new FormData();
    form.append("image", blob, fileName);
    form.append("prompt", prompt);
    form.append("model", "gpt-image-1.5");
    form.append("size", "1024x1536");
    form.append("quality", "low");
    form.append("n", "1");

    res = await fetch(OPENAI_EDITS, { method: "POST", headers, body: form });
    data = await res.json();
  } else {
    res = await fetch(OPENAI_GENERATIONS, {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "gpt-image-1.5",
        prompt,
        size: "1024x1536",
        quality: "low",
        n: 1,
      }),
    });
    data = await res.json();
  }

  if (!res.ok) {
    const msg = data?.error?.message || `OpenAI error ${res.status}`;
    return { error: msg, status: res.status };
  }

  const b64 = data.data?.[0]?.b64_json;
  if (!b64) return { error: "No image returned from OpenAI.", status: 502 };
  return { b64 };
}

/** Mirrors POST /api/generate-image default branch (Thrifty sidebar → generate-image). */
export async function runImageGenerationPipeline({
  prompt,
  referenceFile,
  referenceInline,
  referenceRoot,
  model = "gemini",
  openaiApiKey: requestOpenaiApiKey,
  geminiApiKey: requestGeminiApiKey,
}) {
  const openaiApiKey = process.env.OPENAI_API_KEY?.trim() || requestOpenaiApiKey?.trim();
  const geminiApiKey = process.env.GEMINI_API_KEY?.trim() || requestGeminiApiKey?.trim();

  const wantOpenAI = model === "gpt-image-1";
  const hasOpenAI = Boolean(openaiApiKey?.trim());
  const hasGemini = Boolean(geminiApiKey?.trim());

  if (wantOpenAI) {
    return generateWithGptImage1({ prompt, referenceFile, referenceInline, referenceRoot, openaiApiKey });
  }
  if (hasGemini) {
    return generateWithGemini({ prompt, referenceFile, referenceInline, referenceRoot, geminiApiKey });
  }
  if (hasOpenAI) {
    return generateWithGptImage1({ prompt, referenceFile, referenceInline, referenceRoot, openaiApiKey });
  }
  return { error: "No AI API key configured. Set OPENAI_API_KEY or GEMINI_API_KEY.", status: 400 };
}
