import { readdir } from "fs/promises";
import path from "path";

export async function GET() {
  const dir = path.join(process.cwd(), "public", "audio");
  try {
    const files = await readdir(dir);
    const audioFiles = files.filter((f) =>
      /\.(mp3|wav|m4a|aac|ogg|flac)$/i.test(f)
    );
    return Response.json({ files: audioFiles.map((f) => `/audio/${f}`) });
  } catch {
    return Response.json({ files: [] });
  }
}
