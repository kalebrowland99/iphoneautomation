/**
 * Maps Firebase / network errors to short UI copy (full message for tooltips / console).
 * @param {unknown} err
 * @returns {{ short: string, detail: string }}
 */
export function firebaseFriendlyError(err) {
  const code = typeof err === "object" && err && "code" in err ? String(/** @type {{ code?: string }} */ (err).code) : "";
  const msg = typeof err === "object" && err && "message" in err
    ? String(/** @type {{ message?: string }} */ (err).message)
    : String(err ?? "");

  if (code === "auth/unauthorized-domain" || msg.includes("unauthorized-domain")) {
    return {
      short: "Firebase: add this exact URL host in Auth → Settings → Authorized domains",
      detail: msg || code,
    };
  }
  if (code === "auth/operation-not-allowed" || msg.includes("OPERATION_NOT_ALLOWED")) {
    return {
      short: "Firebase: enable Anonymous in Authentication → Sign-in method",
      detail: msg || code,
    };
  }
  if (code === "permission-denied" || msg.includes("permission-denied")) {
    return {
      short: "Firebase: deploy Firestore/Storage rules (users/{uid}/…)",
      detail: msg || code,
    };
  }
  if (code === "failed-precondition" || msg.includes("failed-precondition")) {
    return {
      short: "Firebase: create Firestore DB / Storage bucket in console",
      detail: msg || code,
    };
  }

  return {
    short: code ? `Firebase: ${code}` : "Firebase: see browser console (F12)",
    detail: msg || code || "unknown error",
  };
}
