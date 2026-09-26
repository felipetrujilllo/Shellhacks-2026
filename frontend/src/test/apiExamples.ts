// Reads the tagged JSON examples straight from docs/api.md — the same fixtures the backend
// tests validate — so the frontend types are checked against the contract, not a copy.
// Read with node:fs (not Vite's `?raw`): docs/ is outside the Vite root, which Vite's
// fs sandbox denies — and widening that sandbox would also expose it on the dev server.
/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect } from 'vitest'
import type { Overlap, Project } from '../types'

// Path-based on purpose: jsdom replaces the global URL, which node:fs rejects.
const apiDoc = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../../../docs/api.md'),
  'utf8',
)

export function apiExample(tag: string): unknown {
  const match = apiDoc.match(new RegExp(`<!-- example: ${tag} -->\\s*\`\`\`json\\r?\\n([\\s\\S]*?)\`\`\``))
  if (!match) throw new Error(`docs/api.md has no example tagged "${tag}"`)
  return JSON.parse(match[1])
}

const nullableNumber = (v: unknown) => v === null || typeof v === 'number'
const nullableString = (v: unknown) => v === null || typeof v === 'string'

const PROJECT_CHECKS: Record<keyof Project, (v: unknown) => boolean> = {
  project_id: (v) => typeof v === 'string',
  utility: (v) => typeof v === 'string',
  state: (v) => typeof v === 'string',
  project_name: (v) => typeof v === 'string',
  name_a: nullableString,
  lat_a: nullableNumber,
  lon_a: nullableNumber,
  name_b: nullableString,
  lat_b: nullableNumber,
  lon_b: nullableNumber,
  lat_center: (v) => typeof v === 'number',
  lon_center: (v) => typeof v === 'number',
  in_service_date: (v) => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v),
  est_cost_usd: (v) => v === null || Number.isInteger(v),
  location_confidence: (v) => v === 'confirmed' || v === 'low',
}

const OVERLAP_CHECKS: Record<Exclude<keyof Overlap, 'project_a' | 'project_b'>, (v: unknown) => boolean> = {
  overlap_id: (v) => typeof v === 'string',
  rank: (v) => Number.isInteger(v) && (v as number) >= 1,
  score: (v) => typeof v === 'number',
  distance_mi: (v) => typeof v === 'number',
  time_gap_days: (v) => Number.isInteger(v) && (v as number) >= 0,
  est_savings_usd: (v) => v === null || (Number.isInteger(v) && (v as number) >= 0),
  savings_basis: (v) => typeof v === 'string' && v.length > 0,
}

function expectShape(value: unknown, checks: Record<string, (v: unknown) => boolean>, extra: string[] = []) {
  const obj = value as Record<string, unknown>
  expect(Object.keys(obj).sort()).toEqual([...Object.keys(checks), ...extra].sort())
  for (const [key, check] of Object.entries(checks)) {
    expect(check(obj[key]), `field ${key} = ${JSON.stringify(obj[key])}`).toBe(true)
  }
}

/** Asserts `value` has exactly the Project fields with the contract's types. */
export function expectProject(value: unknown): asserts value is Project {
  expectShape(value, PROJECT_CHECKS)
}

/** Asserts `value` has exactly the Overlap fields with the contract's types. */
export function expectOverlap(value: unknown): asserts value is Overlap {
  expectShape(value, OVERLAP_CHECKS, ['project_a', 'project_b'])
  const o = value as Overlap
  expectProject(o.project_a)
  expectProject(o.project_b)
}
