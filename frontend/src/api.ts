// Typed fetchers for the GridWatch API (contract: docs/api.md).
import type { Health, Overlap, Project } from './types'

/** Joins VITE_API_URL with an API path. Throws if VITE_API_URL is not configured. */
export function apiUrl(path: string): string {
  const base = import.meta.env.VITE_API_URL?.trim()
  if (!base) {
    throw new Error('VITE_API_URL is not set — add it to frontend/.env (see .env.example)')
  }
  return `${base.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`
}

async function getJson<T>(path: string): Promise<T> {
  const url = apiUrl(path)
  const res = await fetch(url)
  if (!res.ok) {
    throw new Error(`GET ${url} failed with status ${res.status} ${res.statusText}`.trimEnd())
  }
  return (await res.json()) as T
}

export const fetchHealth = (): Promise<Health> => getJson('/health')

export const fetchProjects = (): Promise<Project[]> => getJson('/projects')

/** Ranked: rank 1 first. */
export const fetchOverlaps = (): Promise<Overlap[]> => getJson('/overlaps')

export const fetchOverlap = (overlapId: string): Promise<Overlap> =>
  getJson(`/overlaps/${encodeURIComponent(overlapId)}`)
