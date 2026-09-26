/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { CSV_TEMPLATE, parseCsv, reviewCsv } from './importProjects'

const header = 'utility,project_name,lat_center,lon_center,in_service_date'

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

// Pairs for uploaded projects are computed by the server now (backend/app/submissions.py,
// tested in backend/tests/test_submissions.py), with the same engine as the published pairs.
describe('sponsor seed file', () => {
  // Read with node:fs like test/apiExamples.ts, since data/ is outside the Vite root.
  const seedFile = (name: string) =>
    readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../data/seed', name), 'utf8')

  it('passes review with every row ready to upload', () => {
    const rows = reviewCsv(seedFile('projects_seed.csv'), 'seed', [])
    expect(rows).toHaveLength(10)
    expect(rows.every(r => r.issues.length === 0 && r.project)).toBe(true)
  })
})
