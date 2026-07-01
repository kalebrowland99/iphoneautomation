import { copyFileSync, existsSync, mkdirSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const srcDir = join(root, "node_modules", "@ffmpeg", "core", "dist", "umd");
const destDir = join(root, "public", "ffmpeg");

if (!existsSync(srcDir)) {
  console.warn("[copy-ffmpeg-core] @ffmpeg/core not installed — skip copying WASM assets");
  process.exit(0);
}

mkdirSync(destDir, { recursive: true });

for (const file of ["ffmpeg-core.js", "ffmpeg-core.wasm"]) {
  copyFileSync(join(srcDir, file), join(destDir, file));
  console.log(`[copy-ffmpeg-core] ${file} -> public/ffmpeg/`);
}
