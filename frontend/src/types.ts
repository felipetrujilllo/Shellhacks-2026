// Mirrors the API contract in docs/api.md (backend models: backend/app/schemas.py).
// Field names are identical to the backend's — keep them in sync.

export type LocationConfidence = 'confirmed' | 'low'

/** Sperry's coordination tier, best first (backend: TIER_ORDER in pipeline/overlap.py). */
export type CoordinationTier = 'crossing' | 'shared_land' | 'site_logistics' | 'crews'

export interface Project {
  project_id: string
  utility: string
  state: string
  project_name: string
  name_a: string | null
  lat_a: number | null
  lon_a: number | null
  name_b: string | null
  lat_b: number | null
  lon_b: number | null
  /** Always present — what overlap detection compares. */
  lat_center: number
  lon_center: number
  /** ISO `YYYY-MM-DD`. */
  in_service_date: string
  /** Whole dollars; null where redacted. */
  est_cost_usd: number | null
  location_confidence: LocationConfidence
}

export interface Overlap {
  overlap_id: string
  /** 1 = best opportunity: tier first, then by descending score. */
  rank: number
  score: number
  distance_mi: number
  /** Miles between the projects' closest points (segment, or center without endpoints). */
  closest_mi: number
  tier: CoordinationTier
  time_gap_days: number
  project_a: Project
  project_b: Project
  /** Rough shared-mobilization savings, whole dollars; null when no cost is known. */
  est_savings_usd: number | null
  /** Plain-English explanation of the estimate (or why there is none); show verbatim. */
  savings_basis: string
}

/** Response of POST /workspace: the published plans plus this browser's uploads, ranked together. */
export interface Workspace {
  projects: Project[]
  /** Ranked: rank 1 first, uploaded pairs (`SUB:` ids) mixed in. */
  overlaps: Overlap[]
}

export interface Health {
  status: string
}
