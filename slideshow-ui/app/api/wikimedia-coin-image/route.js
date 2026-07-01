import { NextResponse } from "next/server";
import { fetchRemoteImageDataUrl } from "@/lib/fetchRemoteImageDataUrl";

export const runtime = "nodejs";
export const maxDuration = 30;
export const dynamic = "force-dynamic";
export const revalidate = 0;

const WIKIMEDIA_HOST = /^https:\/\/upload\.wikimedia\.org\//i;
const USER_AGENT =
  "AutoSlideshow/1.0 (https://github.com/kalebrowland99/autoslideshow; +random coin photos)";

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

function normalizeRemoteUrl(raw) {
  const s = String(raw || "").trim();
  if (!s || !WIKIMEDIA_HOST.test(s)) return "";
  return s;
}

/** GET /api/wikimedia-coin-image?url=… — same-origin proxy for Wikimedia coin bytes. */
export async function GET(req) {
  const reqUrl = new URL(req.url);
  const url = normalizeRemoteUrl(reqUrl.searchParams.get("url"));
  if (!url) {
    return NextResponse.json({ error: "Missing or invalid Wikimedia image url." }, { status: 400 });
  }

  const mode = String(reqUrl.searchParams.get("mode") || "").trim().toLowerCase();
  const imageDataUrl = await fetchRemoteImageDataUrl(url, USER_AGENT);
  if (!imageDataUrl?.startsWith("data:image/")) {
    return NextResponse.json(
      { error: "Could not download image from Wikimedia.", imageUrl: url },
      { status: 502 },
    );
  }

  if (mode === "json") {
    return NextResponse.json(
      { imageDataUrl, imageUrl: url },
      { headers: { "Cache-Control": "no-store" } },
    );
  }

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
