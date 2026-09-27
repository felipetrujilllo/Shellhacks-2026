import { describe, expect, it } from 'vitest'
import { formatScorePct } from './format'
import { DEFAULT_MIN_MATCH, MATCH_STEPS, filterByMinMatch, matchLabel } from './matchFilter'
import { apiExample, expectOverlap, expectProject } from './test/apiExamples'
import { makeOverlaps } from './test/overlapFixtures'

const ids = (items: readonly { overlap_id: string }[]) => items.map((o) => o.overlap_id)
const projectIds = (items: readonly { project_id: string }[]) => items.map((p) => p.project_id)

/**
 * Projects and overlaps from the docs/api.md examples, varied by spreading.
 * Overlaps in rank order, each with its own two projects:
 *   OVL_1 0.5018 (50%)  DESC_2 – GPC_1   (contract example)
 *   OVL_2 0.8311 (83%)  DESC_3 – GPC_2   (contract example)
 *   OVL_3 0.695  (70%)  SC_3 – GA_3      (displays exactly 70%, though below 0.70 raw)
 *   OVL_4 0.6949 (69%)  SC_4 – GA_4      (displays 1% below 70%)
 *   OVL_5 0.705  (71%)  SC_5 – GA_5
 * Projects also include LONE, which is in no overlap at all.
 */
function fixture() {
  const example = apiExample('overlaps')
  if (!Array.isArray(example) || example.length !== 2) throw new Error('expected the two-pair overlaps example')
  const [ovl1, ovl2]: unknown[] = example
  expectOverlap(ovl1)
  expectOverlap(ovl2)
  const extra = makeOverlaps(5).slice(2).map((o, i) => {
    const n = i + 3
    return {
      ...o,
      score: [0.695, 0.6949, 0.705][i],
      project_a: { ...o.project_a, project_id: `SC_${n}` },
      project_b: { ...o.project_b, project_id: `GA_${n}` },
    }
  })
  const overlaps = [ovl1, ovl2, ...extra]
  const lone = { ...ovl2.project_a, project_id: 'LONE', project_name: 'Nobody nearby' }
  // Interleaved (not overlap order) so the test proves the project order comes from the input.
  const projects = [
    extra[2].project_b, lone, ovl2.project_a, ovl1.project_a, extra[0].project_a, ovl1.project_b,
    extra[1].project_a, ovl2.project_b, extra[0].project_b, extra[1].project_b, extra[2].project_a,
  ]
  projects.forEach((p) => expectProject(p))
  return { projects, overlaps }
}

describe('MATCH_STEPS / DEFAULT_MIN_MATCH', () => {
  it('is exactly 0–0.90 every 5% (19 exact decimal stops)', () => {
    expect(MATCH_STEPS).toEqual([
      0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9,
    ])
    expect(MATCH_STEPS).toHaveLength(19)
    expect(MATCH_STEPS[0]).toBe(0)
    expect(MATCH_STEPS[18]).toBe(0.9)
    expect(MATCH_STEPS[14]).toBe(0.7) // exact, not 0.7000000000000001
    MATCH_STEPS.forEach((step, i) => expect(Math.round(step * 100)).toBe(i * 5))
  })

  it('defaults to 0 ("All"), which is a stop', () => {
    expect(DEFAULT_MIN_MATCH).toBe(0)
    expect(MATCH_STEPS).toContain(DEFAULT_MIN_MATCH)
  })
})

describe('matchLabel', () => {
  it('reads "All" at 0 and "≥ N% match" otherwise', () => {
    expect(matchLabel(0)).toBe('All')
    expect(matchLabel(0.05)).toBe('≥ 5% match')
    expect(matchLabel(0.7)).toBe('≥ 70% match')
    expect(matchLabel(0.9)).toBe('≥ 90% match')
  })

  it('uses the same percentage text as formatScorePct for every stop', () => {
    for (const step of MATCH_STEPS.slice(1)) expect(matchLabel(step)).toBe(`≥ ${formatScorePct(step)} match`)
  })
})

describe('filterByMinMatch', () => {
  it('at 0 returns the input arrays themselves, untouched', () => {
    const { projects, overlaps } = fixture()
    const result = filterByMinMatch(projects, overlaps, DEFAULT_MIN_MATCH)
    expect(result.projects).toBe(projects)
    expect(result.overlaps).toBe(overlaps)
    expect(projectIds(result.projects)).toContain('LONE')
  })

  it('is inclusive on the displayed percentage: a pair shown as 70% is kept at 70%, one shown as 69% is dropped', () => {
    const { projects, overlaps } = fixture()
    // The boundary scores display exactly as the filter judges them.
    expect(formatScorePct(0.695)).toBe('70%')
    expect(formatScorePct(0.6949)).toBe('69%')
    expect(formatScorePct(0.705)).toBe('71%')
    expect(ids(filterByMinMatch(projects, overlaps, 0.7).overlaps)).toEqual(['OVL_2', 'OVL_3', 'OVL_5'])
    // And at 65% the 69% pair is back.
    expect(ids(filterByMinMatch(projects, overlaps, 0.65).overlaps)).toEqual(['OVL_2', 'OVL_3', 'OVL_4', 'OVL_5'])
  })

  it('keeps every kept pair\'s label consistent with the threshold label', () => {
    const { projects, overlaps } = fixture()
    for (const step of MATCH_STEPS.slice(1)) {
      const threshold = Number.parseInt(formatScorePct(step), 10)
      const { overlaps: kept } = filterByMinMatch(projects, overlaps, step)
      for (const o of overlaps) {
        expect(kept.includes(o), `${o.overlap_id} (${formatScorePct(o.score)}) at ${matchLabel(step)}`)
          .toBe(Number.parseInt(formatScorePct(o.score), 10) >= threshold)
      }
    }
  })

  it('keeps only projects in a kept overlap, hides a project with no overlap, in input order', () => {
    const { projects, overlaps } = fixture()
    const result = filterByMinMatch(projects, overlaps, 0.7)
    // Input order: GA_5, LONE, DESC_3, DESC_2, SC_3, GPC_1, SC_4, GPC_2, GA_3, GA_4, SC_5.
    expect(projectIds(result.projects)).toEqual(['GA_5', 'DESC_3', 'SC_3', 'GPC_2', 'GA_3', 'SC_5'])
    // The kept projects are the input objects themselves, not copies.
    result.projects.forEach((p) => expect(projects).toContain(p))
    result.overlaps.forEach((o) => expect(overlaps).toContain(o))
  })

  it('at a low threshold still hides the project with no overlap', () => {
    const { projects, overlaps } = fixture()
    const result = filterByMinMatch(projects, overlaps, 0.05)
    expect(ids(result.overlaps)).toEqual(['OVL_1', 'OVL_2', 'OVL_3', 'OVL_4', 'OVL_5'])
    expect(projectIds(result.projects)).toEqual(projectIds(projects).filter((id) => id !== 'LONE'))
  })

  it('keeps nothing when no pair reaches the threshold', () => {
    const { projects, overlaps } = fixture()
    expect(filterByMinMatch(projects, overlaps, 0.9)).toEqual({ projects: [], overlaps: [] })
  })

  it('never mutates its inputs', () => {
    const { projects, overlaps } = fixture()
    const before = structuredClone({ projects, overlaps })
    const projectRefs = [...projects]
    const overlapRefs = [...overlaps]
    for (const step of MATCH_STEPS) filterByMinMatch(projects, overlaps, step)
    expect({ projects, overlaps }).toEqual(before)
    projects.forEach((p, i) => expect(p).toBe(projectRefs[i]))
    overlaps.forEach((o, i) => expect(o).toBe(overlapRefs[i]))
  })

  it('works on frozen inputs', () => {
    const { projects, overlaps } = fixture()
    Object.freeze(projects)
    Object.freeze(overlaps)
    expect(() => filterByMinMatch(projects, overlaps, 0.5)).not.toThrow()
  })
})

describe('invalid min fails loud', () => {
  it.each([0.07, -0.05, 0.95, 1, NaN, Infinity, 70])('filterByMinMatch and matchLabel throw RangeError for %s', (min) => {
    const { projects, overlaps } = fixture()
    expect(() => filterByMinMatch(projects, overlaps, min)).toThrow(RangeError)
    expect(() => matchLabel(min)).toThrow(RangeError)
  })
})
