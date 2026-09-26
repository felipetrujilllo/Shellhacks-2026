// Overlap fixtures derived from the docs/api.md contract example, so contract changes
// (new fields) flow into the tests instead of breaking hand-written literals.
import { apiExample, expectOverlap } from './apiExamples'

/** `count` distinct overlaps (OVL_1..N, rank 1..N, distinct names/distances/gaps), in rank order. */
export function makeOverlaps(count: number) {
  const base = apiExample('overlap')
  expectOverlap(base)
  return Array.from({ length: count }, (_, i) => {
    const n = i + 1
    return {
      ...base,
      overlap_id: `OVL_${n}`,
      rank: n,
      distance_mi: n + 0.25,
      time_gap_days: n * 10,
      project_a: { ...base.project_a, project_name: `SC line ${n}` },
      project_b: { ...base.project_b, project_name: `GA line ${n}` },
    }
  })
}
