/** Gallery + exports scope saved shows to the editor app (Labely / Valcoin / Thrifty). */
export function normalizeSavedShowAppId(show) {
  const v = String(show?.appId ?? "").trim();
  if (v === "labely" || v === "valcoin" || v === "thrifty") return v;
  return "thrifty";
}

export function savedShowMatchesApp(show, appId) {
  return normalizeSavedShowAppId(show) === (appId ?? "thrifty");
}
