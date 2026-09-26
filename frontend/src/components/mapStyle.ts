// Pure MapLibre style builders for the project layers, plus the map's style constants.
// No MapLibre runtime import here (types only), so jsdom tests can evaluate these expressions.
import type { ExpressionSpecification } from 'maplibre-gl'
import type { LayerProps } from 'react-map-gl/maplibre'
import { OTHER_UTILITY_COLOR, UTILITY_COLORS } from '../colors'

export const PROJECT_LINE_WIDTH = 5
export const OVERLAP_LINE_WIDTH = 4
export const SELECTED_LINE_WIDTH = 7
export const LINE_CASING_WIDTH = 3

export const OVERLAP_COLOR = '#f59e0b' // amber
export const SELECTED_OVERLAP_COLOR = '#c4b5fd' // violet
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

export const PROJECT_LINES_ID = 'project-lines'
export const PROJECT_LOW_LINES_ID = 'project-lines-low'
export const PROJECT_POINTS_ID = 'project-points'

const IS_LOW: ExpressionSpecification = ['==', ['get', 'location_confidence'], 'low']
const IS_LINE: ExpressionSpecification = ['==', ['geometry-type'], 'LineString']

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
 * dims every other project; `haloColor` is the casing color that separates lines from the basemap.
 */
export function projectLayers(selectedPair: readonly string[] | null, haloColor: string) {
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
  const points: LayerProps = {
    id: PROJECT_POINTS_ID,
    type: 'circle',
    filter: ['==', ['geometry-type'], 'Point'],
    paint: {
      'circle-color': utilityColorExpression,
      'circle-radius': 6,
      'circle-opacity': withConfidence(selection, LOW_CONFIDENCE_POINT_FILL_OPACITY),
      'circle-stroke-color': ['case', IS_LOW, utilityColorExpression, '#ffffff'],
      'circle-stroke-width': ['case', IS_LOW, 2, 1.5],
      'circle-stroke-opacity': withConfidence(selection, LOW_CONFIDENCE_OPACITY),
    },
  }
  return { casing, lines, lowLines, points }
}
