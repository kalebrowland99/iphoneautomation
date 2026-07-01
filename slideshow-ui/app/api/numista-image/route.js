import { NextResponse } from "next/server";
import { fetchRemoteImageDataUrl } from "@/lib/fetchRemoteImageDataUrl";

export const runtime = "nodejs";
export const maxDuration = 30;

const NUMISTA_HOST = /^https:\/\/([a-z]{2}\.)?numista\.com\//i;

function normalizeRemoteUrl(raw) {
  const s = String(raw || "").trim();
  if (!s || !NUMISTA_HOST.test(s)) return "";
  return s;
}

function dataUrlToBuffer(imageDataUrl) {
  const m = /^data:([^;]+);base64,(.+)$/i.exec(String(imageDataUrl || "").trim());
  if (!m) return null;
  try {
    const binary = atob(m[2]);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return { mime: m[1], buffer: bytes };
  } catch {
    return null;
  }
}

/** GET /api/numista-image?url=… — same-origin proxy for Numista catalogue photos (never redirect). */
export async function GET(req) {
  const reqUrl = new URL(req.url);
  // GET /api/numista-image?healthcheck=1 — verifies the proxy can reach Numista
  if (reqUrl.searchParams.get("healthcheck")) {
    const probe =
      "https://en.numista.com/catalogue/photos/etats-unis/3260-original.jpg";
    const ok = await fetchRemoteImageDataUrl(probe, "AutoSlideshow Healthcheck/1.0");
    return NextResponse.json({
      ok: Boolean(ok),
      probe,
      bytes: ok ? ok.length : 0,
      runtime: "nodejs",
    });
  }

  const url = normalizeRemoteUrl(reqUrl.searchParams.get("url"));
  if (!url) {
    return NextResponse.json({ error: "Missing or invalid Numista image url." }, { status: 400 });
  }

  const mode = String(reqUrl.searchParams.get("mode") || "").trim().toLowerCase();
  if (mode === "redirect") {
    return NextResponse.json(
      {
        error:
          "Redirect mode is disabled (Numista blocks cross-origin browser loads). Use JSON or mode=raw.",
      },
      { status: 400 },
    );
  }

  const imageDataUrl = await fetchRemoteImageDataUrl(url, "AutoSlideshow Valcoin/1.0 (Numista)");
  if (!imageDataUrl) {
    return NextResponse.json(
      { error: "Could not download image from Numista CDN.", imageUrl: url },
      { status: 502 },
    );
  }

  if (mode === "raw") {
    const parsed = dataUrlToBuffer(imageDataUrl);
    if (!parsed?.buffer?.length) {
      return NextResponse.json({ error: "Invalid image payload." }, { status: 502 });
    }
    return new NextResponse(parsed.buffer, {
      headers: {
        "Content-Type": parsed.mime,
        "Cache-Control": "public, max-age=86400",
      },
    });
  }

  return NextResponse.json({ imageDataUrl, imageUrl: url });
}
