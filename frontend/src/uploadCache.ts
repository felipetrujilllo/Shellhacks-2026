// This browser's uploaded projects, kept in localStorage so they survive a refresh. Nothing
// else keeps them: the server scores them on every POST /workspace and stores nothing, so
// nobody else ever sees them (docs/api.md). Clearing site data or switching device loses them.
import type { Project } from './types'

/** One versioned key: a change to the stored shape bumps it instead of misreading old data. */
export const UPLOADS_STORAGE_KEY = 'relay.uploads.v1'

export interface CachedUploads {
  /** The uploads as imported (client ids; the server serves them as SUB-<id>). */
  uploads: Project[]
  /** False when the browser refuses storage (private window, blocked site data). */
  available: boolean
  /** Set when something is stored but unreadable. */
  problem: string | null
}

export const UNREADABLE_UPLOADS = 'The uploads saved in this browser are unreadable, so they are not shown.'

// The server validates every field; this only guards what the app itself reads.
const isUpload = (value: unknown) =>
  typeof value === 'object' && value !== null && typeof (value as { project_id?: unknown }).project_id === 'string'

/** Never throws: blocked storage reads as no uploads, unreadable data is reported. */
export function loadUploads(): CachedUploads {
  let raw: string | null
  try {
    raw = localStorage.getItem(UPLOADS_STORAGE_KEY)
  } catch {
    return { uploads: [], available: false, problem: null }
  }
  if (raw === null) return { uploads: [], available: true, problem: null }
  try {
    const parsed: unknown = JSON.parse(raw)
    if (Array.isArray(parsed) && parsed.every(isUpload)) return { uploads: parsed as Project[], available: true, problem: null }
  } catch { /* unreadable: reported below */ }
  return { uploads: [], available: true, problem: UNREADABLE_UPLOADS }
}

/** Stores the whole list (an empty one removes the key). False when the browser would not store it. */
export function saveUploads(uploads: Project[]): boolean {
  try {
    if (uploads.length) localStorage.setItem(UPLOADS_STORAGE_KEY, JSON.stringify(uploads))
    else localStorage.removeItem(UPLOADS_STORAGE_KEY)
    return true
  } catch {
    return false
  }
}
