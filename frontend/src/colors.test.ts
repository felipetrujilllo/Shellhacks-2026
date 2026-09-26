import { describe, expect, it } from 'vitest'
import { DESC, GPC, OTHER_UTILITY_COLOR, UTILITY_COLORS, utilityColor } from './colors'

// Every source file under src/, as text (Vite glob import), to guard the single source of truth.
const sources = import.meta.glob<string>(['./**/*.{ts,tsx}', '!./**/*.test.{ts,tsx}'], {
  query: '?raw',
  import: 'default',
  eager: true,
})

describe('utilityColor', () => {
  it('returns each named utility its color and any other utility the fallback', () => {
    expect(utilityColor(DESC)).toBe('#60a5fa')
    expect(utilityColor(GPC)).toBe('#f87171')
    expect(utilityColor('Santee Cooper')).toBe(OTHER_UTILITY_COLOR)
    expect(utilityColor('constructor')).toBe(OTHER_UTILITY_COLOR) // not an inherited Object key
  })

  it('is defined once: no other source file defines utilityColor or hard-codes a utility color', () => {
    const others = Object.entries(sources).filter(([path]) => path !== './colors.ts')
    expect(others.length).toBeGreaterThan(5) // the glob really found the source tree
    const hexes = [...Object.values(UTILITY_COLORS), OTHER_UTILITY_COLOR]
    for (const [path, text] of others) {
      expect(text, path).not.toMatch(/(const|let|function)\s+utilityColor\b/)
      for (const hex of hexes) expect(text.toLowerCase(), `${path} hard-codes ${hex}`).not.toContain(hex)
    }
  })
})
