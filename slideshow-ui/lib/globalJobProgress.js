/** Client-side long job UI (generate / export). Not a server queue — survives only while this tab runs. */

const listeners = new Set();

/** @type {null | {
 *   percent: number,
 *   phase: string,
 *   paused: boolean,
 *   hint?: string,
 * }} */
let job = null;

export function subscribeGlobalJob(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit() {
  for (const fn of listeners) fn();
}

/** @param {NonNullable<typeof job>} next */
export function setGlobalJob(next) {
  job = next;
  emit();
}

export function patchGlobalJob(/** @type {Partial<NonNullable<typeof job>>} */ patch) {
  if (!job) return;
  job = { ...job, ...patch };
  emit();
}

export function clearGlobalJob() {
  job = null;
  emit();
}

export function getGlobalJob() {
  return job;
}

/** Wired from ConfigPanel so the bar can pause / resume / stop without prop drilling. */
export const jobControls = {
  pause() {},
  resume() {},
  stop() {},
};

const HEARTBEAT_KEY = "autoslide_job_heartbeat_v1";

export function writeJobHeartbeat(/** @type {{ percent: number, phase: string }} */ payload) {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      HEARTBEAT_KEY,
      JSON.stringify({ ...payload, ts: Date.now() })
    );
  } catch {
    /* ignore */
  }
}

export function clearJobHeartbeat() {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(HEARTBEAT_KEY);
  } catch {
    /* ignore */
  }
}

/** @returns {null | { percent: number, phase: string, ts: number }} */
export function readJobHeartbeat() {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(HEARTBEAT_KEY);
    if (!raw) return null;
    const o = JSON.parse(raw);
    if (!o || typeof o.ts !== "number") return null;
    return o;
  } catch {
    return null;
  }
}
