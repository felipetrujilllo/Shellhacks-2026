import { describe, expect, it } from 'vitest'
import { BASEMAPS, DEFAULT_BASEMAP, ESRI_ATTRIBUTION, SATELLITE_STYLE, dataBounds } from './basemaps'
import { makeOverlaps } from '../test/overlapFixtures'

const project = makeOverlaps(1)[0].project_a

describe('basemaps', () => {
  it('defaults to CARTO Dark Matter and offers exactly dark and satellite', () => {
    expect(DEFAULT_BASEMAP).toBe('dark')
    expect(Object.keys(BASEMAPS)).toEqual(['dark', 'satellite'])
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
