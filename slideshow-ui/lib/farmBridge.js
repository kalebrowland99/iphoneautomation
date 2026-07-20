/** Upload encoded MP4 bytes to the iMouse farm gallery ingest API. */

import { appendAutomationLog } from "@/lib/automationLog";

// Retries are sized to survive a full farm-dashboard restart mid-upload
// (restart.ps1 can take ~90s). With capped backoff the total retry window is
// ~2 min, so a bounced dashboard no longer fails the phone's upload.
const FARM_UPLOAD_RETRIES = 15;
const FARM_UPLOAD_RETRY_MS = 1500;
const FARM_UPLOAD_RETRY_MAX_MS = 8000;

function farmRetryDelayMs(attempt) {
  return Math.min(FARM_UPLOAD_RETRY_MS * attempt, FARM_UPLOAD_RETRY_MAX_MS);
}

let _farmNotifyContext = { farmUrl: "", secret: "" };

/** Set once from /automation so markFarmJobFailed can notify the farm server. */
export function setFarmNotifyContext({ farmUrl, secret } = {}) {
  _farmNotifyContext = {
    farmUrl: String(farmUrl || "").trim(),
    secret: String(secret || "").trim(),
  };
}

/** Local dev: route farm API through Next.js (/farm-api) to avoid cross-origin fetch failures. */
export function resolveFarmApiBase(farmUrl) {
  const base = String(farmUrl || "").replace(/\/+$/, "");
  if (!base || typeof window === "undefined") return base;
  try {
    const target = new URL(base);
    const localFarm =
      (target.hostname === "localhost" || target.hostname === "127.0.0.1") &&
      (!target.port || target.port === "8080");
    const onSlideshowUi =
      window.location.port === "3000" ||
      window.location.hostname === "localhost" ||
      window.location.hostname === "127.0.0.1";
    if (localFarm && onSlideshowUi) {
      return "/farm-api";
    }
  } catch {
    /* use absolute farmUrl */
  }
  return base;
}

function farmApiUrl(farmUrl, path) {
  const base = resolveFarmApiBase(farmUrl);
  const suffix = String(path || "").replace(/^\/+/, "");
  if (base.startsWith("/")) {
    return `${base}/${suffix}`;
  }
  return `${base}/api/${suffix}`;
}

function isNetworkFetchError(err) {
  return (
    err instanceof TypeError ||
    String(err?.message || err).toLowerCase().includes("failed to fetch")
  );
}

async function farmFetch(url, options, { retries = 0, retryOn = null } = {}) {
  let lastErr;
  const attempts = Math.max(1, Number(retries) + 1);
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      const res = await fetch(url, options);
      if (retryOn?.(res.status) && attempt < attempts) {
        await new Promise((r) => setTimeout(r, farmRetryDelayMs(attempt)));
        continue;
      }
      return res;
    } catch (err) {
      lastErr = err;
      if (!isNetworkFetchError(err) || attempt >= attempts) break;
      await new Promise((r) => setTimeout(r, farmRetryDelayMs(attempt)));
    }
  }
  const hint =
    "Could not reach the farm dashboard — confirm it is running on port 8080, then retry.";
  throw new Error(lastErr?.message ? `${lastErr.message}. ${hint}` : hint);
}

const FARM_AUTORUN_PREFIX = "autoslide_farm_autorun_v1:";

function farmAutoRunKey(jobId) {
  return `${FARM_AUTORUN_PREFIX}${String(jobId || "").trim()}`;
}

/** @returns {null | "started" | "done" | "cancelled" | "failed"} */
export function getFarmJobAutoRunState(jobId) {
  if (typeof window === "undefined" || !jobId) return null;
  try {
    const raw = window.sessionStorage.getItem(farmAutoRunKey(jobId));
    return raw || null;
  } catch {
    return null;
  }
}

export function shouldAutoRunFarmJob(_jobId) {
  return true;
}

export function markFarmJobAutoRunStarted(jobId) {
  if (typeof window === "undefined" || !jobId) return;
  try {
    window.sessionStorage.setItem(farmAutoRunKey(jobId), "started");
  } catch {
    /* ignore */
  }
}

export function markFarmJobAutoRunFinished(jobId) {
  if (typeof window === "undefined" || !jobId) return;
  try {
    window.sessionStorage.setItem(farmAutoRunKey(jobId), "done");
  } catch {
    /* ignore */
  }
}

export function markFarmJobAutoRunCancelled(jobId) {
  if (typeof window === "undefined" || !jobId) return;
  try {
    window.sessionStorage.setItem(farmAutoRunKey(jobId), "cancelled");
  } catch {
    /* ignore */
  }
}

export function markFarmJobAutoRunFailed(jobId) {
  if (typeof window === "undefined" || !jobId) return;
  try {
    window.sessionStorage.setItem(farmAutoRunKey(jobId), "failed");
  } catch {
    /* ignore */
  }
}

export async function fetchFarmJobStatus({ farmUrl, jobId, secret }) {
  if (!farmUrl || !jobId) return null;
  const headers = {};
  if (secret) headers["X-Farm-Secret"] = secret;
  const res = await farmFetch(
    farmApiUrl(farmUrl, `slideshow/jobs/${encodeURIComponent(jobId)}`),
    {
      headers,
      cache: "no-store",
    },
  );
  if (!res.ok) return null;
  return res.json();
}

/** Parse farm ingest rejection bodies (422 blank slide / blank video). */
export class FarmUploadError extends Error {
  constructor(message, { retry = false, reason = "" } = {}) {
    super(message);
    this.name = "FarmUploadError";
    this.retry = retry;
    this.reason = reason;
  }
}

function farmUploadErrorFromBody(text, status) {
  const trimmed = String(text || "").trim();
  if (/^internal server error$/i.test(trimmed)) {
    return new FarmUploadError(
      "Farm server error during upload — the dashboard may have restarted. Retry this phone.",
      { reason: "server_error" },
    );
  }
  if (!trimmed) return new FarmUploadError(`HTTP ${status}`);
  try {
    const body = JSON.parse(text);
    const detail = body?.detail;
    if (detail && typeof detail === "object") {
      return new FarmUploadError(
        detail.message || detail.reason || "Farm upload rejected",
        { retry: Boolean(detail.retry), reason: String(detail.reason || "") },
      );
    }
    if (typeof detail === "string") return new FarmUploadError(detail);
    if (typeof body?.message === "string") return new FarmUploadError(body.message);
    if (typeof body?.error === "string") return new FarmUploadError(body.error);
  } catch {
    /* plain text */
  }
  return new FarmUploadError(trimmed);
}

function shouldRetryUpload(status) {
  return !status || status >= 500 || status === 408 || status === 429;
}

/** Parse FastAPI / farm error bodies into a short user-facing string. */
async function readFarmErrorResponse(res) {
  const text = await res.text();
  if (!text) return `HTTP ${res.status}`;
  try {
    const body = JSON.parse(text);
    if (typeof body?.detail === "string") return body.detail;
    if (body?.detail != null && typeof body.detail === "object") {
      return body.detail.message || body.detail.reason || JSON.stringify(body.detail);
    }
    if (typeof body?.message === "string") return body.message;
    if (typeof body?.error === "string") return body.error;
  } catch {
    /* plain text */
  }
  return text;
}

export async function uploadMp4ToFarm({
  farmUrl,
  jobId,
  secret,
  slot,
  file,
  filename,
  clear = false,
}) {
  const form = new FormData();
  const blob = file instanceof Blob ? file : new Blob([file], { type: "video/mp4" });
  form.append("file", blob, filename);
  form.append("slot", String(slot));
  form.append("job_id", String(jobId || ""));
  if (clear) form.append("clear", "true");

  const headers = {};
  if (secret) headers["X-Farm-Secret"] = secret;

  const res = await farmFetch(
    farmApiUrl(farmUrl, "slideshow/ingest"),
    {
      method: "POST",
      headers,
      body: form,
    },
    { retries: FARM_UPLOAD_RETRIES, retryOn: shouldRetryUpload },
  );
  if (!res.ok) {
    const text = await res.text();
    throw farmUploadErrorFromBody(text, res.status);
  }
  return res.json();
}

export async function notifyAutomationFailed({ farmUrl, jobId, secret, error }) {
  const headers = { "Content-Type": "application/json" };
  if (secret) headers["X-Farm-Secret"] = secret;
  const res = await farmFetch(
    farmApiUrl(farmUrl, `slideshow/jobs/${encodeURIComponent(jobId)}/automation-failed`),
    {
      method: "POST",
      headers,
      body: JSON.stringify({ error: String(error || "Automation failed") }),
    },
    { retries: 2 },
  );
  if (!res.ok) {
    throw new Error(await readFarmErrorResponse(res));
  }
  return res.json();
}

export async function notifyAutomationDone({ farmUrl, jobId, secret }) {
  const headers = {};
  if (secret) headers["X-Farm-Secret"] = secret;

  const res = await farmFetch(
    farmApiUrl(farmUrl, `slideshow/jobs/${encodeURIComponent(jobId)}/automation-done`),
    { method: "POST", headers },
    { retries: FARM_UPLOAD_RETRIES },
  );
  if (!res.ok) {
    throw new Error(await readFarmErrorResponse(res));
  }
  return res.json();
}

export function setFarmJobStatus(message) {
  const text = String(message || "");
  if (typeof window !== "undefined") {
    window.__FARM_JOB_STATUS__ = text;
  }
  appendAutomationLog(text);
}

export function markFarmJobDone(jobId) {
  if (typeof window !== "undefined") {
    window.__FARM_JOB_DONE__ = true;
  }
  appendAutomationLog("Farm job completed successfully.", "success");
  if (jobId) markFarmJobAutoRunFinished(jobId);
}

export function markFarmJobFailed(message, jobId) {
  const text = String(message || "Farm automation failed");
  if (typeof window !== "undefined") {
    window.__FARM_JOB_ERROR__ = text;
  }
  appendAutomationLog(text, "error");
  if (jobId) markFarmJobAutoRunFailed(jobId);
  const ctx = _farmNotifyContext;
  if (jobId && ctx.farmUrl) {
    void notifyAutomationFailed({
      farmUrl: ctx.farmUrl,
      jobId,
      secret: ctx.secret,
      error: text,
    }).catch(() => {
      /* server may be down; orchestrator wait will still time out */
    });
  }
}
