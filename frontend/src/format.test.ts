import { describe, expect, it } from 'vitest'
import { formatDays, formatMiles, formatPairs, formatUsd, formatUsdCompact } from './format'

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
})
