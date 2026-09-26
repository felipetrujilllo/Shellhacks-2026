/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { compareImports, CSV_TEMPLATE, parseCsv, reviewCsv } from './importProjects'
import { makeOverlaps } from './test/overlapFixtures'

const header = 'utility,project_name,lat_center,lon_center,in_service_date'
const source = makeOverlaps(1)[0].project_a

describe('CSV project review', () => {
  it('parses BOM, CRLF, embedded commas, escaped quotes and multiline fields', () => {
    expect(parseCsv('\uFEFFa,b\r\n"name, \\"test\\"",x'.replaceAll('\\"', '""'))).toEqual([['a', 'b'], ['name, "test"', 'x']])
    expect(parseCsv('a,b\n"two\nlines",ok')).toEqual([['a', 'b'], ['two\nlines', 'ok']])
  })
  it('maps the template with endpoints and marks supplied locations unverified', () => {
    const [row] = reviewCsv(CSV_TEMPLATE, 'batch', [])
    expect(row.issues).toEqual([])
    expect(row.project).toMatchObject({ project_id: 'batch:1', lat_center: 32.34, lon_a: -81.18, est_cost_usd: 2500000, location_confidence: 'low' })
  })
  it('retains bad rows for review without mapping them', () => {
    const rows = reviewCsv(`${header}\nNew Utility,Missing location,,-81,2027-02-30\nNew Utility,Valid,32,-81,2027-06-01`, 'batch', [])
    expect(rows[0].project).toBeNull()
    expect(rows[0].issues).toEqual(['lat_center is missing', 'Use a valid in-service date (YYYY-MM-DD)'])
    expect(rows[1].project).not.toBeNull()
  })
  it.each(['NaN', 'Infinity', '91'])('rejects invalid latitude %s', lat => {
    expect(reviewCsv(`${header}\nU,P,${lat},-81,2027-01-01`, 'x', [])[0].project).toBeNull()
  })
  it('rejects duplicate utility/project pairs, ignoring case, within and across uploads', () => {
    const csv = `${header}\nU,Project,32,-81,2027-01-01\nu,project,32,-81,2027-01-01`
    const rows = reviewCsv(csv, 'x', [])
    expect(rows[1].issues).toContain('This utility and project name already exist')
    expect(reviewCsv(csv, 'y', [rows[0].project!])[0].project).toBeNull()
  })
  it('requires complete endpoint pairs and a nonnegative cost', () => {
    const [row] = reviewCsv(`${header},lat_a,est_cost_usd\nU,P,32,-81,2027-01-01,32,-1`, 'x', [])
    expect(row.issues).toEqual(['Endpoint A needs both latitude and longitude', 'Estimated cost must be a positive number or blank'])
  })
  it('preserves valid zero coordinates', () => {
    expect(reviewCsv(`${header}\nU,P,0,0,2027-01-01`, 'x', [])[0].project?.lat_center).toBe(0)
  })
  it('rejects malformed files and missing columns', () => {
    expect(() => parseCsv('a\n"unfinished')).toThrow('unfinished')
    expect(() => reviewCsv('name\nTest', 'x', [])).toThrow('Missing columns')
    expect(() => reviewCsv(`${header}\n`, 'x', [])).toThrow('no project rows')
    expect(() => reviewCsv(`${header},utility\nU,P,32,-81,2027-01-01,U`, 'x', [])).toThrow('unique')
  })
})

describe('import comparisons', () => {
  it('finds other utilities within 25 miles and ranks timing', () => {
    const near = { ...source, project_id: 'new', utility: 'New Utility' }
    const far = { ...source, project_id: 'far', lat_center: 45 }
    const matches = compareImports([near], [source, near, far], [])
    expect(matches).toHaveLength(1)
    expect(matches[0]).toMatchObject({ rank: 1, distance_mi: 0, time_gap_days: 0, score: 1, est_savings_usd: null })
  })
  it('does not compare projects from the same utility or add seed-only pairs', () => {
    const same = { ...source, project_id: 'new', utility: source.utility.toUpperCase() }
    expect(compareImports([same], [source, same], [])).toEqual([])
    expect(compareImports([], [source, { ...source, utility: 'Other' }], [])).toEqual([])
  })
  it('preserves existing pairs and creates only one pair between two imported projects', () => {
    const a = { ...source, project_id: 'a', utility: 'A' }
    const b = { ...source, project_id: 'b', utility: 'B' }
    const existing = makeOverlaps(1)
    const result = compareImports([a, b], [a, b], existing)
    expect(result).toHaveLength(2)
    expect(result.find(o => o.overlap_id === existing[0].overlap_id)).toBeDefined()
  })

  // The backend's golden file: the sponsor's 10 starter projects must give exactly its 6 pairs.
  // Read with node:fs like test/apiExamples.ts, since data/ is outside the Vite root.
  const seedFile = (name: string) =>
    readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../data/seed', name), 'utf8')

  it("reproduces the backend's 6 sponsor overlaps with the same distances and gaps", () => {
    const seedCsv = seedFile('projects_seed.csv')
    const seedIds = parseCsv(seedCsv).slice(1).map(row => row[0])
    const rows = reviewCsv(seedCsv, 'seed', [])
    expect(rows.every(r => r.issues.length === 0)).toBe(true)
    const projects = rows.map(r => r.project!)
    const idOf = (projectId: string) => seedIds[Number(projectId.split(':')[1]) - 1]
    const pairs = compareImports(projects, projects, [])
      .map(o => [...[idOf(o.project_a.project_id), idOf(o.project_b.project_id)].sort(), o.distance_mi, o.time_gap_days].join(','))
    const expected = parseCsv(seedFile('expected_overlaps.csv')).slice(1)
      .map(([, a, b, distance, gap]) => [...[a, b].sort(), Number(distance), Number(gap)].join(','))
    expect(pairs.sort()).toEqual(expected.sort())
  })

  it('scores a pair the same as pipeline.overlap.opportunity_score', () => {
    // DESC_3 / GPC_2 from the seed data: 5.65 mi and 152 days apart; the backend scores it 0.8311.
    const desc = { ...source, project_id: 'd', utility: 'DESC', lat_center: 32.346439, lon_center: -81.0785475, in_service_date: '2025-12-31' }
    const gpc = { ...source, project_id: 'g', utility: 'GPC', lat_center: 32.352116, lon_center: -81.175112, in_service_date: '2026-06-01' }
    const [pair] = compareImports([desc], [desc, gpc], [])
    expect(pair).toMatchObject({ distance_mi: 5.65, time_gap_days: 152 })
    expect(pair.score).toBeCloseTo(0.8311, 4)
  })

  it('flags a pair just under 25 miles and skips one just over', () => {
    // Latitude offsets along one meridian that are 24.99 and 25.01 miles long on a 3958.8 mi earth.
    const base = { ...source, project_id: 'base', utility: 'A', lat_center: 32, lon_center: -81 }
    const under = { ...base, project_id: 'under', utility: 'B', lat_center: 32 + 0.3616807 }
    const over = { ...base, project_id: 'over', utility: 'B', lat_center: 32 + 0.3619702 }
    expect(compareImports([under], [base, under], [])).toMatchObject([{ distance_mi: 24.99 }])
    expect(compareImports([over], [base, over], [])).toEqual([])
  })
})
