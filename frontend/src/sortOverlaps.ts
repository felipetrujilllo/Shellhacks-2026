// Orders the opportunity list. Pure: returns a new array and never touches the input, so the
// API's rank order stays intact for everything else (map, savings headline, #rank badges).
import type { Overlap } from './types'

export type SortKey = 'rank' | 'distance' | 'time_gap' | 'savings'

/** The sort choices in menu order; the first is the default. */
export const SORT_OPTIONS: readonly { key: SortKey; label: string }[] = [
  { key: 'rank', label: 'Rank (tier, then score)' },
  { key: 'distance', label: 'Distance (closest first)' },
  { key: 'time_gap', label: 'Time gap (shortest first)' },
  { key: 'savings', label: 'Est. savings (highest first)' },
]

/** The server's order (Sperry tier first, then score): re-sorting by score would undo the tiers. */
export const DEFAULT_SORT_KEY: SortKey = 'rank'

/** Negative when `a` goes first. Null savings always sort after any estimate. */
const COMPARE: Record<SortKey, (a: Overlap, b: Overlap) => number> = {
  rank: (a, b) => a.rank - b.rank,
  distance: (a, b) => a.distance_mi - b.distance_mi,
  time_gap: (a, b) => a.time_gap_days - b.time_gap_days,
  savings: (a, b) => {
    if (a.est_savings_usd === null || b.est_savings_usd === null) {
      return (a.est_savings_usd === null ? 1 : 0) - (b.est_savings_usd === null ? 1 : 0)
    }
    return b.est_savings_usd - a.est_savings_usd
  },
}

/** A sorted copy of `overlaps` by `key`; ties keep the API's rank order (rank asc). */
export function sortOverlaps(overlaps: readonly Overlap[], key: SortKey): Overlap[] {
  const compare = COMPARE[key]
  if (!compare) throw new Error(`unknown sort key: ${String(key)}`)
  return [...overlaps].sort((a, b) => compare(a, b) || a.rank - b.rank)
}
