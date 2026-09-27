// The logic behind the "minimum match" slider. Pure: never touches its inputs, and at the
// default (0 = "All") hands back the very same arrays, so the app is unchanged until it moves.
import { formatScorePct } from './format'
import type { Overlap, Project } from './types'

/** Slider stops: 0, 0.05, …, 0.90 (every 5%). `i * 5 / 100` is exact (e.g. 0.7), unlike `0.05 * i`. */
export const MATCH_STEPS: readonly number[] = Object.freeze(Array.from({ length: 19 }, (_, i) => (i * 5) / 100))

/** 0 means "All": no filtering. */
export const DEFAULT_MIN_MATCH = 0

/** The step's whole percent (0, 5, …, 90). Fails loud on anything that isn't a slider stop. */
function stepPct(min: number): number {
  const i = MATCH_STEPS.findIndex((step) => Math.abs(step - min) < 1e-9)
  if (i === -1) throw new RangeError(`min match must be one of MATCH_STEPS (0–0.9 in 0.05 steps), got ${min}`)
  return i * 5
}

/** The whole percent the UI shows for a score, read from formatScorePct so the filter can't drift from the label. */
function displayedPct(score: number): number {
  return Number.parseInt(formatScorePct(score), 10)
}

/** `0` -> `"All"`, `0.7` -> `"≥ 70% match"`. */
export function matchLabel(min: number): string {
  const pct = stepPct(min)
  return pct === 0 ? 'All' : `≥ ${formatScorePct(pct / 100)} match`
}

/**
 * Keeps the overlaps whose displayed % match is at least `min` (inclusive) and the projects in
 * at least one kept overlap, in input order. At `min` 0 returns the input arrays themselves.
 */
export function filterByMinMatch(
  projects: Project[],
  overlaps: Overlap[],
  min: number,
): { projects: Project[]; overlaps: Overlap[] } {
  const threshold = stepPct(min)
  if (threshold === 0) return { projects, overlaps }
  const kept = overlaps.filter((o) => displayedPct(o.score) >= threshold)
  const keptIds = new Set(kept.flatMap((o) => [o.project_a.project_id, o.project_b.project_id]))
  return { projects: projects.filter((p) => keptIds.has(p.project_id)), overlaps: kept }
}
