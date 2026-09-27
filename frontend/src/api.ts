// Typed fetchers for the GridWatch API (contract: docs/api.md).
import type { Health, Overlap, Project, Workspace } from './types'

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

/**
 * POST /workspace: the published plans plus `uploads` (this browser's own, possibly none),
 * scored and ranked together. The server stores nothing. Rejects with the server's reason,
 * e.g. a 409 when an upload repeats a published project.
 */
export async function fetchWorkspace(uploads: Project[]): Promise<Workspace> {
  const url = apiUrl('/workspace')
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ projects: uploads }),
  })
  if (!res.ok) {
    // A 409 carries a readable `detail` string; a 422's is a list, so fall back to the status.
    const body: unknown = await res.json().catch(() => null)
    const detail = (body as { detail?: unknown } | null)?.detail
    throw new Error(typeof detail === 'string' ? detail : `POST ${url} failed with status ${res.status} ${res.statusText}`.trimEnd())
  }
  return (await res.json()) as Workspace
}
