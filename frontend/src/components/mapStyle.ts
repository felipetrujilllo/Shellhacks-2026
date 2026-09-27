// Pure MapLibre style builders for the project layers, plus the map's style constants.
// No MapLibre runtime import here (types only), so jsdom tests can evaluate these expressions.
import type { ExpressionSpecification } from 'maplibre-gl'
import type { LayerProps } from 'react-map-gl/maplibre'
import { OTHER_UTILITY_COLOR, UTILITY_COLORS } from '../colors'
import { themeColor } from '../theme'
import type { Tone } from './basemaps'

export const PROJECT_LINE_WIDTH = 5
export const OVERLAP_LINE_WIDTH = 4
export const SELECTED_LINE_WIDTH = 7
export const LINE_CASING_WIDTH = 3

// Colors come from theme.css (see theme.ts); the hex is only the fallback and must match it.
export const OVERLAP_COLOR = themeColor('--color-overlap', '#f59e0b') // amber
export const SELECTED_OVERLAP_COLOR = themeColor('--color-overlap-selected', '#c4b5fd') // violet
/** Outline of confirmed single-point projects on the dark and satellite basemaps (BASEMAPS[…].pointStroke 'light'). */
export const POINT_STROKE_COLOR = themeColor('--color-point-stroke', '#ffffff')
/**
 * Casing that separates lines from the basemap: dark on the vector basemaps, light on satellite.
 * The dark one also outlines points on the light basemap (pointStroke 'dark'): one dark casing color.
 */
export const HALO_COLOR_DARK = themeColor('--color-halo-dark', '#020617')
export const HALO_COLOR_LIGHT = themeColor('--color-halo-light', '#ffffff')
/** The point outline for each basemap's pointStroke tone (basemaps.ts). */
export const POINT_STROKE_COLORS: Record<Tone, string> = { dark: HALO_COLOR_DARK, light: POINT_STROKE_COLOR }
/** Overlap connectors are long amber dashes; low-confidence projects must not look like them. */
export const OVERLAP_DASH: [number, number] = [2, 1.5]

// Low-confidence (unconfirmed) locations: faded, and drawn as round dots (lines) or hollow
// rings (points) in the utility's own color, so they read as "tentative" without being
// mistaken for the amber dashed overlap connectors.
export const LOW_CONFIDENCE_OPACITY = 0.6
/** Near-zero dashes + round caps render as a row of dots. In line widths. */
export const LOW_CONFIDENCE_DASH: [number, number] = [0.1, 2]
const LOW_CONFIDENCE_CASING_OPACITY = 0.35
const LOW_CONFIDENCE_POINT_FILL_OPACITY = 0.2
const DIMMED_OPACITY = 0.25
const POINT_RADIUS = 6
const LOW_POINT_STROKE_WIDTH = 2
/** Width of the dark ring outside a low-confidence point's utility-colored stroke, on the light basemap. */
export const LOW_POINT_RING_WIDTH = 1

export const PROJECT_LINES_ID = 'project-lines'
export const PROJECT_LOW_LINES_ID = 'project-lines-low'
export const PROJECT_POINTS_ID = 'project-points'
export const PROJECT_LOW_POINT_RING_ID = 'project-points-low-ring'

const IS_LOW: ExpressionSpecification = ['==', ['get', 'location_confidence'], 'low']
const IS_LINE: ExpressionSpecification = ['==', ['geometry-type'], 'LineString']
const IS_POINT: ExpressionSpecification = ['==', ['geometry-type'], 'Point']

/**
 * MapLibre twin of colors.ts's utilityColor(), built from the same table. The cast is needed
 * because TS can't see that the spread yields at least one label/color pair (mapStyle.test.ts
 * evaluates it against utilityColor()).
 */
export const utilityColorExpression = [
  'match',
  ['get', 'utility'],
  ...Object.entries(UTILITY_COLORS).flat(),
  OTHER_UTILITY_COLOR,
] as unknown as ExpressionSpecification

/** Multiply `opacity` for low-confidence features by `lowFactor`. */
function withConfidence(opacity: ExpressionSpecification | number, lowFactor: number): ExpressionSpecification {
  return ['*', opacity, ['case', IS_LOW, lowFactor, 1]]
}

/**
 * Layers for the "projects" source. `selectedPair` (the selected overlap's two project ids)
 * dims every other project; `haloColor` is the casing color that separates lines from the basemap;
 * `pointStrokeColor` outlines confirmed points (the basemap's pointStroke, basemaps.ts).
 *
 * Low-confidence points keep their faded utility-colored stroke. When the outline is the dark one
 * (HALO_COLOR_DARK, on the near-white light basemap, where that stroke is under 3:1), they also get
 * a thin ring of it just outside the stroke (`lowPointRing`); the layer is hidden otherwise, so the
 * dark and satellite basemaps look as before.
 */
export function projectLayers(selectedPair: readonly string[] | null, haloColor: string, pointStrokeColor: string = POINT_STROKE_COLOR) {
  const selection: ExpressionSpecification | number = selectedPair
    ? ['case', ['in', ['get', 'project_id'], ['literal', [...selectedPair]]], 1, DIMMED_OPACITY]
    : 1

  const casing: LayerProps = {
    id: 'project-casing',
    type: 'line',
    filter: IS_LINE,
    paint: {
      'line-color': haloColor,
      'line-width': PROJECT_LINE_WIDTH + LINE_CASING_WIDTH,
      'line-opacity': withConfidence(selection, LOW_CONFIDENCE_CASING_OPACITY),
    },
    layout: { 'line-cap': 'round' },
  }
  const lines: LayerProps = {
    id: PROJECT_LINES_ID,
    type: 'line',
    filter: ['all', IS_LINE, ['!', IS_LOW]],
    paint: { 'line-color': utilityColorExpression, 'line-width': PROJECT_LINE_WIDTH, 'line-opacity': selection },
    layout: { 'line-cap': 'round' },
  }
  // A separate layer (not a data-driven dasharray) keeps confirmed lines plainly solid.
  const lowLines: LayerProps = {
    id: PROJECT_LOW_LINES_ID,
    type: 'line',
    filter: ['all', IS_LINE, IS_LOW],
    paint: {
      'line-color': utilityColorExpression,
      'line-width': PROJECT_LINE_WIDTH,
      'line-opacity': withConfidence(selection, LOW_CONFIDENCE_OPACITY),
      'line-dasharray': LOW_CONFIDENCE_DASH,
    },
    layout: { 'line-cap': 'round' },
  }
  // Strokes are drawn outside circle-radius, so this ring (drawn first, under the points) sits
  // just outside the low-confidence point's own stroke. It is not faded like that stroke: it is
  // what keeps the point at 3:1 on the light basemap.
  const lowPointRing: LayerProps = {
    id: PROJECT_LOW_POINT_RING_ID,
    type: 'circle',
    filter: ['all', IS_POINT, IS_LOW],
    paint: {
      'circle-radius': POINT_RADIUS + LOW_POINT_STROKE_WIDTH,
      'circle-opacity': 0,
      'circle-stroke-color': pointStrokeColor,
      'circle-stroke-width': LOW_POINT_RING_WIDTH,
      'circle-stroke-opacity': selection,
    },
    layout: { visibility: pointStrokeColor === HALO_COLOR_DARK ? 'visible' : 'none' },
  }
  const points: LayerProps = {
    id: PROJECT_POINTS_ID,
    type: 'circle',
    filter: IS_POINT,
    paint: {
      'circle-color': utilityColorExpression,
      'circle-radius': POINT_RADIUS,
      'circle-opacity': withConfidence(selection, LOW_CONFIDENCE_POINT_FILL_OPACITY),
      'circle-stroke-color': ['case', IS_LOW, utilityColorExpression, pointStrokeColor],
      'circle-stroke-width': ['case', IS_LOW, LOW_POINT_STROKE_WIDTH, 1.5],
      'circle-stroke-opacity': withConfidence(selection, LOW_CONFIDENCE_OPACITY),
    },
  }
  return { casing, lines, lowLines, lowPointRing, points }
}
