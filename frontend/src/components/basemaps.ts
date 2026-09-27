import type { StyleSpecification } from 'maplibre-gl'
import type { Theme } from '../theme'
import type { Project } from '../types'

export type BasemapId = 'dark' | 'light' | 'satellite'
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
/** A casing tone: 'dark' or 'light' (mapStyle.ts has the colors). */
export type Tone = 'dark' | 'light'
/**
 * Every basemap. `halo` is the casing color drawn under project lines and overlap connectors:
 * dark on both vector styles (on the near-white light style it is what keeps the lines at 3:1),
 * light on satellite imagery. `pointStroke` outlines single-point projects (#47): white on Dark
 * Matter and satellite, as before; dark on Positron, where white is 1.1:1 against the land. On
 * a dark outline, low-confidence points get it as an outer ring too (mapStyle.ts).
 */
export const BASEMAPS: Record<BasemapId, { label: string; style: string | StyleSpecification; halo: Tone; pointStroke: Tone }> = {
  dark: { label: 'Dark', style: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json', halo: 'dark', pointStroke: 'light' },
  // CARTO Positron: free, no key, and the same vector tiles as Dark Matter.
  light: { label: 'Light', style: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json', halo: 'dark', pointStroke: 'dark' },
  satellite: { label: 'Satellite', style: SATELLITE_STYLE, halo: 'light', pointStroke: 'light' },
}

/**
 * What the map's basemap picker offers, in order. Dark and Light are also the app theme: picking
 * one switches the theme (and shows that theme's vector style); Satellite leaves the theme alone.
 */
export const BASEMAP_OPTIONS: readonly BasemapId[] = ['dark', 'light', 'satellite']

/** The basemap the map shows, which is also the picker's pressed option: satellite if on, else the theme's own style. */
export function pickerValue(satellite: boolean, theme: Theme): BasemapId {
  return satellite ? 'satellite' : theme
}

/** What choosing `id` in the picker does: Satellite turns imagery on; Dark/Light turn it off and set that theme. */
export function pickerChange(id: BasemapId): { satellite: true; theme: null } | { satellite: false; theme: Theme } {
  return id === 'satellite' ? { satellite: true, theme: null } : { satellite: false, theme: id }
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
