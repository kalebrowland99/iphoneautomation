/** Labely score 0-100 and rating labels (must match API / prompts). */

export const BAD_LABELY_SCORE = 17;
export const MIN_BAD_LABELY_SCORE = 1;
export const MAX_BAD_LABELY_SCORE = 30;
export const BAD_LABELY_VERDICT = "Avoid";

export function randomBadLabelyScore() {
  return MIN_BAD_LABELY_SCORE + Math.floor(Math.random() * (MAX_BAD_LABELY_SCORE - MIN_BAD_LABELY_SCORE + 1));
}

export function normalizeBadLabelyScore(_score) {
  return randomBadLabelyScore();
}

export function clampLabelyScore(score) {
  const n = Number(score);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, Math.round(n)));
}

export function ratingLabelFromScore(score) {
  const s = clampLabelyScore(score);
  if (s <= 30) return "Avoid";
  if (s <= 45) return "Limit";
  if (s <= 60) return "Okay Occasionally";
  if (s <= 80) return "Good";
  return "Great";
}
