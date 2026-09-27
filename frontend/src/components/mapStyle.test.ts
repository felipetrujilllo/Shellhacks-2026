// jsdom has no WebGL, so instead of rendering MapLibre these tests run the real layer filters and
// paint expressions through MapLibre's own style-spec evaluator, fed with the GeoJSON features
// the map is given (projectsToGeoJSON).
import {
  Color,
  featureFilter,
  latest,
  normalizePropertyExpression,
  validateStyleMin,
  type LayerSpecification,
} from '@maplibre/maplibre-gl-style-spec'
import type { LayerProps } from 'react-map-gl/maplibre'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { OTHER_UTILITY_COLOR, UTILITY_COLORS, utilityColor } from '../colors'
import { projectsToGeoJSON } from '../geo'
import type { LocationConfidence, Project } from '../types'
import { BASEMAPS, type BasemapId } from './basemaps'
import { LOW_CONFIDENCE_DASH, OVERLAP_DASH, POINT_STROKE_COLORS, projectLayers, utilityColorExpression } from './mapStyle'

type Feature = ReturnType<typeof projectsToGeoJSON>['features'][number]
type LayerType = 'line' | 'circle'

const GLOBALS = { zoom: 8 }

function project(id: string, confidence: LocationConfidence, overrides: Partial<Project> = {}): Project {
  return {
    project_id: id,
    utility: 'Georgia Power',
    state: 'GA',
    project_name: id,
    name_a: 'A',
    lat_a: 32.1,
    lon_a: -81.1,
    name_b: 'B',
    lat_b: 32.3,
    lon_b: -81.5,
    lat_center: 32.2,
    lon_center: -81.3,
    in_service_date: '2026-01-01',
    est_cost_usd: null,
    location_confidence: confidence,
    ...overrides,
  }
}

/** Build the map's GeoJSON feature for one project, exactly as ProjectMap does. */
function featureOf(p: Project): Feature {
  return projectsToGeoJSON([p]).features[0]
}

const asEvalFeature = (f: Feature) => ({ type: f.geometry.type, properties: f.properties })

function layerType(layer: LayerProps): LayerType {
  if (layer.type !== 'line' && layer.type !== 'circle') throw new Error(`unexpected layer type ${layer.type}`)
  return layer.type
}

function matches(layer: LayerProps, f: Feature): boolean {
  if (!('filter' in layer) || !layer.filter) return true
  return featureFilter(layer.filter, layer.id ?? 'layer').filter(GLOBALS, asEvalFeature(f))
}

/** Evaluate one paint property of `layer` for feature `f` (undefined when the layer doesn't set it). */
function paint(layer: LayerProps, prop: string, f: Feature): unknown {
  if (!('paint' in layer)) throw new Error(`layer ${layer.id} has no paint`)
  const value = (layer.paint as Record<string, unknown> | undefined)?.[prop]
  if (value === undefined) return undefined
  const spec = (latest as unknown as Record<string, Record<string, never>>)[`paint_${layerType(layer)}`][prop]
  const expr = normalizePropertyExpression(value as never, `${layer.id}.${prop}`, spec)
  const result: unknown = expr.evaluate(GLOBALS, asEvalFeature(f))
  return result instanceof Color ? result.toString() : result
}

/** The one layer of `layers` that draws feature `f` (its casing aside). */
function drawingLayer(layers: LayerProps[], f: Feature): LayerProps {
  const drawing = layers.filter((l) => matches(l, f))
  expect(drawing).toHaveLength(1)
  return drawing[0]
}

const LINE_PROPS = ['line-color', 'line-width', 'line-opacity', 'line-dasharray']
const CIRCLE_PROPS = ['circle-color', 'circle-radius', 'circle-opacity', 'circle-stroke-color', 'circle-stroke-width', 'circle-stroke-opacity']

function styleOf(layers: LayerProps[], f: Feature, props: string[]) {
  const layer = drawingLayer(layers, f)
  return Object.fromEntries(props.map((p) => [p, paint(layer, p, f)]))
}

// A runtime expression error makes MapLibre warn and silently fall back to the default value,
// which could make two styles "differ" for the wrong reason. Fail on any such warning.
let warn: ReturnType<typeof vi.spyOn>
beforeEach(() => { warn = vi.spyOn(console, 'warn') })
afterEach(() => {
  expect(warn).not.toHaveBeenCalled()
  warn.mockRestore()
})

describe('projectLayers: low-confidence styling', () => {
  const { casing, lines, lowLines, points } = projectLayers(null, '#ffffff')
  const lineLayers = [lines, lowLines]

  const confirmedLine = featureOf(project('LINE_OK', 'confirmed'))
  const lowLine = featureOf(project('LINE_LOW', 'low'))
  const confirmedPoint = featureOf(project('POINT_OK', 'confirmed', { lat_b: null, lon_b: null }))
  const lowPoint = featureOf(project('POINT_LOW', 'low', { lat_b: null, lon_b: null }))

  it('the features the map receives carry location_confidence', () => {
    expect(lowLine.properties.location_confidence).toBe('low')
    expect(confirmedLine.properties.location_confidence).toBe('confirmed')
    expect(lowPoint.geometry.type).toBe('Point')
  })

  it('draws a low-confidence line on a different layer, dotted and faded, from a confirmed one', () => {
    expect(drawingLayer(lineLayers, confirmedLine).id).toBe('project-lines')
    expect(drawingLayer(lineLayers, lowLine).id).toBe('project-lines-low')

    const confirmed = styleOf(lineLayers, confirmedLine, LINE_PROPS)
    const low = styleOf(lineLayers, lowLine, LINE_PROPS)
    expect(low).not.toEqual(confirmed)
    expect(confirmed['line-dasharray']).toBeUndefined() // solid
    expect(low['line-dasharray']).toEqual(LOW_CONFIDENCE_DASH)
    expect(low['line-opacity']).toBeLessThan(confirmed['line-opacity'] as number)
    // Same utility, same color: only the confidence styling changes.
    expect(low['line-color']).toBe(confirmed['line-color'])
  })

  it('keeps low-confidence lines visually distinct from the dashed overlap connectors', () => {
    expect(LOW_CONFIDENCE_DASH).not.toEqual(OVERLAP_DASH)
  })

  it('fades the casing under low-confidence lines', () => {
    expect(paint(casing, 'line-opacity', lowLine)).toBeLessThan(paint(casing, 'line-opacity', confirmedLine) as number)
  })

  it('draws a low-confidence point as a faded hollow ring in its utility color', () => {
    const confirmed = styleOf([points], confirmedPoint, CIRCLE_PROPS)
    const low = styleOf([points], lowPoint, CIRCLE_PROPS)
    expect(low).not.toEqual(confirmed)
    expect(low['circle-opacity']).toBeLessThan(confirmed['circle-opacity'] as number)
    expect(confirmed['circle-stroke-color']).toBe(Color.parse('#ffffff')!.toString())
    expect(low['circle-stroke-color']).toBe(Color.parse(UTILITY_COLORS['Georgia Power'])!.toString())
  })

  it('still dims non-selected projects when an overlap is selected, whatever their confidence', () => {
    const selected = projectLayers(['LINE_LOW', 'LINE_OK'], '#ffffff')
    const other = featureOf(project('OTHER_LOW', 'low'))
    const pairLayers = [selected.lines, selected.lowLines]
    expect(paint(drawingLayer(pairLayers, other), 'line-opacity', other))
      .toBeLessThan(paint(drawingLayer(pairLayers, lowLine), 'line-opacity', lowLine) as number)
    expect(paint(drawingLayer(pairLayers, confirmedLine), 'line-opacity', confirmedLine)).toBe(1)
  })

  it('is a valid MapLibre style', () => {
    const style = {
      version: 8 as const,
      sources: { projects: { type: 'geojson' as const, data: { type: 'FeatureCollection' as const, features: [] } } },
      layers: [casing, lines, lowLines, points].map((l) => ({ ...l, source: 'projects' }) as LayerSpecification),
    }
    expect(validateStyleMin(style)).toEqual([])
  })
})

describe('projectLayers: point outline per basemap (#47)', () => {
  // The colors ProjectMap passes: the basemap's pointStroke tone, resolved by POINT_STROKE_COLORS.
  const layersFor = (id: BasemapId, selectedPair: readonly string[] | null = null) =>
    projectLayers(selectedPair, '#020617', POINT_STROKE_COLORS[BASEMAPS[id].pointStroke])
  // Today's white on Dark Matter and satellite; --color-halo-dark on Positron (theme.test.ts: 18:1 there).
  const EXPECTED_OUTLINE: Record<BasemapId, string> = { dark: '#ffffff', light: '#020617', satellite: '#ffffff' }
  const RING_VISIBILITY: Record<BasemapId, string> = { dark: 'none', light: 'visible', satellite: 'none' }
  const IDS = Object.keys(BASEMAPS) as BasemapId[]

  const confirmedPoint = featureOf(project('POINT_OK', 'confirmed', { lat_b: null, lon_b: null }))
  const lowPoint = featureOf(project('POINT_LOW', 'low', { lat_b: null, lon_b: null }))
  const lowLine = featureOf(project('LINE_LOW', 'low'))
  const color = (hex: string) => Color.parse(hex)!.toString()

  it.each(IDS)('%s: outlines confirmed points in the basemap\'s outline color', (id) => {
    const { points } = layersFor(id)
    expect(paint(points, 'circle-stroke-color', confirmedPoint)).toBe(color(EXPECTED_OUTLINE[id]))
    // Low-confidence points keep their utility-colored stroke on every basemap.
    expect(paint(points, 'circle-stroke-color', lowPoint)).toBe(color(UTILITY_COLORS['Georgia Power']))
  })

  it.each(IDS)('%s: rings low-confidence points in the outline color only on the light basemap', (id) => {
    const { lowPointRing, points } = layersFor(id)
    expect((lowPointRing.layout as { visibility?: string } | undefined)?.visibility).toBe(RING_VISIBILITY[id])
    expect(paint(lowPointRing, 'circle-stroke-color', lowPoint)).toBe(color(EXPECTED_OUTLINE[id]))
    // Only low-confidence points get the ring, never confirmed points or lines.
    expect(matches(lowPointRing, lowPoint)).toBe(true)
    expect(matches(lowPointRing, confirmedPoint)).toBe(false)
    expect(matches(lowPointRing, lowLine)).toBe(false)
    // A ring, not a disc: no fill, and it starts where the point's own stroke ends (strokes sit outside circle-radius).
    expect(paint(lowPointRing, 'circle-opacity', lowPoint)).toBe(0)
    expect(paint(lowPointRing, 'circle-radius', lowPoint))
      .toBe((paint(points, 'circle-radius', lowPoint) as number) + (paint(points, 'circle-stroke-width', lowPoint) as number))
    expect(paint(lowPointRing, 'circle-stroke-width', lowPoint)).toBeGreaterThan(0)
    // Not faded like the utility stroke: it is what carries the 3:1 on Positron.
    expect(paint(lowPointRing, 'circle-stroke-opacity', lowPoint)).toBe(1)
  })

  it('keeps low-confidence points visibly different from confirmed ones on the light basemap', () => {
    const { lowPointRing, points } = layersFor('light')
    const confirmed = styleOf([points], confirmedPoint, CIRCLE_PROPS)
    const low = styleOf([points], lowPoint, CIRCLE_PROPS)
    expect(low['circle-opacity']).toBeLessThan(confirmed['circle-opacity'] as number) // faded, nearly hollow fill
    expect(low['circle-stroke-color']).not.toBe(confirmed['circle-stroke-color']) // utility color vs dark outline
    expect(low['circle-stroke-width']).not.toBe(confirmed['circle-stroke-width'])
    expect(low['circle-stroke-opacity']).toBeLessThan(confirmed['circle-stroke-opacity'] as number)
    // Confirmed points have no extra ring.
    expect(matches(lowPointRing, confirmedPoint)).toBe(false)
  })

  it('dims the ring with the rest of a project outside the selected pair', () => {
    const { lowPointRing } = layersFor('light', ['POINT_OK'])
    expect(paint(lowPointRing, 'circle-stroke-opacity', lowPoint)).toBeLessThan(1)
    const selected = layersFor('light', ['POINT_LOW'])
    expect(paint(selected.lowPointRing, 'circle-stroke-opacity', lowPoint)).toBe(1)
  })

  it.each(IDS)('%s: is a valid MapLibre style with the ring layer', (id) => {
    const { casing, lines, lowLines, lowPointRing, points } = layersFor(id)
    const style = {
      version: 8 as const,
      sources: { projects: { type: 'geojson' as const, data: { type: 'FeatureCollection' as const, features: [] } } },
      layers: [casing, lines, lowLines, lowPointRing, points].map((l) => ({ ...l, source: 'projects' }) as LayerSpecification),
    }
    expect(validateStyleMin(style)).toEqual([])
  })
})

describe('utilityColorExpression', () => {
  it('gives every utility the same color as utilityColor()', () => {
    const { lines } = projectLayers(null, '#ffffff')
    for (const utility of [...Object.keys(UTILITY_COLORS), 'Santee Cooper']) {
      const f = featureOf(project('P', 'confirmed', { utility }))
      expect(paint({ ...lines, paint: { 'line-color': utilityColorExpression } }, 'line-color', f))
        .toBe(Color.parse(utilityColor(utility))!.toString())
    }
    expect(utilityColor('Santee Cooper')).toBe(OTHER_UTILITY_COLOR)
  })
})
