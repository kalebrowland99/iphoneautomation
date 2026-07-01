import { NextResponse } from "next/server";
import { braveImagesConfigured } from "@/lib/braveFoodImage";
import { getUsedBraveImageUrls, markBraveImagesUsed } from "@/lib/braveUsedImages";

export const dynamic = "force-dynamic";

export async function GET() {
  const urls = await getUsedBraveImageUrls();
  return NextResponse.json({
    configured: braveImagesConfigured(),
    count: urls.size,
  });
}

export async function POST(req) {
  let body = {};
  try {
    body = await req.json();
  } catch {
    body = {};
  }
  const urls = Array.isArray(body.urls) ? body.urls : [];
  const result = await markBraveImagesUsed(urls);
  return NextResponse.json({ ok: true, ...result });
}
