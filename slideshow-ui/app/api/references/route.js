import { NextResponse } from "next/server";
import { listPublicReferenceImageRelPaths } from "@/lib/referenceImages";

export async function GET(req) {
  const { searchParams } = new URL(req.url);
  const appId = searchParams.get("appId") || "thrifty";
  const images = await listPublicReferenceImageRelPaths(appId);
  return NextResponse.json({ images });
}
