import { describe, expect, it } from 'vitest'
import { summarizeSavings } from './savings'

const pair = (est_savings_usd: number | null) => ({ est_savings_usd })

describe('summarizeSavings', () => {
  it('sums known est_savings_usd values and counts every pair', () => {
    expect(summarizeSavings([pair(709900), pair(1200000), pair(300000)])).toEqual({
      pairCount: 3, estimatedCount: 3, notEstimatedCount: 0, totalUsd: 2209900,
    })
  })

  it('excludes null savings from the total and counts those pairs as not estimated', () => {
    expect(summarizeSavings([pair(1200000), pair(null), pair(300000), pair(null), pair(null)])).toEqual({
      pairCount: 5, estimatedCount: 2, notEstimatedCount: 3, totalUsd: 1500000,
    })
  })

  it('treats a known $0 estimate as estimated, not as missing', () => {
    expect(summarizeSavings([pair(0), pair(null)])).toEqual({
      pairCount: 2, estimatedCount: 1, notEstimatedCount: 1, totalUsd: 0,
    })
  })

  it('returns a zero summary for no pairs', () => {
    expect(summarizeSavings([])).toEqual({ pairCount: 0, estimatedCount: 0, notEstimatedCount: 0, totalUsd: 0 })
  })
})
