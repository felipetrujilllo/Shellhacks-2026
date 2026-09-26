// MapLibre map of both utilities' projects with overlap connectors. Map-only logic lives here.
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useMemo, useRef } from 'react'
import Map, {
  Layer,
  NavigationControl,
  Source,
  type LayerProps,
  type MapLayerMouseEvent,
  type MapRef,
} from 'react-map-gl/maplibre'
import { setWorkerUrl, type ExpressionSpecification } from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { overlapsToGeoJSON, projectsToGeoJSON } from '../geo'
import type { Overlap, Project } from '../types'

// maplibre-gl v6 finds its worker via a runtime-built relative URL that Vite can't see, so
// neither dev pre-bundling nor the production build ships it — the worker 404s and no tiles
// or GeoJSON render. Bundle the worker explicitly and hand MapLibre its URL.
setWorkerUrl(maplibreWorkerUrl)

// Free, no-API-key basemap.
const MAP_STYLE = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json'

// SC/GA border along the Savannah River.
const INITIAL_VIEW = { longitude: -82.2, latitude: 32.9, zoom: 6.5 }

// Single source of truth for utility colors: the legend and the layer styles both read this.
const DESC = 'Dominion Energy South Carolina'
const GPC = 'Georgia Power'
export const UTILITY_COLORS = {
  [DESC]: '#2563eb', // blue
  [GPC]: '#dc2626', // red
}
const OTHER_UTILITY_COLOR = '#6b7280'
const OVERLAP_COLOR = '#f59e0b' // amber
const SELECTED_OVERLAP_COLOR = '#7c3aed' // violet

const OVERLAP_LAYER_ID = 'overlap-lines'

const utilityColor: ExpressionSpecification = [
  'match',
  ['get', 'utility'],
  DESC,
  UTILITY_COLORS[DESC],
  GPC,
  UTILITY_COLORS[GPC],
  OTHER_UTILITY_COLOR,
]

interface ProjectMapProps {
  projects: Project[]
  overlaps: Overlap[]
  selectedId: string | null
  onSelect: (overlapId: string) => void
}

export default function ProjectMap({ projects, overlaps, selectedId, onSelect }: ProjectMapProps) {
  const mapRef = useRef<MapRef>(null)
  const projectData = useMemo(() => projectsToGeoJSON(projects), [projects])
  const overlapData = useMemo(() => overlapsToGeoJSON(overlaps), [overlaps])

  // Fly to the selected pair.
  useEffect(() => {
    const o = overlaps.find((x) => x.overlap_id === selectedId)
    const map = mapRef.current
    if (!o || !map) return
    const lons = [o.project_a.lon_center, o.project_b.lon_center]
    const lats = [o.project_a.lat_center, o.project_b.lat_center]
    map.fitBounds(
      [
        [Math.min(...lons), Math.min(...lats)],
        [Math.max(...lons), Math.max(...lats)],
      ],
      { padding: 80, maxZoom: 11, duration: 1200 },
    )
  }, [selectedId, overlaps])

  const selected = selectedId ?? ''
  const projectLineLayer: LayerProps = {
    id: 'project-lines',
    type: 'line',
    filter: ['==', ['geometry-type'], 'LineString'],
    paint: { 'line-color': utilityColor, 'line-width': 4 },
    layout: { 'line-cap': 'round' },
  }
  const projectPointLayer: LayerProps = {
    id: 'project-points',
    type: 'circle',
    filter: ['==', ['geometry-type'], 'Point'],
    paint: {
      'circle-color': utilityColor,
      'circle-radius': 6,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 1.5,
    },
  }
  const overlapLayer: LayerProps = {
    id: OVERLAP_LAYER_ID,
    type: 'line',
    paint: {
      'line-color': ['case', ['==', ['get', 'overlap_id'], selected], SELECTED_OVERLAP_COLOR, OVERLAP_COLOR],
      'line-width': ['case', ['==', ['get', 'overlap_id'], selected], 6, 3],
      'line-dasharray': [2, 1.5],
      'line-opacity': 0.9,
    },
  }

  function handleClick(e: MapLayerMouseEvent) {
    const id = e.features?.[0]?.properties?.overlap_id
    if (typeof id === 'string') onSelect(id)
  }

  return (
    <div className="relative h-full w-full">
      <Map
        ref={mapRef}
        initialViewState={INITIAL_VIEW}
        mapStyle={MAP_STYLE}
        style={{ width: '100%', height: '100%' }}
        interactiveLayerIds={[OVERLAP_LAYER_ID]}
        onClick={handleClick}
      >
        <NavigationControl position="top-right" />
        <Source id="projects" type="geojson" data={projectData}>
          <Layer {...projectLineLayer} />
          <Layer {...projectPointLayer} />
        </Source>
        <Source id="overlaps" type="geojson" data={overlapData}>
          <Layer {...overlapLayer} />
        </Source>
      </Map>
      <Legend />
    </div>
  )
}

function Legend() {
  return (
    <div className="absolute bottom-6 left-2 rounded-md bg-white/90 p-2 text-xs shadow">
      {Object.entries(UTILITY_COLORS).map(([utility, color]) => (
        <div key={utility} className="flex items-center gap-2">
          <span className="inline-block h-1 w-5 rounded" style={{ backgroundColor: color }} />
          {utility}
        </div>
      ))}
      <div className="flex items-center gap-2">
        <span className="inline-block w-5 border-t-2 border-dashed" style={{ borderColor: OVERLAP_COLOR }} />
        Coordination opportunity
      </div>
    </div>
  )
}
