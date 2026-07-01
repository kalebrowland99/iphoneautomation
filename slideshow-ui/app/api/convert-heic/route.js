import { NextResponse } from "next/server";
import sharp from "sharp";
import convertHeic from "heic-convert";

export const runtime = "nodejs";

/**
 * Prefer Sharp (fast, EXIF rotate) when libvips supports the input.
 * iPhone HEIC: prebuilt Sharp often omits HEIF (patents) — fall back to `heic-convert` (libde265 WASM).
 */
async function bufferToNormalizedJpeg(buffer) {
  try {
    return await sharp(buffer).rotate().jpeg({ quality: 88, mozjpeg: true }).toBuffer();
  } catch (sharpErr) {
    try {
      const rawJpeg = await convertHeic({
        buffer,
        format: "JPEG",
        quality: 0.88,
      });
      const jpegBuf = Buffer.isBuffer(rawJpeg) ? rawJpeg : Buffer.from(rawJpeg);
      return await sharp(jpegBuf).rotate().jpeg({ quality: 88, mozjpeg: true }).toBuffer();
    } catch (heicErr) {
      console.error("[convert-heic] sharp:", sharpErr?.message, "| heic-convert:", heicErr?.message);
      const msg =
        heicErr?.message || sharpErr?.message || "Could not decode image.";
      throw new Error(
        msg.includes("parse") || msg.includes("HEIF")
          ? "Could not read this HEIC file (try opening in Photos and exporting as JPEG)."
          : msg
      );
    }
  }
}

/**
 * Raster uploads → JPEG data URL (HEIC/HEIF/JPEG/PNG/WebP where supported).
 */
export async function POST(req) {
  try {
    const ct = req.headers.get("content-type") || "";
    let buffer;

    if (ct.includes("multipart/form-data")) {
      const form = await req.formData();
      const f = form.get("file");
      if (!f || typeof f === "string") {
        return NextResponse.json({ error: "Missing multipart field `file`." }, { status: 400 });
      }
      buffer = Buffer.from(await f.arrayBuffer());
    } else {
      const json = await req.json().catch(() => ({}));
      const raw = typeof json.base64 === "string" ? json.base64.trim() : "";
      const b64 = raw.includes(",") ? raw.replace(/^data:[^;]+;base64,/i, "") : raw;
      if (!b64) {
        return NextResponse.json(
          { error: "Send multipart/form-data with `file`, or JSON `{ base64 }`." },
          { status: 400 }
        );
      }
      buffer = Buffer.from(b64, "base64");
    }

    if (!buffer?.length) {
      return NextResponse.json({ error: "Empty file." }, { status: 400 });
    }

    const jpeg = await bufferToNormalizedJpeg(buffer);
    const dataUrl = `data:image/jpeg;base64,${jpeg.toString("base64")}`;
    return NextResponse.json({ dataUrl });
  } catch (err) {
    console.error("[convert-heic]", err);
    return NextResponse.json(
      { error: err?.message || "Could not convert image." },
      { status: 422 }
    );
  }
}
