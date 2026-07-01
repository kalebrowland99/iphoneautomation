/** Upload encoded MP4 bytes to the iMouse farm gallery ingest API. */

import { appendAutomationLog } from "@/lib/automationLog";

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

export function shouldAutoRunFarmJob(jobId) {
  const state = getFarmJobAutoRunState(jobId);
  if (!state) return true;
  return state !== "started" && state !== "done" && state !== "cancelled" && state !== "failed";
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
  const base = String(farmUrl || "").replace(/\/+$/, "");
  if (!base || !jobId) return null;
  const headers = {};
  if (secret) headers["X-Farm-Secret"] = secret;
  const res = await fetch(`${base}/api/slideshow/jobs/${encodeURIComponent(jobId)}`, {
    headers,
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

/** Parse FastAPI / farm error bodies into a short user-facing string. */
async function readFarmErrorResponse(res) {
  const text = await res.text();
  if (!text) return `HTTP ${res.status}`;
  try {
    const body = JSON.parse(text);
    if (typeof body?.detail === "string") return body.detail;
    if (body?.detail != null) return JSON.stringify(body.detail);
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

  const base = String(farmUrl || "").replace(/\/+$/, "");
  const res = await fetch(`${base}/api/slideshow/ingest`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) {
    throw new Error(await readFarmErrorResponse(res));
  }
  return res.json();
}

export async function notifyAutomationDone({ farmUrl, jobId, secret }) {
  const headers = {};
  if (secret) headers["X-Farm-Secret"] = secret;

  const base = String(farmUrl || "").replace(/\/+$/, "");
  const res = await fetch(
    `${base}/api/slideshow/jobs/${encodeURIComponent(jobId)}/automation-done`,
    { method: "POST", headers },
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
}
