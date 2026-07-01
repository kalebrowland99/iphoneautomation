import { NextResponse } from "next/server";

const OPENAI_CHAT = "https://api.openai.com/v1/chat/completions";

export async function POST(req) {
  const { type, itemName, soldPrice, appId, text } = await req.json();
  const apiKey = process.env.OPENAI_API_KEY?.trim();

  if (!apiKey) return NextResponse.json({ error: "OPENAI_API_KEY not set" }, { status: 500 });

  if (type === "imessageThread") {
    const priceStr = soldPrice ? `$${soldPrice}` : "a lot of money";
    const appName = appId === "valcoin" ? "Valcoin" : "Thrifty";
    const appCategory = appId === "valcoin" ? "coinscan" : "reselling";
    const prompt = `Generate a realistic iMessage conversation between a mom and her son.
Context:
- Mom found a thrift-store item ("${itemName || "some item"}") at Goodwill, checked it on the ${appName} ${appCategory} app.
- She called her son but he didn't answer, so she texts him.
- She's also mad about his girlfriend's thrift haul videos online and says she's not welcome at family events.
- Because he didn't answer, she gave the item away to someone else at the store.
- Son texts back upset, saying he looked up the item on ${appName} and it was worth ${priceStr}.
- Mom shuts him down: she doesn't care about ${appName}, tells him to get a real job and stop reselling.

Rules:
- Exactly 5 messages in this order: mom, mom, mom, son, mom
- Mom texts are passive-aggressive, casual, lowercase, realistic mom texting style
- Son's text is shocked/frustrated, references "${priceStr}" specifically
- Last mom message is dismissive and tells him to get a job and stop reselling
- Keep each message under 25 words
- Vary the wording naturally — don't sound templated
- Return ONLY a JSON array, no markdown, no explanation:
[{"from":"mom","text":"..."},{"from":"mom","text":"..."},{"from":"mom","text":"..."},{"from":"son","text":"..."},{"from":"mom","text":"..."}]`;

    try {
      const res = await fetch(OPENAI_CHAT, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
        body: JSON.stringify({
          model: "gpt-4o-mini",
          temperature: 1.1,
          max_tokens: 400,
          messages: [{ role: "user", content: prompt }],
        }),
      });

      const data = await res.json();
      const raw = data.choices?.[0]?.message?.content?.trim() ?? "";

      // Strip markdown code fences if model adds them
      const cleaned = raw.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim();
      const thread = JSON.parse(cleaned);

      if (!Array.isArray(thread) || thread.length !== 5) {
        throw new Error("Unexpected thread format");
      }

      return NextResponse.json({ thread });
    } catch (e) {
      console.error("generate-text error:", e);
      return NextResponse.json({ error: String(e) }, { status: 500 });
    }
  }

  if (type === "starterPackThrifting") {
    // Wide variety of thrift starter pack themes — pick one randomly each call
    const PACKS = [
      { headline: "pov: you thrift full time", angle: "the physical grind — bins, lines, dust, germ-x, masks, sweaty hauls" },
      { headline: "pov: you're a goodwill hunter", angle: "dedicated goodwill shopper — cart fills, rack digs, color-tag days, donation truck" },
      { headline: "pov: you resell thrift finds", angle: "the depop/poshmark reseller hustle — packaging tape, shipping labels, post office, price research" },
      { headline: "pov: you scored a thrift grail", angle: "finding an incredible rare piece — the moment of discovery, the price tag, the haul photo" },
      { headline: "pov: you're a thrift flipper", angle: "buying cheap, selling high — thrift rack, wash pile, photoshoot setup, listing app" },
      { headline: "pov: you run thrift haul TikToks", angle: "filming thrift content — ring light, haul spread on bed, comment section chaos, viral sound" },
      { headline: "pov: you only wear thrifted clothes", angle: "full thrifted wardrobe lifestyle — layered fits, unique pieces, people asking where you got it" },
      { headline: "pov: goodwill bins is your gym", angle: "the bins experience — elbow fights, dive posture, gloves, treasure pile on the side" },
      { headline: "pov: thrifting is a personality trait", angle: "thrift as identity — tote bag, vintage everything, explaining it to non-thrifters, the flex" },
      { headline: "pov: you thrift before anyone else wakes up", angle: "early morning thrifter — empty parking lot, first through the door, fresh rack" },
    ];

    const pack = PACKS[Math.floor(Math.random() * PACKS.length)];

    const GREY_HAT_POOL = [
      "switching tags", "swiping buggies", "cart snatching", "hiding finds",
      "tag swapping", "rack squatting", "price sticker swap", "holding racks hostage",
      "stealing from carts", "covering finds", "stacking carts", "faking condition tags",
      "hiding under racks", "digging in donated bags", "price-tag peeling",
    ];
    const greyHatExample = GREY_HAT_POOL[Math.floor(Math.random() * GREY_HAT_POOL.length)];

    const prompt = `You are generating a viral TikTok thrift starter pack slide.

Pack concept: "${pack.headline}"
Theme angle: ${pack.angle}

Rules:
- Audience: Gen Z / young millennial thrifters
- Tone: relatable, slightly controversial, debate-bait — NOT hateful or discriminatory
- Do NOT mention Google Lens, do NOT use any specific brand names
- Return ONLY raw JSON — no markdown, no extra text

Label rules (CRITICAL — read carefully):
- Labels must be CONCRETE and INSTANTLY SELF-EXPLANATORY to any thrifter
- A label should describe a specific, real, physical object or action — NOT a metaphor, NOT a vibe, NOT a clever phrase
- A stranger who thrifts should read the label and immediately picture the exact thing
- Bad examples: "hide and seek", "the ultimate tote", "the hustle", "thrift therapy" — too abstract/vague
- Good examples: "germ-x bottle", "the bins smell", "cart diving", "depop notification", "post office run", "price tag drama", "donation pile", "bin gloves", "haul spread", "shipping tape"

Output:
1. headline — all lowercase, 1–2 punchy lines, creative variation of "${pack.headline}" (slight rewording each time, don't copy word for word)
2. Three tiles — each has:
   - label: 1–3 words, a SPECIFIC concrete thrift object or action (follow label rules above)
   - imagePrompt: one sentence for a realistic iPhone candid photo of exactly that label subject (no text overlays, no people in foreground, 9:16 portrait)

Hard rule: tiles[1].label MUST be a grey-hat / black-hat thrifting controversy inspired by: "${greyHatExample}". Keep it 1–3 words, specific and concrete (e.g. "tag switching", "cart snatching").

Return this exact JSON shape:
{
  "headline": "...",
  "tiles": [
    {"label": "...", "imagePrompt": "..."},
    {"label": "...", "imagePrompt": "..."},
    {"label": "...", "imagePrompt": "..."}
  ]
}`;

    try {
      const res = await fetch(OPENAI_CHAT, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
        body: JSON.stringify({
          model: "gpt-4o-mini",
          temperature: 1.2,
          max_tokens: 320,
          messages: [{ role: "user", content: prompt }],
        }),
      });

      const data = await res.json();
      const raw = data.choices?.[0]?.message?.content?.trim() ?? "";
      const cleaned = raw.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim();
      const out = JSON.parse(cleaned);

      const headline = String(out?.headline ?? "").trim();
      const tilesRaw = Array.isArray(out?.tiles) ? out.tiles : [];

      // Fallback: also accept old flat items[] shape
      if ((!tilesRaw.length) && Array.isArray(out?.items)) {
        const items = out.items.map((s) => String(s ?? "").trim()).filter(Boolean);
        if (!headline || items.length !== 3) throw new Error("Unexpected starter pack format");
        return NextResponse.json({ headline, items: items.map((s) => s.slice(0, 28)), imagePrompts: [] });
      }

      if (!headline || tilesRaw.length !== 3) throw new Error("Unexpected starter pack format");

      const items = tilesRaw.map((t) => String(t?.label ?? "").trim().slice(0, 28));
      const imagePrompts = tilesRaw.map((t) => String(t?.imagePrompt ?? "").trim().slice(0, 300));

      return NextResponse.json({ headline, items, imagePrompts });
    } catch (e) {
      console.error("generate-text error:", e);
      return NextResponse.json({ error: String(e) }, { status: 500 });
    }
  }

  if (type === "labelyOutroVariation") {
    const seedText = String(text || "").trim();
    const base =
      seedText
      || "Just found 2 cancerous foods in my cabinet. I had no idea was probably shortening my lifespan since it was a tier 1 carcinogen, who knows if i kept consuming that what i'd get 10 years down the line. The app i use is called labely.";
    const prompt = `Rewrite this TikTok outro into ONE varied version with the same core meaning and tone:
"${base}"

Requirements:
- Output exactly 2-3 short sentences.
- Keep first-person voice ("I", "my").
- Mention: found cancerous foods at home/cabinet, concern about long-term health risk, and app name Labely.
- Keep it natural and conversational, not robotic.
- No hashtags, no emojis, no markdown, no quotes.
- Return ONLY the final text.`;
    try {
      const res = await fetch(OPENAI_CHAT, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
        body: JSON.stringify({
          model: "gpt-4o-mini",
          temperature: 1.1,
          max_tokens: 180,
          messages: [{ role: "user", content: prompt }],
        }),
      });
      const data = await res.json();
      const out = String(data.choices?.[0]?.message?.content ?? "").replace(/^["']|["']$/g, "").trim();
      if (!out) throw new Error("Empty outro variation");
      return NextResponse.json({ text: out });
    } catch (e) {
      console.error("generate-text error:", e);
      return NextResponse.json({ text: base });
    }
  }

  return NextResponse.json({ error: "Unknown type" }, { status: 400 });
}
