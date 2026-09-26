import { describe, expect, it } from 'vitest'
import { formatDays, formatMiles, formatPairs, formatScorePct, formatUsd, formatUsdCompact } from './format'

describe('format', () => {
  it('keeps the existing exact formats', () => {
    expect(formatMiles(5.65)).toBe('5.7 mi')
    expect(formatDays(1)).toBe('1 day')
    expect(formatDays(152)).toBe('152 days')
    expect(formatUsd(709900)).toBe('$709,900')
  })

  it('formats headline money compactly with one decimal at most', () => {
    expect(formatUsdCompact(0)).toBe('$0')
    expect(formatUsdCompact(300000)).toBe('$300K')
    expect(formatUsdCompact(709900)).toBe('$709.9K')
    expect(formatUsdCompact(1500000)).toBe('$1.5M')
    expect(formatUsdCompact(4249999)).toBe('$4.2M')
  })

  it('pluralizes pair counts', () => {
    expect(formatPairs(0)).toBe('0 pairs')
    expect(formatPairs(1)).toBe('1 pair')
    expect(formatPairs(6)).toBe('6 pairs')
  })

  it('formats a 0-1 score as a whole-number percentage', () => {
    expect(formatScorePct(0.8311)).toBe('83%')
    expect(formatScorePct(0.7055)).toBe('71%')
    expect(formatScorePct(0)).toBe('0%')
    expect(formatScorePct(1)).toBe('100%')
  })

  it('throws a RangeError for scores outside 0-1 or non-finite', () => {
    for (const bad of [-0.01, 1.01, 83, NaN, Infinity, -Infinity]) {
      expect(() => formatScorePct(bad)).toThrow(RangeError)
    }
  })
})
