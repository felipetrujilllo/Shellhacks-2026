// Pure API-data -> GeoJSON builders for the map layers. No rendering here.
// GeoJSON positions are [longitude, latitude].
import type { FeatureCollection, LineString, Point, Position } from 'geojson'
import type { Overlap, Project } from './types'

export interface ProjectFeatureProps {
  project_id: string
  utility: string
}

export interface OverlapFeatureProps {
  overlap_id: string
  rank: number
}

function endpoint(lat: number | null, lon: number | null): Position | null {
  return lat != null && lon != null ? [lon, lat] : null
}

const center = (p: Project): Position => [p.lon_center, p.lat_center]

/**
 * Geometry for one project:
 * - both endpoints known -> LineString a -> b
 * - otherwise (one or no endpoint known) -> Point at the project center.
 *   The center always exists and is exactly what overlap detection measures, so the
 *   marker sits where the overlap lines from overlapsToGeoJSON end.
 */
function projectGeometry(p: Project): LineString | Point {
  const a = endpoint(p.lat_a, p.lon_a)
  const b = endpoint(p.lat_b, p.lon_b)
  if (a && b) return { type: 'LineString', coordinates: [a, b] }
  return { type: 'Point', coordinates: center(p) }
}

export function projectsToGeoJSON(
  projects: Project[],
): FeatureCollection<LineString | Point, ProjectFeatureProps> {
  return {
    type: 'FeatureCollection',
    features: projects.map((p) => ({
      type: 'Feature',
      geometry: projectGeometry(p),
      properties: { project_id: p.project_id, utility: p.utility },
    })),
  }
}

/** Each overlap -> LineString between the two project centers. */
export function overlapsToGeoJSON(
  overlaps: Overlap[],
): FeatureCollection<LineString, OverlapFeatureProps> {
  return {
    type: 'FeatureCollection',
    features: overlaps.map((o) => ({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: [center(o.project_a), center(o.project_b)] },
      properties: { overlap_id: o.overlap_id, rank: o.rank },
    })),
  }
}
