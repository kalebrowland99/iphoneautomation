/**
 * Per-generation micro-jitter for anti-fingerprinting.
 *
 * Every generation gets a fresh `jitterSeed` stored in config.
 * Within one generation the values are stable (same seed → same offsets),
 * so preview and export always match.
 *
 * Usage in a slide component:
 *   import { makeJitter } from "@/lib/jitter";
 *   const J = makeJitter(config?.jitterSeed ?? 0);
 *   // J(elementId, maxPt) → integer offset in slide points, e.g. ±2
 *   height: px(navH + J(1, 2))
 */
export function makeJitter(seed) {
  return function J(id, maxPt = 2) {
    // Mix seed and element id with two cheap hash steps
    const h = (Math.imul(seed ^ 0xdeadbeef, 2654435761) ^ Math.imul(id * 40503, 0x9e3779b9)) >>> 0;
    const range = maxPt * 2 + 1;          // e.g. maxPt=2 → range 5 (-2…+2)
    return (h % range) - maxPt;           // integer in [-maxPt, +maxPt]
  };
}
