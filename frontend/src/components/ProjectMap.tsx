// MapLibre map of both utilities' projects with overlap connectors. Map-only logic lives here.
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import Map, {
  AttributionControl,
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
import BasemapToggle from './BasemapToggle'
import MapLegend from './MapLegend'
import { BASEMAPS, DEFAULT_BASEMAP, dataBounds, type BasemapId } from './basemaps'
import {
  LINE_CASING_WIDTH,
  OVERLAP_COLOR,
  OVERLAP_DASH,
  OVERLAP_LINE_WIDTH,
  PROJECT_LINES_ID,
  PROJECT_LOW_LINES_ID,
  PROJECT_POINTS_ID,
  SELECTED_LINE_WIDTH,
  SELECTED_OVERLAP_COLOR,
  projectLayers,
} from './mapStyle'

// maplibre-gl v6 finds its worker via a runtime-built relative URL that Vite can't see, so
// neither dev pre-bundling nor the production build ships it — the worker 404s and no tiles
// or GeoJSON render. Bundle the worker explicitly and hand MapLibre its URL.
setWorkerUrl(maplibreWorkerUrl)

const FIT_PADDING = { top: 100, right: 64, bottom: 72, left: 64 }

// SC/GA border along the Savannah River.
const INITIAL_VIEW = { longitude: -82.2, latitude: 32.9, zoom: 6.5 }

const OVERLAP_LAYER_ID = 'overlap-lines'

interface ProjectMapProps {
  projects: Project[]
  overlaps: Overlap[]
  selectedId: string | null
  onSelect: (overlapId: string) => void
  focusedProject?: Project | null
}

export default function ProjectMap({ projects, overlaps, selectedId, onSelect, focusedProject }: ProjectMapProps) {
  const mapRef = useRef<MapRef>(null)
  const [basemap, setBasemap] = useState<BasemapId>(DEFAULT_BASEMAP)
  const [loaded, setLoaded] = useState(false)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const hoveredProject = projects.find((p) => p.project_id === hoveredId)
  const bounds = useMemo(() => dataBounds(projects), [projects])
  const haloColor = basemap === 'dark' ? '#020617' : '#ffffff'

  function fitData() {
    if (bounds) mapRef.current?.fitBounds(bounds, { padding: FIT_PADDING, maxZoom: 11, duration: 600 })
  }

  useEffect(() => {
    if (loaded && bounds && !selectedId && !focusedProject) {
      mapRef.current?.fitBounds(bounds, { padding: FIT_PADDING, maxZoom: 11, duration: 0 })
    }
  }, [loaded, bounds, selectedId, focusedProject])
  const projectData = useMemo(() => projectsToGeoJSON(projects), [projects])
  const overlapData = useMemo(() => overlapsToGeoJSON(overlaps), [overlaps])

  useEffect(() => {
    if (!loaded || !focusedProject) return
    const bounds = dataBounds([focusedProject])
    if (bounds) mapRef.current?.fitBounds(bounds, {
      padding: { top: 110, left: 55, bottom: 80, right: 55 }, maxZoom: 11, duration: 900,
    })
  }, [loaded, focusedProject])

  // Fly to the selected pair.
  useEffect(() => {
    const o = overlaps.find((x) => x.overlap_id === selectedId)
    const map = mapRef.current
    if (!o || !map || !loaded) return
    const selectedBounds = dataBounds([o.project_a, o.project_b])
    if (selectedBounds) map.fitBounds(selectedBounds,
      { padding: { ...FIT_PADDING, right: map.getContainer().clientWidth > 700 ? 325 : 64 }, maxZoom: 11, duration: 1200 })
  }, [selectedId, overlaps, loaded])

  const selected = selectedId ?? ''
  const selectedOverlap = overlaps.find((o) => o.overlap_id === selectedId)
  const project = projectLayers(
    selectedOverlap ? [selectedOverlap.project_a.project_id, selectedOverlap.project_b.project_id] : null,
    haloColor,
  )
  const overlapOpacity: ExpressionSpecification = selectedOverlap
    ? ['case', ['==', ['get', 'overlap_id'], selected], 1, 0.2]
    : ['literal', 0.9]
  const overlapLayer: LayerProps = {
    id: OVERLAP_LAYER_ID,
    type: 'line',
    paint: {
      'line-color': ['case', ['==', ['get', 'overlap_id'], selected], SELECTED_OVERLAP_COLOR, OVERLAP_COLOR],
      'line-width': ['case', ['==', ['get', 'overlap_id'], selected], SELECTED_LINE_WIDTH, OVERLAP_LINE_WIDTH],
      'line-dasharray': OVERLAP_DASH,
      'line-opacity': overlapOpacity,
    },
  }

  const overlapCasing: LayerProps = {
    ...overlapLayer,
    id: 'overlap-casing',
    paint: {
      // A continuous casing avoids mismatched dash spacing: MapLibre measures
      // dash lengths in line-width units, which differ between these two layers.
      'line-color': haloColor,
      'line-opacity': overlapOpacity,
      'line-width': ['case', ['==', ['get', 'overlap_id'], selected],
        SELECTED_LINE_WIDTH + LINE_CASING_WIDTH, OVERLAP_LINE_WIDTH + LINE_CASING_WIDTH],
    },
  }

  function handleClick(e: MapLayerMouseEvent) {
    const id = e.features?.find((f) => f.properties?.overlap_id)?.properties?.overlap_id
    if (typeof id === 'string') onSelect(id)
    handleHover(e)
  }

  function handleHover(e: MapLayerMouseEvent) {
    const id = e.features?.find((f) => f.properties?.project_id)?.properties?.project_id
    setHoveredId(typeof id === 'string' ? id : null)
  }

  return (
    <div className="relative h-full w-full bg-slate-950">
      <Map
        ref={mapRef}
        initialViewState={INITIAL_VIEW}
        mapStyle={BASEMAPS[basemap].style}
        attributionControl={false}
        onLoad={() => setLoaded(true)}
        style={{ width: '100%', height: '100%' }}
        interactiveLayerIds={[OVERLAP_LAYER_ID, PROJECT_LINES_ID, PROJECT_LOW_LINES_ID, PROJECT_POINTS_ID]}
        cursor={hoveredId ? 'pointer' : 'grab'}
        onClick={handleClick}
        onMouseMove={handleHover}
        onMouseLeave={() => setHoveredId(null)}
      >
        <NavigationControl position="top-right" />
        <AttributionControl position="bottom-right" compact={false} />
        <Source id="projects" type="geojson" data={projectData}>
          <Layer {...project.casing} />
          <Layer {...project.lines} />
          <Layer {...project.lowLines} />
          <Layer {...project.points} />
        </Source>
        <Source id="overlaps" type="geojson" data={overlapData}>
          <Layer {...overlapCasing} />
          <Layer {...overlapLayer} />
        </Source>
      </Map>
      <div className="absolute left-4 top-4 flex flex-wrap items-center gap-2 pr-12">
        <BasemapToggle value={basemap} onChange={setBasemap} />
        <button type="button" onClick={fitData} disabled={!bounds}
          className="min-h-11 rounded-xl border border-white/15 bg-slate-950/90 px-3 text-xs font-semibold text-slate-200 shadow-lg backdrop-blur-md hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-sky-400 disabled:opacity-40">
          Fit to data
        </button>
        <MapLegend />
      </div>
      {hoveredProject && (
        <div role="tooltip" className="pointer-events-none absolute bottom-24 left-4 right-4 max-w-sm rounded-xl border border-white/15 bg-slate-950/95 p-4 text-slate-100 shadow-xl backdrop-blur-md">
          <p className="mb-1 text-xs text-sky-300">{hoveredProject.utility}</p>
          <p className="text-sm font-semibold">{hoveredProject.project_name}</p>
          <p className="mt-2 text-xs text-slate-400">In service: <time dateTime={hoveredProject.in_service_date}>{hoveredProject.in_service_date}</time></p>
        </div>
      )}
    </div>
  )
}
