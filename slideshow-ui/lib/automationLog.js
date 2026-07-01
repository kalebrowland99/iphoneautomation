/** Scrollable activity log for /automation farm runs (client-only). */

const listeners = new Set();

/** @type {{ id: string, ts: number, message: string, level: string }[]} */
let entries = [];
let lastMessage = "";

export function clearAutomationLog() {
  entries = [];
  lastMessage = "";
  emit();
}

export function getAutomationLogEntries() {
  return entries;
}

export function subscribeAutomationLog(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit() {
  for (const fn of listeners) fn();
}

/**
 * @param {string} message
 * @param {"info" | "success" | "error" | "warn"} [level]
 */
export function appendAutomationLog(message, level = "info") {
  const msg = String(message || "").trim();
  if (!msg) return;
  if (msg === lastMessage) return;
  lastMessage = msg;
  entries = [
    ...entries.slice(-199),
    {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      ts: Date.now(),
      message: msg,
      level,
    },
  ];
  emit();
}
