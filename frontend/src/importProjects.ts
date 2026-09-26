import type { Project } from './types'

// Ids the server gives uploaded projects and their pairs (backend/app/submissions.py).
export const SUBMITTED_PROJECT_PREFIX = 'SUB-'
export const SUBMITTED_OVERLAP_PREFIX = 'SUB:'

export interface ImportRow { row: number; name: string; issues: string[]; project: Project | null }
export interface ImportBatch { id: string; filename: string; rows: ImportRow[] }

export const CSV_TEMPLATE = 'project_id,utility,project_name,lat_center,lon_center,in_service_date,est_cost_usd,name_a,lat_a,lon_a,name_b,lat_b,lon_b\nproposal-01,Your utility,Savannah corridor upgrade,32.34,-81.14,2027-06-01,2500000,West substation,32.35,-81.18,East substation,32.33,-81.10\n'

/** RFC-style quoted fields, including embedded commas, escaped quotes and newlines. */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = [], field = '', quoted = false, closed = false
  text = text.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++ }
      else if (c === '"') { quoted = false; closed = true }
      else field += c
    } else if (c === ',' || c === '\n') {
      row.push(field.trim()); field = ''; closed = false
      if (c === '\n') { if (row.some(Boolean)) rows.push(row); row = [] }
    } else if (c === '"' && field === '' && !closed) quoted = true
    else {
      if (closed || c === '"') throw new Error('Invalid CSV quoting. Export the spreadsheet as CSV and try again.')
      field += c
    }
  }
  if (quoted) throw new Error('A quoted field is unfinished. Check the CSV and try again.')
  row.push(field.trim())
  if (row.some(Boolean)) rows.push(row)
  return rows
}

export function reviewCsv(text: string, batchId: string, existing: Project[]): ImportRow[] {
  const [rawHeaders, ...rows] = parseCsv(text)
  if (!rawHeaders || !rows.length) throw new Error('This file has no project rows.')
  if (rows.length > 1000) throw new Error('Use a file with 1,000 projects or fewer.')
  const headers = rawHeaders.map(h => h.toLowerCase())
  if (new Set(headers).size !== headers.length) throw new Error('Column names must be unique.')
  const required = ['utility', 'project_name', 'lat_center', 'lon_center', 'in_service_date']
  const missing = required.filter(h => !headers.includes(h))
  if (missing.length) throw new Error(`Missing columns: ${missing.join(', ')}. Download the template for the expected format.`)
  const keys = new Set(existing.map(p => `${p.utility.toLowerCase()}|${p.project_name.toLowerCase()}`))
  return rows.map((values, i) => {
    const raw = Object.fromEntries(headers.map((h, j) => [h, values[j] ?? '']))
    const issues: string[] = []
    if (values.length !== headers.length) issues.push('Column count does not match the header')
    if (!raw.utility) issues.push('Utility is missing')
    if (!raw.project_name) issues.push('Project name is missing')
    function coord(key: string, limit: number, required = false): number | null {
      if (!raw[key]) { if (required) issues.push(`${key} is missing`); return null }
      const n = Number(raw[key])
      if (!Number.isFinite(n) || Math.abs(n) > limit) { issues.push(`${key} is invalid`); return null }
      return n
    }
    const lat = coord('lat_center', 90, true), lon = coord('lon_center', 180, true)
    const latA = coord('lat_a', 90), lonA = coord('lon_a', 180)
    const latB = coord('lat_b', 90), lonB = coord('lon_b', 180)
    if ((latA === null) !== (lonA === null)) issues.push('Endpoint A needs both latitude and longitude')
    if ((latB === null) !== (lonB === null)) issues.push('Endpoint B needs both latitude and longitude')
    const date = raw.in_service_date
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(Date.parse(date)) ||
      new Date(date).toISOString().slice(0, 10) !== date) issues.push('Use a valid in-service date (YYYY-MM-DD)')
    const cost = raw.est_cost_usd ? Number(raw.est_cost_usd.replace(/[$,]/g, '')) : null
    if (cost !== null && (!Number.isFinite(cost) || cost < 0)) issues.push('Estimated cost must be a positive number or blank')
    const key = `${raw.utility.toLowerCase()}|${raw.project_name.toLowerCase()}`
    if (keys.has(key)) issues.push('This utility and project name already exist')
    if (!issues.length) keys.add(key)
    return { row: i + 2, name: raw.project_name || `Row ${i + 2}`, issues,
      project: issues.length ? null : {
        // project_id is only the client's reference: POST /submissions assigns the real one.
        // The API requires a state and the template has no state column.
        project_id: `${batchId}:${i + 1}`, utility: raw.utility, state: raw.state || 'Unknown',
        project_name: raw.project_name, lat_center: lat!, lon_center: lon!,
        name_a: raw.name_a || null, lat_a: latA, lon_a: lonA,
        name_b: raw.name_b || null, lat_b: latB, lon_b: lonB,
        in_service_date: date, est_cost_usd: cost,
        // Uploaded coordinates are supplied by the user, not independently verified.
        location_confidence: 'low',
      } }
  })
}
