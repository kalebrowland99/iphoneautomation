import { NextResponse } from "next/server";
import { braveImagesConfigured } from "@/lib/braveFoodImage";
import { getBraveUsageSnapshot } from "@/lib/braveUsage";

export const dynamic = "force-dynamic";

export async function GET() {
  if (!braveImagesConfigured()) {
    return NextResponse.json({ configured: false, used: 0, limit: 0, remaining: 0, month: "" });
  }
  const usage = await getBraveUsageSnapshot();
  return NextResponse.json({ configured: true, ...usage });
}
