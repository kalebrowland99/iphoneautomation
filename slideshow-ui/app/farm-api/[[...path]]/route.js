import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const FARM_BASE = (process.env.FARM_PROXY_URL || "http://127.0.0.1:8080").replace(
  /\/+$/,
  "",
);

async function proxyToFarm(request, context) {
  const { path: pathParts = [] } = await context.params;
  const path = pathParts.map((p) => String(p || "").trim()).filter(Boolean).join("/");
  const incoming = new URL(request.url);
  const target = `${FARM_BASE}/api/${path}${incoming.search}`;

  const headers = new Headers();
  const secret = request.headers.get("x-farm-secret");
  if (secret) headers.set("X-Farm-Secret", secret);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const accept = request.headers.get("accept");
  if (accept) headers.set("Accept", accept);

  const init = { method: request.method, headers };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  let upstream;
  try {
    upstream = await fetch(target, init);
  } catch (err) {
    console.error("[farm-api proxy] fetch failed:", target, err);
    return NextResponse.json(
      { detail: `Farm dashboard unreachable at ${FARM_BASE}` },
      { status: 502 },
    );
  }

  const body = await upstream.arrayBuffer();
  const responseHeaders = new Headers();
  const upstreamType = upstream.headers.get("content-type");
  if (upstreamType) responseHeaders.set("Content-Type", upstreamType);

  return new NextResponse(body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export async function GET(request, context) {
  return proxyToFarm(request, context);
}

export async function POST(request, context) {
  return proxyToFarm(request, context);
}

export async function PUT(request, context) {
  return proxyToFarm(request, context);
}

export async function PATCH(request, context) {
  return proxyToFarm(request, context);
}

export async function DELETE(request, context) {
  return proxyToFarm(request, context);
}

export async function OPTIONS() {
  return new NextResponse(null, {
    status: 204,
    headers: {
      Allow: "GET, POST, PUT, PATCH, DELETE, OPTIONS",
    },
  });
}
