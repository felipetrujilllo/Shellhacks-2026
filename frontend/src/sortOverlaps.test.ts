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
  it('score: highest first, ties by rank asc', () => {
    // 0.9 (2), 0.7 (5), 0.5 (1, 3 tie -> rank order), 0.2 (4)
    expect(ids(sortOverlaps(fixture(), 'score'))).toEqual(['OVL_2', 'OVL_5', 'OVL_1', 'OVL_3', 'OVL_4'])
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

  it('offers exactly the four keys, score first as the default', () => {
    expect(SORT_OPTIONS.map(o => o.key)).toEqual(['score', 'distance', 'time_gap', 'savings'])
    expect(DEFAULT_SORT_KEY).toBe('score')
  })

  it('fails loud on an unknown key', () => {
    expect(() => sortOverlaps(fixture(), 'bogus' as never)).toThrow('unknown sort key: bogus')
  })
})
