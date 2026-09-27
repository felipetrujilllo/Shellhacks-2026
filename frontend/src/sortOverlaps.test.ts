import { describe, expect, it } from 'vitest'
import { DEFAULT_SORT_KEY, SORT_OPTIONS, sortOverlaps } from './sortOverlaps'
import { makeOverlaps } from './test/overlapFixtures'

// Five pairs whose score / distance / gap / savings orders all differ from rank order.
// OVL_n has rank n. Fields per rank:          1        2        3       4        5
const SCORES = [0.5, 0.9, 0.5, 0.2, 0.7]
const DISTANCES = [8.2, 3.1, 12.0, 3.1, 0.4]
const GAPS = [300, 45, 10, 45, 900]
const SAVINGS = [null, 250000, 900000, null, 250000]

function fixture() {
  return makeOverlaps(5).map((o, i) => ({
    ...o, score: SCORES[i], distance_mi: DISTANCES[i], time_gap_days: GAPS[i], est_savings_usd: SAVINGS[i],
  }))
}

const ids = (overlaps: readonly { overlap_id: string }[]) => overlaps.map(o => o.overlap_id)

describe('sortOverlaps', () => {
  it('rank: keeps the server\'s tier-first order even where scores disagree', () => {
    // Scores 0.5, 0.9, 0.5, 0.2, 0.7 would put OVL_2 first; rank order does not re-sort by score.
    // Reversed input, so the order comes from rank, not from the input order.
    expect(ids(sortOverlaps(fixture().reverse(), 'rank'))).toEqual(['OVL_1', 'OVL_2', 'OVL_3', 'OVL_4', 'OVL_5'])
  })

  it('rank: a crossing pair with a lower score stays ahead of a higher-scoring crews pair', () => {
    const [crossing, crews] = makeOverlaps(2)
    // Input arrives out of order, so the result comes from sorting by rank, not from the input order.
    const input = [
      { ...crews, tier: 'crews' as const, score: 0.95 },
      { ...crossing, tier: 'crossing' as const, score: 0.2 },
    ]
    expect(sortOverlaps(input, DEFAULT_SORT_KEY).map(o => [o.overlap_id, o.tier])).toEqual([['OVL_1', 'crossing'], ['OVL_2', 'crews']])
  })

  it('distance: closest first, ties by rank asc', () => {
    // 0.4 (5), 3.1 (2, 4 tie), 8.2 (1), 12.0 (3)
    expect(ids(sortOverlaps(fixture(), 'distance'))).toEqual(['OVL_5', 'OVL_2', 'OVL_4', 'OVL_1', 'OVL_3'])
  })

  it('time gap: shortest first, ties by rank asc', () => {
    // 10 (3), 45 (2, 4 tie), 300 (1), 900 (5)
    expect(ids(sortOverlaps(fixture(), 'time_gap'))).toEqual(['OVL_3', 'OVL_2', 'OVL_4', 'OVL_1', 'OVL_5'])
  })

  it('savings: highest first, ties by rank asc, null savings always last (in rank order)', () => {
    // 900k (3), 250k (2, 5 tie), then nulls (1, 4)
    expect(ids(sortOverlaps(fixture(), 'savings'))).toEqual(['OVL_3', 'OVL_2', 'OVL_5', 'OVL_1', 'OVL_4'])
  })

  it('savings: nulls stay last even when every estimate is $0 and input has nulls first', () => {
    const overlaps = makeOverlaps(3).map((o, i) => ({ ...o, est_savings_usd: [null, 0, null][i] }))
    expect(ids(sortOverlaps(overlaps, 'savings'))).toEqual(['OVL_2', 'OVL_1', 'OVL_3'])
  })

  it('does not mutate its input for any key', () => {
    const input = Object.freeze(fixture())
    const before = ids(input)
    for (const { key } of SORT_OPTIONS) {
      const sorted = sortOverlaps(input, key)
      expect(sorted).not.toBe(input)
      expect(sorted).toHaveLength(input.length)
    }
    expect(ids(input)).toEqual(before)
  })

  it('offers exactly the four keys, rank first as the default, labelled tier then score', () => {
    expect(SORT_OPTIONS.map(o => o.key)).toEqual(['rank', 'distance', 'time_gap', 'savings'])
    expect(DEFAULT_SORT_KEY).toBe('rank')
    expect(SORT_OPTIONS[0]).toEqual({ key: 'rank', label: 'Rank (tier, then score)' })
  })

  it('fails loud on an unknown key', () => {
    expect(() => sortOverlaps(fixture(), 'bogus' as never)).toThrow('unknown sort key: bogus')
  })
})
