import type { StyleSpecification } from 'maplibre-gl'
import type { Project } from '../types'

export type BasemapId = 'dark' | 'satellite'
export const DEFAULT_BASEMAP: BasemapId = 'dark'
export const ESRI_ATTRIBUTION = 'Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community'
export const SATELLITE_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    'esri-imagery': {
      type: 'raster',
      tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
      tileSize: 256,
      maxzoom: 19,
      attribution: ESRI_ATTRIBUTION,
    },
  },
  layers: [{ id: 'esri-imagery', type: 'raster', source: 'esri-imagery' }],
}
export const BASEMAPS: Record<BasemapId, { label: string; style: string | StyleSpecification }> = {
  dark: { label: 'Dark', style: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json' },
  satellite: { label: 'Satellite', style: SATELLITE_STYLE },
}

export type DataBounds = [[number, number], [number, number]]

/** Includes complete coordinate pairs only; a missing endpoint must not become (0, 0). */
export function dataBounds(projects: Project[]): DataBounds | null {
  let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity
  for (const project of projects) {
    for (const [lon, lat] of [
      [project.lon_center, project.lat_center],
      [project.lon_a, project.lat_a],
      [project.lon_b, project.lat_b],
    ]) {
      if (lon == null || lat == null || !Number.isFinite(lon) || !Number.isFinite(lat)) continue
      minLon = Math.min(minLon, lon)
      maxLon = Math.max(maxLon, lon)
      minLat = Math.min(minLat, lat)
      maxLat = Math.max(maxLat, lat)
    }
  }
  return minLon === Infinity ? null : [[minLon, minLat], [maxLon, maxLat]]
}
