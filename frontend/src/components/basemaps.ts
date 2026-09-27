import type { StyleSpecification } from 'maplibre-gl'
import type { Theme } from '../theme'
import type { Project } from '../types'

export type BasemapId = 'dark' | 'light' | 'satellite'
/** The pick before the user chooses one; themedBasemap() shows the light style for it in the light theme. */
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
/**
 * Every basemap. `halo` is the casing color drawn under project lines and overlap connectors:
 * dark on both vector styles (on the near-white light style it is what keeps the lines at 3:1),
 * light on satellite imagery.
 */
export const BASEMAPS: Record<BasemapId, { label: string; style: string | StyleSpecification; halo: 'dark' | 'light' }> = {
  dark: { label: 'Dark', style: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json', halo: 'dark' },
  // CARTO Positron: free, no key, and the same vector tiles as Dark Matter.
  light: { label: 'Light', style: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json', halo: 'dark' },
  satellite: { label: 'Satellite', style: SATELLITE_STYLE, halo: 'light' },
}

// Each theme's own vector basemap: the one in the "Dark" slot of the basemap picker.
const THEME_BASEMAP: Record<Theme, BasemapId> = { dark: 'dark', light: 'light' }

/** The basemaps the picker offers in `theme`: the theme's vector style, then satellite (both themes). */
export function basemapOptions(theme: Theme): BasemapId[] {
  return [THEME_BASEMAP[theme], 'satellite']
}

/**
 * The basemap to show for the user's pick in `theme`: satellite stays satellite, and either
 * vector style becomes the theme's own, so switching theme swaps Dark Matter and Positron.
 */
export function themedBasemap(pick: BasemapId, theme: Theme): BasemapId {
  return pick === 'satellite' ? 'satellite' : THEME_BASEMAP[theme]
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
