"use client";

import { useMemo, useRef, useState } from "react";
import { Switch } from "@/components/ui/switch";

const VIDEO_ACCEPT = "video/mp4,video/quicktime,video/x-m4v,video/webm";
const AUDIO_ACCEPT = "audio/mpeg,audio/wav,audio/mp4,audio/aac,audio/ogg";
const IMAGE_ACCEPT = "image/png,image/jpeg,image/webp,image/gif";
const MAX_SOURCE_VIDEOS = 3;
const DEFAULT_COPIES = 20;
const MAX_SOURCE_FILE_MB = 250;
const FFMPEG_CORE_VERSION = "0.12.6";
const DRAWTEXT_FONT_PATH = "/fonts/arial.ttf";

const DEFAULT_SETTINGS = {
  noise: true,
  framerate: true,
  border: true,
  speed: true,
  trim: true,
  scale: true,
  blur: true,
  color: true,
  runningLine: false,
  staticText: false,
  watermark: false,
  audioPitch: true,
  addAudio: false,
  addAudioMode: "overlay",
  verticalCombo: false,
  metadata: true,
  codec: true,
};

const DEFAULT_PHRASES = [
  "daily find",
  "watch this",
  "quick clip",
  "new angle",
  "fresh version",
  "saved for later",
  "phone upload",
  "original edit",
];

const FRAME_RATE_POOL = [24, 25, 30, 48, 60];
const PRESETS = ["veryfast", "fast", "medium"];
const AUDIO_BITRATES = [128, 160, 192, 256, 320];
const WATERMARK_POSITIONS = [
  { label: "top left", x: "18", y: "18" },
  { label: "top right", x: "main_w-overlay_w-18", y: "18" },
  { label: "bottom left", x: "18", y: "main_h-overlay_h-18" },
  { label: "bottom right", x: "main_w-overlay_w-18", y: "main_h-overlay_h-18" },
  { label: "center", x: "(main_w-overlay_w)/2", y: "(main_h-overlay_h)/2" },
];

function randomHex(byteLength = 8) {
  const u = new Uint8Array(byteLength);
  if (typeof crypto !== "undefined" && crypto.getRandomValues) crypto.getRandomValues(u);
  else for (let i = 0; i < byteLength; i++) u[i] = Math.floor(Math.random() * 256);
  return [...u].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function clampNumber(value, min, max, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

function randomBetween(min, max, digits = 3) {
  const v = min + Math.random() * (max - min);
  return Number(v.toFixed(digits));
}

function randomInt(min, max) {
  return Math.floor(min + Math.random() * (max - min + 1));
}

function pick(items) {
  return items[Math.floor(Math.random() * items.length)];
}

function sanitizeName(value) {
  return String(value || "video")
    .replace(/\.[^.]+$/, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 42) || "video";
}

function extensionFor(file, fallback = "mp4") {
  const m = /\.([a-z0-9]+)$/i.exec(file?.name || "");
  return (m?.[1] || fallback).toLowerCase().replace(/[^a-z0-9]/g, "") || fallback;
}

function escapeDrawtextText(value) {
  return String(value || "")
    .replace(/\\/g, "\\\\")
    .replace(/:/g, "\\:")
    .replace(/'/g, "\\'")
    .replace(/,/g, "\\,")
    .replace(/%/g, "\\%");
}

function colorValue(hex) {
  return `0x${String(hex || "#ffffff").replace("#", "")}`;
}

function randomColor() {
  const colors = [
    "#ffffff",
    "#000000",
    "#ff4d4d",
    "#ffd166",
    "#06d6a0",
    "#4cc9f0",
    "#b517ff",
    "#f8f7ff",
  ];
  return pick(colors);
}

function parsePhrases(raw) {
  const lines = String(raw || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  return lines.length ? lines : DEFAULT_PHRASES;
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function getVideoMeta(file) {
  return new Promise((resolve) => {
    const video = document.createElement("video");
    const url = URL.createObjectURL(file);
    const done = (value) => {
      URL.revokeObjectURL(url);
      resolve(value);
    };
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      const hasAudio =
        (typeof video.audioTracks !== "undefined" && video.audioTracks.length > 0) ||
        Boolean(video.mozHasAudio) ||
        (typeof video.webkitAudioDecodedByteCount === "number" && video.webkitAudioDecodedByteCount > 0);
      done({
        duration: Number.isFinite(video.duration) ? video.duration : 0,
        hasAudio,
      });
    };
    video.onerror = () => done({ duration: 0, hasAudio: false });
    video.src = url;
  });
}

function formatFfmpegError(error, ffmpegLog) {
  const message = String(error?.message || error || "");
  if (error?.name === "ErrnoError" || message.includes("FS error")) {
    if (ffmpegLog) return `FFmpeg failed: ${ffmpegLog}`;
    return "FFmpeg ran out of browser memory or could not read/write a file. Try a smaller/shorter video or fewer copies.";
  }
  return message || "Video uniqueizer failed. Check the browser console for details.";
}

async function loadFfmpegCore(ffmpeg, toBlobURL) {
  const localBase = `${window.location.origin}/ffmpeg`;
  const cdnBase = `https://cdn.jsdelivr.net/npm/@ffmpeg/core@${FFMPEG_CORE_VERSION}/dist/umd`;
  const candidates = [localBase, cdnBase];

  let lastError = null;
  for (const baseURL of candidates) {
    try {
      const sameOrigin = baseURL.startsWith(window.location.origin);
      if (sameOrigin) {
        await ffmpeg.load({
          coreURL: `${baseURL}/ffmpeg-core.js`,
          wasmURL: `${baseURL}/ffmpeg-core.wasm`,
        });
      } else {
        await ffmpeg.load({
          coreURL: await toBlobURL(`${baseURL}/ffmpeg-core.js`, "text/javascript"),
          wasmURL: await toBlobURL(`${baseURL}/ffmpeg-core.wasm`, "application/wasm"),
        });
      }
      return;
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError || new Error("Could not load FFmpeg engine.");
}

async function ensureDrawtextFont(ffmpeg, fontLoadedRef) {
  if (fontLoadedRef.current) return "/arial.ttf";
  const response = await fetch(DRAWTEXT_FONT_PATH);
  if (!response.ok) {
    throw new Error("Could not load drawtext font from this site.");
  }
  await ffmpeg.writeFile("/arial.ttf", new Uint8Array(await response.arrayBuffer()));
  fontLoadedRef.current = true;
  return "/arial.ttf";
}

async function mountSourceVideo(ffmpeg, file, mountId) {
  const mountDir = `/source-${mountId}`;
  const inputName = `source.${extensionFor(file, "mp4")}`;
  const sourceFile = new File([file], inputName, { type: file.type || "video/mp4" });
  await ffmpeg.createDir(mountDir);
  await ffmpeg.mount("WORKERFS", { files: [sourceFile] }, mountDir);
  return { mountDir, inputName: `${mountDir}/${inputName}` };
}

async function unmountSourceVideo(ffmpeg, mountDir) {
  try {
    await ffmpeg.unmount(mountDir);
  } catch {}
}

function buildPlan({ item, copyIndex, settings, phrases, hasWatermarks, hasAudio, hasComboVideos }) {
  const duration = Number(item.duration) || 0;
  const trimStart = settings.trim ? randomBetween(0.04, 0.55, 3) : 0;
  let trimEnd = settings.trim ? randomBetween(0.04, 0.65, 3) : 0;
  if (duration > 0 && duration - trimStart - trimEnd < 1) {
    trimEnd = Math.max(0, duration - trimStart - 1);
  }

  const speed = settings.speed ? randomBetween(0.94, 1.075, 4) : 1;
  const pitch = settings.audioPitch ? randomBetween(0.975, 1.035, 4) : 1;
  const staticText = pick(phrases);
  const runningText = pick(phrases);
  const watermarkPosition = pick(WATERMARK_POSITIONS);

  return {
    id: randomHex(6),
    copyIndex,
    trimStart,
    trimEnd,
    sourceDuration: duration,
    clipDuration: duration > 0 ? Math.max(0.8, duration - trimStart - trimEnd) : 0,
    speed,
    pitch,
    fps: settings.framerate ? pick(FRAME_RATE_POOL) : 30,
    borderPx: settings.border ? randomInt(4, 28) : 0,
    borderColor: settings.border ? randomColor() : "#000000",
    scale: settings.scale ? randomBetween(0.985, 1.045, 4) : 1,
    blur: settings.blur ? randomBetween(0.12, 0.55, 3) : 0,
    noise: settings.noise ? randomInt(2, 9) : 0,
    brightness: settings.color ? randomBetween(-0.025, 0.025, 4) : 0,
    contrast: settings.color ? randomBetween(0.965, 1.055, 4) : 1,
    saturation: settings.color ? randomBetween(0.94, 1.075, 4) : 1,
    gamma: settings.color ? randomBetween(0.97, 1.035, 4) : 1,
    hue: settings.color ? randomBetween(-2.2, 2.2, 3) : 0,
    staticText,
    staticTextSize: randomInt(26, 62),
    staticTextColor: randomColor(),
    staticTextBg: randomColor(),
    staticTextOpacity: randomBetween(0.42, 0.82, 2),
    staticTextX: randomBetween(0.06, 0.72, 3),
    staticTextY: randomBetween(0.08, 0.82, 3),
    staticTextStart: randomBetween(0.25, 1.8, 2),
    staticTextDuration: randomBetween(1.3, 4.8, 2),
    runningText,
    runningTextSize: randomInt(22, 46),
    runningTextColor: randomColor(),
    runningLineY: randomBetween(0.08, 0.88, 3),
    runningLineSpeed: randomInt(95, 250),
    watermark: settings.watermark && hasWatermarks,
    watermarkOpacity: randomBetween(0.18, 0.58, 2),
    watermarkWidth: randomInt(80, 260),
    watermarkPosition,
    watermarkStart: randomBetween(0.15, 2.5, 2),
    watermarkEnd: duration > 0 ? randomBetween(Math.max(2.6, duration * 0.45), Math.max(3, duration - trimEnd), 2) : 999,
    addAudio: settings.addAudio && hasAudio,
    addAudioMode: settings.addAudioMode,
    audioOverlayVolume: randomBetween(0.08, 0.28, 2),
    verticalCombo: settings.verticalCombo && hasComboVideos,
    crf: settings.codec ? randomInt(18, 26) : 23,
    gop: settings.codec ? randomInt(20, 80) : 48,
    bframes: settings.codec ? randomInt(0, 2) : 2,
    videoBitrate: settings.codec ? randomInt(2, 8) : 5,
    audioBitrate: settings.codec ? pick(AUDIO_BITRATES) : 192,
    preset: settings.codec ? pick(PRESETS) : "fast",
    title: `clip-${copyIndex + 1}-${randomHex(4)}`,
    creationTime: new Date(Date.now() - randomInt(1, 180) * 86400000 - randomInt(0, 86400) * 1000).toISOString(),
  };
}

function buildAudioFilters(plan) {
  const filters = [];
  if (Math.abs(plan.speed - 1) > 0.001) filters.push(`atempo=${plan.speed.toFixed(4)}`);
  if (Math.abs(plan.pitch - 1) > 0.001) {
    filters.push(`asetrate=44100*${plan.pitch.toFixed(4)}`);
    filters.push("aresample=44100");
    filters.push(`atempo=${(1 / plan.pitch).toFixed(4)}`);
  }
  filters.push(`volume=${randomBetween(0.94, 1.06, 3)}`);
  return filters;
}

function buildFilterGraph({ plan, settings, comboInputIndex, watermarkInputIndex, audioInputIndex, sourceHasAudio, fontPath }) {
  const chains = [];
  let current = "vbase";
  let labelIndex = 0;

  if (comboInputIndex != null) {
    chains.push(
      `[0:v]setpts=PTS/${plan.speed.toFixed(4)},scale=1080:960:force_original_aspect_ratio=decrease,pad=1080:960:(ow-iw)/2:(oh-ih)/2:color=black[top]`,
    );
    chains.push(
      `[${comboInputIndex}:v]setpts=PTS/${plan.speed.toFixed(4)},scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[bottom]`,
    );
    chains.push("[top][bottom]vstack=inputs=2[vbase]");
  } else {
    chains.push(`[0:v]setpts=PTS/${plan.speed.toFixed(4)}[vbase]`);
  }

  const applyVideoFilters = (filters) => {
    if (!filters.length) return;
    const next = `v${labelIndex++}`;
    chains.push(`[${current}]${filters.join(",")}[${next}]`);
    current = next;
  };

  const filters = [];
  if (plan.scale !== 1) filters.push(`scale=trunc(iw*${plan.scale.toFixed(4)}/2)*2:trunc(ih*${plan.scale.toFixed(4)}/2)*2`);
  if (plan.borderPx > 0) {
    filters.push(`pad=iw+${plan.borderPx * 2}:ih+${plan.borderPx * 2}:${plan.borderPx}:${plan.borderPx}:color=${colorValue(plan.borderColor)}`);
  }
  if (plan.blur > 0) filters.push(`boxblur=${plan.blur}:1`);
  if (plan.noise > 0) filters.push(`noise=alls=${plan.noise}:allf=t+u`);
  if (settings.color) {
    filters.push(
      `eq=brightness=${plan.brightness.toFixed(4)}:contrast=${plan.contrast.toFixed(4)}:saturation=${plan.saturation.toFixed(4)}:gamma=${plan.gamma.toFixed(4)}`,
    );
    filters.push(`hue=h=${plan.hue.toFixed(3)}`);
  }
  if (settings.framerate) filters.push(`fps=${plan.fps}`);
  applyVideoFilters(filters);

  if (settings.staticText && fontPath) {
    const end = plan.staticTextStart + plan.staticTextDuration;
    applyVideoFilters([
      `drawtext=fontfile=${fontPath}:text='${escapeDrawtextText(plan.staticText)}':fontcolor=${colorValue(plan.staticTextColor)}@${plan.staticTextOpacity}:fontsize=${plan.staticTextSize}:box=1:boxcolor=${colorValue(plan.staticTextBg)}@0.35:boxborderw=12:x=(w-tw)*${plan.staticTextX}:y=(h-th)*${plan.staticTextY}:enable='between(t,${plan.staticTextStart},${end})'`,
    ]);
  }

  if (settings.runningLine && fontPath) {
    applyVideoFilters([
      `drawtext=fontfile=${fontPath}:text='${escapeDrawtextText(plan.runningText)}':fontcolor=${colorValue(plan.runningTextColor)}@0.86:fontsize=${plan.runningTextSize}:box=1:boxcolor=0x000000@0.28:boxborderw=8:x=w-mod(t*${plan.runningLineSpeed}\\,w+tw):y=(h-th)*${plan.runningLineY}`,
    ]);
  }

  if (plan.watermark && watermarkInputIndex != null) {
    const wm = `wm${labelIndex++}`;
    const next = `v${labelIndex++}`;
    chains.push(
      `[${watermarkInputIndex}:v]scale=${plan.watermarkWidth}:-1,format=rgba,colorchannelmixer=aa=${plan.watermarkOpacity}[${wm}]`,
    );
    chains.push(
      `[${current}][${wm}]overlay=${plan.watermarkPosition.x}:${plan.watermarkPosition.y}:enable='between(t,${plan.watermarkStart},${plan.watermarkEnd})'[${next}]`,
    );
    current = next;
  }

  chains.push(`[${current}]format=yuv420p[vout]`);

  let audioMap = [];
  let audioArgs = [];
  const audioFilters = buildAudioFilters(plan);

  if (plan.addAudio && audioInputIndex != null && plan.addAudioMode === "replace") {
    audioMap = ["-map", `${audioInputIndex}:a:0`];
    audioArgs = audioFilters.length ? ["-filter:a", audioFilters.join(",")] : [];
  } else if (plan.addAudio && audioInputIndex != null && plan.addAudioMode === "overlay" && sourceHasAudio) {
    chains.push(`[0:a]${audioFilters.join(",")}[a0]`);
    chains.push(`[${audioInputIndex}:a]volume=${plan.audioOverlayVolume}[a1]`);
    chains.push("[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]");
    audioMap = ["-map", "[aout]"];
  } else if (plan.addAudio && audioInputIndex != null && plan.addAudioMode === "overlay") {
    audioMap = ["-map", `${audioInputIndex}:a:0`];
    audioArgs = [`-filter:a`, `volume=${plan.audioOverlayVolume}`];
  } else if (sourceHasAudio) {
    audioMap = ["-map", "0:a?"];
    audioArgs = audioFilters.length ? ["-filter:a", audioFilters.join(",")] : [];
  } else {
    audioArgs = ["-an"];
  }

  return {
    filter: chains.join(";"),
    audioMap,
    audioArgs,
  };
}

async function safeDelete(ffmpeg, path) {
  try {
    await ffmpeg.deleteFile(path);
  } catch {}
}

async function encodeUniqueVideo({
  ffmpeg,
  fetchFile,
  inputName,
  outputName,
  item,
  plan,
  settings,
  watermarkFile,
  audioFile,
  comboFile,
  sourceHasAudio,
  fontPath,
  onLog,
}) {
  const args = ["-hide_banner", "-loglevel", "error", "-y"];
  if (plan.trimStart > 0) args.push("-ss", plan.trimStart.toFixed(3));
  if (plan.clipDuration > 0) args.push("-t", plan.clipDuration.toFixed(3));
  args.push("-i", inputName);

  let inputIndex = 1;
  let comboInputIndex = null;
  let watermarkInputIndex = null;
  let audioInputIndex = null;
  const tempFiles = [];

  if (plan.verticalCombo && comboFile) {
    const comboName = `combo-${plan.id}.${extensionFor(comboFile, "mp4")}`;
    await ffmpeg.writeFile(comboName, await fetchFile(comboFile));
    tempFiles.push(comboName);
    args.push("-stream_loop", "-1");
    if (plan.clipDuration > 0) args.push("-t", plan.clipDuration.toFixed(3));
    args.push("-i", comboName);
    comboInputIndex = inputIndex++;
  }

  if (plan.watermark && watermarkFile) {
    const watermarkName = `watermark-${plan.id}.${extensionFor(watermarkFile, "png")}`;
    await ffmpeg.writeFile(watermarkName, await fetchFile(watermarkFile));
    tempFiles.push(watermarkName);
    args.push("-loop", "1", "-i", watermarkName);
    watermarkInputIndex = inputIndex++;
  }

  if (plan.addAudio && audioFile) {
    const audioName = `audio-${plan.id}.${extensionFor(audioFile, "mp3")}`;
    await ffmpeg.writeFile(audioName, await fetchFile(audioFile));
    tempFiles.push(audioName);
    args.push("-stream_loop", "-1");
    if (plan.clipDuration > 0) args.push("-t", Math.max(1, plan.clipDuration / plan.speed).toFixed(3));
    args.push("-i", audioName);
    audioInputIndex = inputIndex++;
  }

  const graph = buildFilterGraph({
    plan,
    settings,
    comboInputIndex,
    watermarkInputIndex,
    audioInputIndex,
    sourceHasAudio,
    fontPath,
  });

  args.push("-filter_complex", graph.filter);
  args.push("-map", "[vout]", ...graph.audioMap, ...graph.audioArgs);

  if (settings.metadata) {
    args.push("-map_metadata", "-1");
    args.push("-metadata", `title=${plan.title}`);
    args.push("-metadata", `creation_time=${plan.creationTime}`);
    args.push("-metadata", `software=Camera ${randomInt(12, 19)}.${randomInt(0, 9)}`);
    args.push("-metadata", `make=${pick(["Apple", "Samsung", "Google", "OnePlus"])}`);
    args.push("-metadata", `model=${pick(["iPhone 15", "iPhone 14", "Galaxy S24", "Pixel 8", "OnePlus 12"])}`);
  }

  args.push(
    "-c:v",
    "libx264",
    "-preset",
    plan.preset,
    "-crf",
    String(plan.crf),
    "-g",
    String(plan.gop),
    "-bf",
    String(plan.bframes),
    "-b:v",
    `${plan.videoBitrate}M`,
    "-r",
    String(plan.fps),
    "-pix_fmt",
    "yuv420p",
    "-c:a",
    "aac",
    "-b:a",
    `${plan.audioBitrate}k`,
    "-movflags",
    "+faststart",
    "-shortest",
    outputName,
  );

  try {
    const exitCode = await ffmpeg.exec(args);
    if (exitCode !== 0) {
      throw new Error(onLog?.() || `FFmpeg exited with code ${exitCode}`);
    }
    const data = await ffmpeg.readFile(outputName);
    return data instanceof Uint8Array ? data : new Uint8Array(data);
  } finally {
    await safeDelete(ffmpeg, outputName);
    await Promise.all(tempFiles.map((path) => safeDelete(ffmpeg, path)));
  }
}

function Toggle({ checked, onChange, title, detail, disabled = false }) {
  return (
    <div
      className={`flex items-start gap-3 rounded-2xl border p-3 transition ${
        checked
          ? "border-foreground/25 bg-foreground/5"
          : "border-border bg-muted/30 hover:bg-muted/50"
      } ${disabled ? "opacity-45" : ""}`}
    >
      <Switch
        checked={checked}
        onCheckedChange={onChange}
        disabled={disabled}
        className="mt-0.5"
        aria-label={title}
      />
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-foreground">{title}</span>
        <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">{detail}</span>
      </span>
    </div>
  );
}

export default function VideoUniqueizer() {
  const [sourceItems, setSourceItems] = useState([]);
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [phraseText, setPhraseText] = useState(DEFAULT_PHRASES.join("\n"));
  const [watermarkFiles, setWatermarkFiles] = useState([]);
  const [audioFiles, setAudioFiles] = useState([]);
  const [comboFiles, setComboFiles] = useState([]);
  const [status, setStatus] = useState("");
  const [progress, setProgress] = useState(0);
  const [running, setRunning] = useState(false);
  const [ffmpegLog, setFfmpegLog] = useState("");
  const ffmpegRef = useRef(null);
  const ffmpegLogRef = useRef("");
  const fontLoadedRef = useRef(false);
  const cancelRef = useRef(false);

  const phrases = useMemo(() => parsePhrases(phraseText), [phraseText]);
  const totalExports = useMemo(
    () => sourceItems.reduce((sum, item) => sum + clampNumber(item.copies, 1, 60, DEFAULT_COPIES), 0),
    [sourceItems],
  );

  const updateSetting = (key, value) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const ensureFfmpeg = async () => {
    if (ffmpegRef.current) return ffmpegRef.current;
    setStatus("Loading FFmpeg engine...");
    const [{ FFmpeg }, { toBlobURL }] = await Promise.all([
      import("@ffmpeg/ffmpeg"),
      import("@ffmpeg/util"),
    ]);
    const ffmpeg = new FFmpeg();
    ffmpeg.on("log", ({ message }) => {
      if (!message) return;
      ffmpegLogRef.current = message.slice(0, 260);
      setFfmpegLog(ffmpegLogRef.current);
    });
    await loadFfmpegCore(ffmpeg, toBlobURL);
    ffmpegRef.current = ffmpeg;
    return ffmpeg;
  };

  const handleSourceVideos = async (files) => {
    const picked = Array.from(files || [])
      .filter((file) => file?.type?.startsWith("video/") || /\.(mp4|mov|m4v|webm)$/i.test(file?.name || ""))
      .slice(0, MAX_SOURCE_VIDEOS);

    const oversized = picked.find((file) => file.size > MAX_SOURCE_FILE_MB * 1024 * 1024);
    if (oversized) {
      setStatus(`"${oversized.name}" is over ${MAX_SOURCE_FILE_MB} MB. Use a smaller file for browser FFmpeg.`);
      return;
    }

    const next = await Promise.all(
      picked.map(async (file) => {
        const meta = await getVideoMeta(file);
        return {
          id: `${Date.now()}-${randomHex(4)}`,
          file,
          copies: DEFAULT_COPIES,
          duration: meta.duration,
          hasAudio: meta.hasAudio,
        };
      }),
    );
    setSourceItems(next);
    setStatus(next.length ? `Loaded ${next.length} source video${next.length === 1 ? "" : "s"}.` : "");
  };

  const updateCopies = (id, value) => {
    setSourceItems((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, copies: clampNumber(value, 1, 60, DEFAULT_COPIES) } : item,
      ),
    );
  };

  const stopRun = () => {
    cancelRef.current = true;
    setStatus("Stopping after the current FFmpeg step...");
    try {
      ffmpegRef.current?.terminate();
    } catch {}
    ffmpegRef.current = null;
  };

  const runExports = async () => {
    if (!sourceItems.length || running) return;
    cancelRef.current = false;
    setRunning(true);
    setProgress(0);
    setFfmpegLog("");
    ffmpegLogRef.current = "";
    fontLoadedRef.current = false;
    const manifest = [];

    try {
      const [{ fetchFile }, { zipSync, strToU8 }] = await Promise.all([
        import("@ffmpeg/util"),
        import("fflate"),
      ]);
      const ffmpeg = await ensureFfmpeg();
      const needsFont = settings.staticText || settings.runningLine;
      const fontPath = needsFont ? await ensureDrawtextFont(ffmpeg, fontLoadedRef) : null;
      const zipEntries = {};
      let completed = 0;

      for (let sourceIndex = 0; sourceIndex < sourceItems.length; sourceIndex++) {
        const item = sourceItems[sourceIndex];
        if (cancelRef.current) break;
        setStatus(`Loading ${item.file.name}...`);
        const { mountDir, inputName } = await mountSourceVideo(ffmpeg, item.file, `${sourceIndex}-${randomHex(4)}`);

        try {
          const copies = clampNumber(item.copies, 1, 60, DEFAULT_COPIES);
          for (let copyIndex = 0; copyIndex < copies; copyIndex++) {
            if (cancelRef.current) break;
            const plan = buildPlan({
              item,
              copyIndex,
              settings,
              phrases,
              hasWatermarks: watermarkFiles.length > 0,
              hasAudio: audioFiles.length > 0,
              hasComboVideos: comboFiles.length > 0,
            });
            const outputName = `out-${plan.id}.mp4`;
            const zipName = `${sanitizeName(item.file.name)}-${String(copyIndex + 1).padStart(2, "0")}-${plan.id}.mp4`;
            setStatus(`Encoding ${item.file.name} copy ${copyIndex + 1} of ${copies}...`);
            const bytes = await encodeUniqueVideo({
              ffmpeg,
              fetchFile,
              inputName,
              outputName,
              item,
              plan,
              settings,
              watermarkFile: watermarkFiles.length ? pick(watermarkFiles) : null,
              audioFile: audioFiles.length ? pick(audioFiles) : null,
              comboFile: comboFiles.length ? pick(comboFiles) : null,
              sourceHasAudio: item.hasAudio,
              fontPath,
              onLog: () => ffmpegLogRef.current,
            });
            zipEntries[zipName] = [
              bytes,
              {
                level: 0,
                mtime: Date.now() - randomInt(0, 30) * 86400000,
                comment: randomHex(5),
              },
            ];
            manifest.push({
              file: zipName,
              source: item.file.name,
              copy: copyIndex + 1,
              settings: plan,
            });
            completed++;
            setProgress(Math.round((completed / totalExports) * 96));
            await new Promise((resolve) => setTimeout(resolve, 0));
          }
        } finally {
          await unmountSourceVideo(ffmpeg, mountDir);
        }
      }

      if (cancelRef.current) {
        setStatus("Export stopped.");
        return;
      }

      setStatus("Building ZIP...");
      zipEntries["manifest.json"] = [
        strToU8(JSON.stringify({ createdAt: new Date().toISOString(), totalExports, manifest }, null, 2)),
        { level: 1, mtime: Date.now(), comment: randomHex(4) },
      ];
      const zipData = zipSync(zipEntries, { level: 0 });
      downloadBlob(new Blob([zipData], { type: "application/zip" }), `video-uniqueizer-${randomHex(6)}.zip`);
      setProgress(100);
      setStatus(`Done. Downloaded ${completed} unique exports in one ZIP.`);
    } catch (error) {
      console.error("[video uniqueizer]", error);
      setStatus(
        cancelRef.current
          ? "Export stopped."
          : formatFfmpegError(error, ffmpegLogRef.current),
      );
    } finally {
      setRunning(false);
      setTimeout(() => {
        if (!cancelRef.current) {
          setProgress(0);
          setFfmpegLog("");
        }
      }, 5000);
    }
  };

  const canRun = sourceItems.length > 0 && !running;

  return (
    <div className="min-h-full p-2 text-foreground md:p-4">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-5">
        <section className="dash-card p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-muted-foreground">Video Uniqueizer</p>
              <h1 className="mt-2 text-3xl font-bold tracking-tighter md:text-4xl">Batch randomized exports for owned videos</h1>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">
                Upload 1-3 source videos, choose how many variants each one needs, then generate a ZIP of locally processed
                MP4 files. Every export gets its own random visual, audio, codec, and metadata settings. Results vary by
                platform, account history, and content, so this tool does not guarantee any specific distribution outcome.
              </p>
            </div>
            <div className="page-banner rounded-2xl px-4 py-3 text-xs leading-5 lg:max-w-sm">
              Use this only for content you own or have permission to repurpose. Browser FFmpeg is CPU-heavy, so many
              exports can take a while. Keep each source video under {MAX_SOURCE_FILE_MB} MB for reliable processing.
            </div>
          </div>
        </section>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_390px]">
          <div className="flex flex-col gap-5">
            <section className="adv-section">
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <h2 className="text-lg font-bold">Source videos</h2>
                  <p className="mt-1 text-xs text-muted-foreground">Pick up to 3 videos. Set copies per video after upload.</p>
                </div>
                <label className="btn-primary inline-flex cursor-pointer px-4 py-2 text-sm font-bold">
                  Upload videos
                  <input
                    type="file"
                    accept={VIDEO_ACCEPT}
                    multiple
                    disabled={running}
                    onChange={(e) => {
                      void handleSourceVideos(e.target.files);
                      e.target.value = "";
                    }}
                    className="sr-only"
                  />
                </label>
              </div>

              <div className="mt-4 grid gap-3">
                {sourceItems.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-border bg-muted/30 p-6 text-center text-sm text-muted-foreground/80">
                    No source videos yet.
                  </div>
                ) : (
                  sourceItems.map((item, index) => (
                    <div key={item.id} className="grid gap-3 rounded-2xl border border-border bg-muted/40 p-4 md:grid-cols-[1fr_150px] md:items-center">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-foreground">
                          {index + 1}. {item.file.name}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground/80">
                          {(item.file.size / (1024 * 1024)).toFixed(1)} MB
                          {item.duration ? ` - ${item.duration.toFixed(1)}s` : ""}
                        </p>
                      </div>
                      <label className="text-xs font-semibold text-muted-foreground">
                        Unique exports
                        <input
                          type="number"
                          min="1"
                          max="60"
                          value={item.copies}
                          disabled={running}
                          onChange={(e) => updateCopies(item.id, e.target.value)}
                          className="mt-1 w-full rounded-xl border border-border bg-muted/50 px-3 py-2 text-sm font-bold text-foreground outline-none focus:border-ring"
                        />
                      </label>
                    </div>
                  ))
                )}
              </div>
            </section>

            <section className="adv-section">
              <h2 className="text-lg font-bold">Randomization layers</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                These ranges are intentionally subtle by default so each export changes technically without wrecking the clip.
              </p>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <Toggle checked={settings.noise} onChange={(v) => updateSetting("noise", v)} title="Noise overlay" detail="Adds per-frame grain at a random low strength." />
                <Toggle checked={settings.framerate} onChange={(v) => updateSetting("framerate", v)} title="Change framerate" detail="Picks 24, 25, 30, 48, or 60 fps per export." />
                <Toggle checked={settings.border} onChange={(v) => updateSetting("border", v)} title="Border overlay" detail="Adds a random color border with random thickness." />
                <Toggle checked={settings.speed} onChange={(v) => updateSetting("speed", v)} title="Video speed" detail="Slightly adjusts playback speed per copy." />
                <Toggle checked={settings.trim} onChange={(v) => updateSetting("trim", v)} title="Trim milliseconds" detail="Cuts a small random amount from front and end." />
                <Toggle checked={settings.scale} onChange={(v) => updateSetting("scale", v)} title="Scaling" detail="Applies a small random resize per export." />
                <Toggle checked={settings.blur} onChange={(v) => updateSetting("blur", v)} title="Blur" detail="Applies a tiny random blur range." />
                <Toggle checked={settings.color} onChange={(v) => updateSetting("color", v)} title="Color micro-shift" detail="Randomizes brightness, contrast, gamma, saturation, and hue." />
                <Toggle checked={settings.audioPitch} onChange={(v) => updateSetting("audioPitch", v)} title="Audio pitch" detail="Slightly shifts audio pitch and volume." />
                <Toggle checked={settings.metadata} onChange={(v) => updateSetting("metadata", v)} title="Change metadata" detail="Strips original metadata and writes random creation/title/device tags." />
                <Toggle checked={settings.codec} onChange={(v) => updateSetting("codec", v)} title="Codec randomization" detail="Randomizes CRF, GOP, B-frames, bitrate, preset, and audio bitrate." />
              </div>
            </section>

            <section className="adv-section">
              <h2 className="text-lg font-bold">Text, watermark, audio, and combo inputs</h2>
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                <div className="rounded-2xl border border-border bg-muted/40 p-4">
                  <div className="grid gap-3">
                    <Toggle checked={settings.runningLine} onChange={(v) => updateSetting("runningLine", v)} title="Running line" detail="Scrolls a random phrase across the video." />
                    <Toggle checked={settings.staticText} onChange={(v) => updateSetting("staticText", v)} title="Static text" detail="Shows a random phrase at random size, color, position, start, and duration." />
                    <label className="block text-xs font-semibold text-muted-foreground">
                      Phrase list
                      <textarea
                        value={phraseText}
                        disabled={running}
                        onChange={(e) => setPhraseText(e.target.value)}
                        rows={8}
                        className="mt-2 w-full resize-y rounded-2xl border border-border bg-muted/50 p-3 text-xs leading-5 text-foreground outline-none focus:border-ring"
                      />
                    </label>
                    <label className="inline-flex cursor-pointer items-center justify-center rounded-xl border border-border bg-muted/50 px-3 py-2 text-xs font-bold text-foreground/80 hover:bg-white/10">
                      Load phrases .txt
                      <input
                        type="file"
                        accept=".txt,text/plain"
                        disabled={running}
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) void file.text().then(setPhraseText);
                          e.target.value = "";
                        }}
                        className="sr-only"
                      />
                    </label>
                  </div>
                </div>

                <div className="grid gap-4">
                  <div className="rounded-2xl border border-border bg-muted/40 p-4">
                    <Toggle
                      checked={settings.watermark}
                      onChange={(v) => updateSetting("watermark", v)}
                      title="Watermark"
                      detail="Overlays a random image with random opacity, size, position, and timing."
                    />
                    <label className="mt-3 block text-xs font-semibold text-muted-foreground">
                      Watermark images
                      <input
                        type="file"
                        accept={IMAGE_ACCEPT}
                        multiple
                        disabled={running}
                        onChange={(e) => setWatermarkFiles(Array.from(e.target.files || []))}
                        className="mt-2 w-full text-xs text-muted-foreground file:mr-3 file:rounded-lg file:border-0 file:bg-white/10 file:px-3 file:py-2 file:text-xs file:font-bold file:text-foreground"
                      />
                    </label>
                    <p className="mt-2 text-xs text-muted-foreground/70">{watermarkFiles.length} image(s) loaded</p>
                  </div>

                  <div className="rounded-2xl border border-border bg-muted/40 p-4">
                    <Toggle
                      checked={settings.addAudio}
                      onChange={(v) => updateSetting("addAudio", v)}
                      title="Add audio"
                      detail="Picks a random audio file to overlay or replace the original track."
                    />
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                      {["overlay", "replace"].map((mode) => (
                        <button
                          key={mode}
                          type="button"
                          disabled={running}
                          onClick={() => updateSetting("addAudioMode", mode)}
                          className={`rounded-xl px-3 py-2 font-bold capitalize ${
                            settings.addAudioMode === mode ? "bg-foreground text-background" : "bg-muted/50 text-muted-foreground"
                          }`}
                        >
                          {mode}
                        </button>
                      ))}
                    </div>
                    <label className="mt-3 block text-xs font-semibold text-muted-foreground">
                      Audio files
                      <input
                        type="file"
                        accept={AUDIO_ACCEPT}
                        multiple
                        disabled={running}
                        onChange={(e) => setAudioFiles(Array.from(e.target.files || []))}
                        className="mt-2 w-full text-xs text-muted-foreground file:mr-3 file:rounded-lg file:border-0 file:bg-white/10 file:px-3 file:py-2 file:text-xs file:font-bold file:text-foreground"
                      />
                    </label>
                    <p className="mt-2 text-xs text-muted-foreground/70">{audioFiles.length} audio file(s) loaded</p>
                  </div>

                  <div className="rounded-2xl border border-border bg-muted/40 p-4">
                    <Toggle
                      checked={settings.verticalCombo}
                      onChange={(v) => updateSetting("verticalCombo", v)}
                      title="Vertical video combo"
                      detail="Stacks the source video on top and a random background clip below."
                    />
                    <label className="mt-3 block text-xs font-semibold text-muted-foreground">
                      Bottom videos
                      <input
                        type="file"
                        accept={VIDEO_ACCEPT}
                        multiple
                        disabled={running}
                        onChange={(e) => setComboFiles(Array.from(e.target.files || []))}
                        className="mt-2 w-full text-xs text-muted-foreground file:mr-3 file:rounded-lg file:border-0 file:bg-white/10 file:px-3 file:py-2 file:text-xs file:font-bold file:text-foreground"
                      />
                    </label>
                    <p className="mt-2 text-xs text-muted-foreground/70">{comboFiles.length} bottom video(s) loaded</p>
                  </div>
                </div>
              </div>
            </section>
          </div>

          <aside className="adv-section h-fit xl:sticky xl:top-6">
            <h2 className="text-lg font-bold">Export queue</h2>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="rounded-2xl bg-muted/40 p-4">
                <p className="text-xs uppercase tracking-widest text-muted-foreground/70">Videos</p>
                <p className="mt-1 text-2xl font-black">{sourceItems.length}</p>
              </div>
              <div className="rounded-2xl bg-muted/40 p-4">
                <p className="text-xs uppercase tracking-widest text-muted-foreground/70">Exports</p>
                <p className="mt-1 text-2xl font-black">{totalExports}</p>
              </div>
            </div>

            <button
              type="button"
              disabled={!canRun}
              onClick={() => void runExports()}
              className="btn-primary mt-5 w-full disabled:pointer-events-none disabled:opacity-35"
            >
              {running ? "Generating..." : "Generate unique ZIP"}
            </button>
            {running ? (
              <button
                type="button"
                onClick={stopRun}
                className="btn-outline mt-3 w-full text-destructive"
              >
                Stop
              </button>
            ) : null}

            <div className="mt-5">
              <div className="h-2 overflow-hidden rounded-full bg-muted border border-border/50">
                <div className="h-full rounded-full bg-foreground transition-all" style={{ width: `${progress}%` }} />
              </div>
              <p className="mt-3 min-h-5 text-xs leading-5 text-muted-foreground">{status || "Ready."}</p>
              {ffmpegLog ? <p className="mt-2 break-words text-[11px] leading-4 text-white/30">{ffmpegLog}</p> : null}
            </div>

            <div className="mt-5 rounded-2xl border border-border bg-muted/40 p-4 text-xs leading-5 text-muted-foreground">
              <p className="font-bold text-foreground/70">What changes per copy:</p>
              <p className="mt-2">
                Visual filters, frame timing, tiny trims, borders, optional text, optional image watermark, optional audio,
                H.264 encode settings, and metadata are randomized independently for every generated file.
              </p>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
