import { NextResponse } from "next/server";
import { runImageGenerationPipeline } from "@/lib/imageGenerationBackend";

const OPENAI_CHAT = "https://api.openai.com/v1/chat/completions";

async function identifyWithOpenAI({ imageUrl, openaiApiKey }) {
  if (!openaiApiKey?.trim()) {
    return { error: "OpenAI API key is not configured on the server.", status: 500 };
  }

  const res = await fetch(OPENAI_CHAT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${openaiApiKey}`,
    },
    body: JSON.stringify({
      model: "gpt-4o",
      messages: [{
        role: "user",
        content: [
          { type: "image_url", image_url: { url: imageUrl, detail: "low" } },
          { type: "text", text: `You are an expert Grailed reseller and thrift evaluator. Analyze this thrift store item photo.

Return ONLY valid JSON — no markdown, no explanation:
{"title": "3-6 word resale title", "price": 45}

Rules:
- title: concise resale product title like "Vintage Chrome Hearts Ring" or "Supreme Box Logo Hoodie" or "Kapital Boro Patchwork Jacket"
- price: realistic Grailed/eBay resale price in USD as an integer

Brand price guidelines:
- Japanese archive (Kapital, Visvim, Undercover, Number Nine, Comme des Garçons, etc.): $150–2000
- High fashion (Rick Owens, Balenciaga, Chrome Hearts, Prada, etc.): $100–1500
- Streetwear (Supreme, BAPE, Off-White, Palace): $60–500
- Gorpcore (Arc'teryx, Patagonia TNF): $40–300
- Vintage workwear (Carhartt, Levi's USA, Dickies): $30–200
- Sneakers (Nike, Jordan, Adidas vintage): $50–400
- General vintage / cultural merch: $15–80

Be decisive. Think like a reseller trying to make money.` },
        ],
      }],
      max_tokens: 60,
    }),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    return { error: data?.error?.message || `OpenAI error ${res.status}`, status: res.status };
  }

  const data = await res.json();
  const raw = data.choices?.[0]?.message?.content?.trim() || "";

  try {
    const parsed = JSON.parse(raw.replace(/```json|```/g, "").trim());
    return {
      title: parsed.title?.replace(/^["']|["']$/g, "") || null,
      price: parsed.price ? String(Math.round(Number(parsed.price))) : null,
    };
  } catch {
    return { error: "Could not parse OpenAI identification response.", status: 502 };
  }
}

async function rewordCaptionWithOpenAI({ text, openaiApiKey }) {
  if (!openaiApiKey?.trim()) {
    return { error: "OpenAI API key is not configured on the server.", status: 500 };
  }
  const res = await fetch(OPENAI_CHAT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${openaiApiKey}`,
    },
    body: JSON.stringify({
      model: "gpt-4o-mini",
      messages: [
        {
          role: "user",
          content: `You lightly reword this short TikTok slideshow hook so it feels fresh but keeps the same meaning, energy, and emojis. Preserve line breaks as \\n if there are multiple lines. Max 2 lines. Output ONLY the new caption text, no quotes or explanation:\n\n${text}`,
        },
      ],
      max_tokens: 120,
    }),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    return { error: data?.error?.message || `OpenAI error ${res.status}`, status: res.status };
  }

  const data = await res.json();
  let out = data.choices?.[0]?.message?.content?.trim() || "";
  out = out.replace(/^["']|["']$/g, "").trim();
  if (!out) return { error: "Empty reword response.", status: 502 };
  return { text: out };
}

/** Turn noisy Wikimedia filenames into short collector-friendly US coin names (text only). */
async function simplifyCoinTitleWithOpenAI({ rawTitle, openaiApiKey }) {
  if (!openaiApiKey?.trim()) {
    return { error: "OpenAI API key is not configured on the server.", status: 500 };
  }
  const raw = String(rawTitle ?? "").trim();
  if (!raw) return { error: "Empty title.", status: 400 };

  const res = await fetch(OPENAI_CHAT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${openaiApiKey}`,
    },
    body: JSON.stringify({
      model: "gpt-4o-mini",
      messages: [
        {
          role: "user",
          content: `You clean up Wikimedia Commons coin photo titles into short US coin names for a collector app.

Raw title (from filename / catalog):
${raw}

Return ONLY JSON (no markdown):
{"title": "1909-S VDB Lincoln Cent"}

Rules:
- 3–8 words, Title Case, United States coins only
- Include year and mint mark (P, D, S, CC, etc.) when present or inferable
- Include denomination and series (e.g. Morgan Dollar, Buffalo Nickel, Washington Quarter)
- If the raw title is only numbers, codes, or gibberish (e.g. "1968KHDUCB", "5813028525", "NNC-US-1855-5C"), infer the most likely US coin collectors would recognize — never return only digits
- Never return "Unknown" — make a reasonable best guess from context
- Drop: obverse/reverse, photographer, museum IDs, file extensions, Flickr IDs
- If the raw title is already clear, shorten it slightly but keep the same coin`,
        },
      ],
      temperature: 0.4,
      max_tokens: 60,
    }),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    return { error: data?.error?.message || `OpenAI error ${res.status}`, status: res.status };
  }

  const data = await res.json();
  const out = data.choices?.[0]?.message?.content?.trim() || "";
  try {
    const parsed = JSON.parse(out.replace(/```json|```/g, "").trim());
    const title = String(parsed.title ?? "").trim().replace(/^["']|["']$/g, "");
    if (!title || /^\d+$/.test(title)) {
      return { error: "Invalid simplified title.", status: 502 };
    }
    return { title };
  } catch {
    return { error: "Could not parse simplified coin title.", status: 502 };
  }
}

async function coinPricesWithOpenAI({ coinName, openaiApiKey }) {
  if (!openaiApiKey?.trim()) {
    return { error: "OpenAI API key is not configured on the server.", status: 500 };
  }
  const res = await fetch(OPENAI_CHAT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${openaiApiKey}`,
    },
    body: JSON.stringify({
      model: "gpt-4o-mini",
      messages: [
        {
          role: "user",
          content: `You estimate realistic US coin prices for collectors.\n\nCoin: ${coinName}\n\nReturn ONLY JSON (no markdown, no explanation) in this shape:\n{"buy": 120, "sell": 180}\n\nRules:\n- buy = what someone might realistically pay at a show/online to acquire it (USD integer)\n- sell = realistic resale / market value to a collector (USD integer)\n- sell must be >= buy\n- Be conservative (no insane viral numbers) unless the coin is truly famous (e.g., 1913 Liberty nickel, 1933 Saint-Gaudens double eagle)\n- If the coin includes a condition note like proof/high grade, reflect higher price but keep plausible\n- If uncertain, return reasonable mid-market estimates rather than refusing.`,
        },
      ],
      temperature: 0.6,
      max_tokens: 80,
    }),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    return { error: data?.error?.message || `OpenAI error ${res.status}`, status: res.status };
  }

  const data = await res.json();
  const raw = data.choices?.[0]?.message?.content?.trim() || "";
  try {
    const parsed = JSON.parse(raw.replace(/```json|```/g, "").trim());
    const buy = Math.round(Number(parsed.buy));
    const sell = Math.round(Number(parsed.sell));
    if (!Number.isFinite(buy) || !Number.isFinite(sell) || buy <= 0 || sell <= 0) {
      return { error: "Invalid coin price response.", status: 502 };
    }
    return { buy: String(buy), sell: String(Math.max(sell, buy)) };
  } catch {
    return { error: "Could not parse OpenAI coin price response.", status: 502 };
  }
}

// ── Route handler ─────────────────────────────────────────────────────────────
export async function POST(req) {
  try {
    const {
      action = "generate",
      prompt,
      referenceFile,
      referenceInline,
      referenceRoot,
      imageUrl,
      geminiApiKey: requestGeminiApiKey,
      openaiApiKey: requestOpenaiApiKey,
      model = "gemini",
      text,
    } = await req.json();

    const openaiApiKey = process.env.OPENAI_API_KEY?.trim() || requestOpenaiApiKey?.trim();
    const geminiApiKey = process.env.GEMINI_API_KEY?.trim() || requestGeminiApiKey?.trim();

    let result;
    if (action === "identify") {
      result = await identifyWithOpenAI({ imageUrl, openaiApiKey });
      if (result.error) {
        return NextResponse.json({ error: result.error }, { status: result.status ?? 500 });
      }
      return NextResponse.json({ title: result.title, price: result.price });
    }

    if (action === "rewordCaption") {
      result = await rewordCaptionWithOpenAI({ text: text ?? "", openaiApiKey });
      if (result.error) {
        return NextResponse.json({ error: result.error }, { status: result.status ?? 500 });
      }
      return NextResponse.json({ text: result.text });
    }

    if (action === "coinTitle") {
      const rawTitle = String(text ?? "").trim();
      result = await simplifyCoinTitleWithOpenAI({ rawTitle, openaiApiKey });
      if (result.error) {
        return NextResponse.json({ error: result.error }, { status: result.status ?? 500 });
      }
      return NextResponse.json({ title: result.title });
    }

    if (action === "coinPrices") {
      const coinName = String(text ?? "").trim();
      result = await coinPricesWithOpenAI({ coinName, openaiApiKey });
      if (result.error) {
        return NextResponse.json({ error: result.error }, { status: result.status ?? 500 });
      }
      return NextResponse.json({ buy: result.buy, sell: result.sell });
    }

    result = await runImageGenerationPipeline({
      prompt,
      referenceFile,
      referenceInline,
      referenceRoot,
      model,
      openaiApiKey: requestOpenaiApiKey,
      geminiApiKey: requestGeminiApiKey,
    });

    if (result.error) {
      return NextResponse.json({ error: result.error }, { status: result.status ?? 500 });
    }
    return NextResponse.json({ b64: result.b64 });
  } catch (err) {
    console.error("[generate-image]", err);
    return NextResponse.json({ error: err.message || "Unknown server error" }, { status: 500 });
  }
}
