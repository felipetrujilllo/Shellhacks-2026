/// <reference types="node" />
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { TIER_LABELS, tierLabel } from './tiers'
import type { CoordinationTier } from './types'

// The exact wording the ticket (#50) fixes, in the server's tier order (best first).
const EXPECTED: [CoordinationTier, string][] = [
  ['crossing', 'Crossing — must coordinate'],
  ['shared_land', 'Share land & permits'],
  ['site_logistics', 'Share site logistics'],
  ['crews', 'Share crews & equipment'],
]

// Path-based on purpose: jsdom replaces the global URL, which node:fs rejects.
const SRC = dirname(fileURLToPath(import.meta.url))

/** Every app source file under src/ (tests and test helpers excluded: they may spell the labels out to assert them). */
function appSources(dir = SRC): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) return entry.name === 'test' ? [] : appSources(path)
    return /\.(ts|tsx)$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name) ? [path] : []
  })
}

describe('tiers', () => {
  it('labels exactly the four tiers, with the exact strings (a real em dash in the crossing label)', () => {
    expect(Object.entries(TIER_LABELS)).toEqual(EXPECTED)
    expect(TIER_LABELS.crossing).toContain('—')
  })

  it('tierLabel returns each tier\'s label', () => {
    for (const [tier, label] of EXPECTED) expect(tierLabel(tier)).toBe(label)
  })

  it('tierLabel fails loud on a tier the frontend does not know', () => {
    expect(() => tierLabel('bogus' as never)).toThrow('unknown coordination tier: bogus')
    expect(() => tierLabel('toString' as never)).toThrow('unknown coordination tier: toString')
  })

  it('keeps the label strings in tiers.ts only: no other app source file spells one out', () => {
    const files = appSources()
    expect(files.map((f) => relative(SRC, f).replace(/\\/g, '/'))).toEqual(expect.arrayContaining(['tiers.ts', 'App.tsx', 'components/OverlapDetail.tsx']))
    const offenders = files.flatMap((file) => {
      const source = readFileSync(file, 'utf8')
      return EXPECTED.filter(([, label]) => source.includes(label)).map(([, label]) => `${relative(SRC, file)}: ${label}`)
    })
    expect(offenders.filter((o) => !o.startsWith('tiers.ts:'))).toEqual([])
    expect(offenders).toHaveLength(EXPECTED.length) // and tiers.ts has all four
  })
})
