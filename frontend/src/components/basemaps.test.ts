import { describe, expect, it } from 'vitest'
import { BASEMAPS, DEFAULT_BASEMAP, ESRI_ATTRIBUTION, SATELLITE_STYLE, basemapOptions, dataBounds, themedBasemap } from './basemaps'
import { makeOverlaps } from '../test/overlapFixtures'

const project = makeOverlaps(1)[0].project_a

describe('basemaps', () => {
  it('defaults to CARTO Dark Matter and offers exactly dark and satellite (in the dark theme)', () => {
    expect(DEFAULT_BASEMAP).toBe('dark')
    expect(themedBasemap(DEFAULT_BASEMAP, 'dark')).toBe('dark')
    // #45 added the light theme's Positron to BASEMAPS; the dark theme still offers exactly these two.
    expect(Object.keys(BASEMAPS)).toEqual(['dark', 'light', 'satellite'])
    expect(basemapOptions('dark')).toEqual(['dark', 'satellite'])
    expect(BASEMAPS.dark.style).toBe('https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json')
  })

  it('uses a version 8 raster style with the required Esri tiles and attribution', () => {
    expect(BASEMAPS.satellite.style).toBe(SATELLITE_STYLE)
    expect(SATELLITE_STYLE.version).toBe(8)
    expect(SATELLITE_STYLE.sources['esri-imagery']).toEqual({
      type: 'raster',
      tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
      tileSize: 256,
      maxzoom: 19,
      attribution: 'Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community',
    })
    expect(SATELLITE_STYLE.sources['esri-imagery']).toHaveProperty('attribution', ESRI_ATTRIBUTION)
    expect(SATELLITE_STYLE.layers).toEqual([{ id: 'esri-imagery', type: 'raster', source: 'esri-imagery' }])
  })
})

describe('basemaps per theme (#45)', () => {
  it('uses CARTO Positron, a free light vector style needing no key, as the light basemap', () => {
    expect(BASEMAPS.light).toEqual({
      label: 'Light',
      style: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
      halo: 'dark',
      pointStroke: 'dark', // #47: dark point outline on the near-white style (see 'point outline per basemap')
    })
  })

  it('in the light theme, defaults to the light style and puts it in the "Dark" slot, before satellite', () => {
    expect(themedBasemap(DEFAULT_BASEMAP, 'light')).toBe('light')
    expect(basemapOptions('light')).toEqual(['light', 'satellite'])
  })

  it('keeps satellite available and selected in both themes', () => {
    for (const theme of ['dark', 'light'] as const) {
      expect(basemapOptions(theme), theme).toContain('satellite')
      expect(themedBasemap('satellite', theme), theme).toBe('satellite')
    }
  })

  it('swaps the vector style when the theme changes, whichever vector style was picked', () => {
    for (const pick of ['dark', 'light'] as const) {
      expect(themedBasemap(pick, 'light'), pick).toBe('light')
      expect(themedBasemap(pick, 'dark'), pick).toBe('dark')
    }
  })

  it('always shows a basemap the picker offers for that theme', () => {
    for (const theme of ['dark', 'light'] as const) {
      for (const pick of Object.keys(BASEMAPS) as (keyof typeof BASEMAPS)[]) {
        expect(basemapOptions(theme), `${pick} in ${theme}`).toContain(themedBasemap(pick, theme))
      }
    }
  })

  it('draws the dark casing on both vector styles and the light casing on satellite', () => {
    // Unchanged from before #45 for dark and satellite; on the near-white light style the dark casing
    // is what gives the lines 3:1 (theme.test.ts checks the ratios).
    expect(BASEMAPS.dark.halo).toBe('dark')
    expect(BASEMAPS.light.halo).toBe('dark')
    expect(BASEMAPS.satellite.halo).toBe('light')
  })
})

describe('point outline per basemap (#47)', () => {
  it('outlines points white on Dark Matter and satellite, as before, and dark on Positron', () => {
    // mapStyle.test.ts checks the colors projectLayers draws from these; theme.test.ts the ratios.
    expect(Object.fromEntries(Object.entries(BASEMAPS).map(([id, b]) => [id, b.pointStroke])))
      .toEqual({ dark: 'light', light: 'dark', satellite: 'light' })
  })
})

describe('dataBounds', () => {
  it('returns null for no projects', () => expect(dataBounds([])).toBeNull())
  it('includes centers and endpoints across projects in longitude/latitude order', () => {
    expect(dataBounds([
      { ...project, lon_center: -82, lat_center: 32, lon_a: -84, lat_a: 31, lon_b: -80, lat_b: 33 },
      { ...project, lon_center: -79, lat_center: 35, lon_a: null, lat_a: null, lon_b: -81, lat_b: 30 },
    ])).toEqual([[-84, 30], [-79, 35]])
  })
  it('ignores incomplete pairs and nonfinite values without dropping zero', () => {
    expect(dataBounds([{ ...project, lon_center: 0, lat_center: 0,
      lon_a: null, lat_a: -40, lon_b: Infinity, lat_b: 80 }])).toEqual([[0, 0], [0, 0]])
  })
  it('supports a single point with no endpoints', () => {
    expect(dataBounds([{ ...project, lon_center: -82, lat_center: 32,
      lon_a: null, lat_a: null, lon_b: null, lat_b: null }])).toEqual([[-82, 32], [-82, 32]])
  })
})
