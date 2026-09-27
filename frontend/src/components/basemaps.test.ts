import { describe, expect, it } from 'vitest'
import { BASEMAPS, BASEMAP_OPTIONS, ESRI_ATTRIBUTION, SATELLITE_STYLE, dataBounds, pickerChange, pickerValue } from './basemaps'
import { makeOverlaps } from '../test/overlapFixtures'

const project = makeOverlaps(1)[0].project_a

describe('basemaps', () => {
  it('defaults to CARTO Dark Matter (no satellite, dark theme) and offers exactly Dark, Light, Satellite in that order', () => {
    expect(pickerValue(false, 'dark')).toBe('dark')
    expect(Object.keys(BASEMAPS)).toEqual(['dark', 'light', 'satellite'])
    expect(BASEMAP_OPTIONS).toEqual(['dark', 'light', 'satellite'])
    expect(BASEMAP_OPTIONS.map((id) => BASEMAPS[id].label)).toEqual(['Dark', 'Light', 'Satellite'])
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

  it('shows satellite whenever it is on, whatever the theme', () => {
    for (const theme of ['dark', 'light'] as const) {
      expect(pickerValue(true, theme), theme).toBe('satellite')
    }
  })

  it('otherwise shows (and presses) the theme\'s own vector style, so switching theme swaps Dark Matter and Positron', () => {
    expect(pickerValue(false, 'dark')).toBe('dark')
    expect(pickerValue(false, 'light')).toBe('light')
  })

  it('always shows a basemap the picker offers', () => {
    for (const theme of ['dark', 'light'] as const) {
      for (const satellite of [false, true]) {
        expect(BASEMAP_OPTIONS, `${theme}, satellite ${satellite}`).toContain(pickerValue(satellite, theme))
      }
    }
  })

  it('picking Dark or Light turns satellite off and sets that theme; picking Satellite leaves the theme alone', () => {
    expect(pickerChange('dark')).toEqual({ satellite: false, theme: 'dark' })
    expect(pickerChange('light')).toEqual({ satellite: false, theme: 'light' })
    expect(pickerChange('satellite')).toEqual({ satellite: true, theme: null })
  })

  it('round-trips: after any pick, the picker presses the option just picked', () => {
    for (const current of ['dark', 'light'] as const) {
      for (const id of BASEMAP_OPTIONS) {
        const change = pickerChange(id)
        expect(pickerValue(change.satellite, change.theme ?? current), `${id} from ${current}`).toBe(id)
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
