import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { Color, latest, normalizePropertyExpression } from '@maplibre/maplibre-gl-style-spec'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Theme } from '../theme'
import ProjectMap from './ProjectMap'
import { BASEMAPS } from './basemaps'
import { HALO_COLOR_DARK, HALO_COLOR_LIGHT, POINT_STROKE_COLOR } from './mapStyle'

// Props of every <Layer> rendered, in order (the MapLibre boundary is mocked below).
type RenderedLayer = { id: string; paint?: Record<string, unknown>; layout?: Record<string, unknown> }
const layers = vi.hoisted(() => ({ rendered: [] as RenderedLayer[] }))

// jsdom has no WebGL: replace only the MapLibre boundary. ProjectMap, BasemapToggle and
// MapLegend stay real, so the map's own controls are exercised as rendered.
// The map exposes the style it was given (a URL, or "raster" for the satellite style object).
vi.mock('react-map-gl/maplibre', () => ({
  default: ({ children, mapStyle }: { children?: ReactNode; mapStyle: unknown }) => (
    <div data-testid="maplibre" data-map-style={typeof mapStyle === 'string' ? mapStyle : 'raster'}>{children}</div>
  ),
  NavigationControl: () => null,
  AttributionControl: () => null,
  Source: ({ children }: { children?: ReactNode }) => <>{children}</>,
  Layer: (props: RenderedLayer) => { layers.rendered.push(props); return null },
}))
vi.mock('maplibre-gl', () => ({ setWorkerUrl: vi.fn() }))
vi.mock('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url', () => ({ default: '' }))

/** The layers of the latest render, by id. */
function latestLayers() {
  const last = new Map<string, RenderedLayer>()
  for (const layer of layers.rendered) last.set(layer.id, layer)
  return last
}

function renderMap(theme: Theme = 'dark') {
  return render(<ProjectMap projects={[]} overlaps={[]} selectedId={null} onSelect={() => {}} focusedProject={null} theme={theme} />)
}

describe('ProjectMap top-left toolbar (#44)', () => {
  it('holds the basemap picker, Fit to data and the legend, in that order', () => {
    renderMap()
    const basemap = screen.getByRole('group', { name: 'Basemap' })
    const toolbar = basemap.parentElement!
    // #59: the picker is just the Satellite toggle; the theme toggle picks Dark Matter or Positron.
    expect(within(basemap).getAllByRole('button').map((b) => b.textContent)).toEqual(['Satellite'])

    const children = Array.from(toolbar.children)
    expect(children[0]).toBe(basemap)
    expect(children[1]).toBe(within(toolbar).getByRole('button', { name: 'Fit to data' }))
    expect(within(children[2] as HTMLElement).getByText('Legend')).toBeInTheDocument()
    expect(children).toHaveLength(3)
  })

  it('has no menu button: that lives in the top bar now', () => {
    renderMap()
    expect(screen.queryByRole('button', { name: /menu/i })).not.toBeInTheDocument()
  })
})

describe('ProjectMap follows the theme (#45)', () => {
  beforeEach(() => { layers.rendered = [] })

  const mapStyle = () => screen.getByTestId('maplibre').getAttribute('data-map-style')
  const picker = () => screen.getByRole('group', { name: 'Basemap' })
  const pickerLabels = () => within(picker()).getAllByRole('button').map((b) => b.textContent)
  // #47 added 'project-points-low-ring' (the dark ring around low-confidence points on the light
  // basemap, hidden on the others), under the points so their own stroke draws on top of it.
  const ALL_LAYERS = ['project-casing', 'project-lines', 'project-lines-low', 'project-points-low-ring', 'project-points', 'overlap-casing', 'overlap-lines']

  it('in the dark theme, shows Dark Matter with the dark casing and offers only Satellite, off (#59)', () => {
    renderMap('dark')
    expect(mapStyle()).toBe(BASEMAPS.dark.style)
    expect(pickerLabels()).toEqual(['Satellite'])
    expect(within(picker()).getByRole('button', { name: 'Satellite' })).toHaveAttribute('aria-pressed', 'false')
    expect(latestLayers().get('project-casing')?.paint?.['line-color']).toBe(HALO_COLOR_DARK)
  })

  it('in the light theme, defaults to Positron with the dark casing and offers only Satellite, off (#59)', () => {
    renderMap('light')
    expect(mapStyle()).toBe('https://basemaps.cartocdn.com/gl/positron-gl-style/style.json')
    expect(pickerLabels()).toEqual(['Satellite'])
    expect(within(picker()).getByRole('button', { name: 'Satellite' })).toHaveAttribute('aria-pressed', 'false')
    expect(latestLayers().get('project-casing')?.paint?.['line-color']).toBe(HALO_COLOR_DARK)
    expect(latestLayers().get('overlap-casing')?.paint?.['line-color']).toBe(HALO_COLOR_DARK)
  })

  it('switching theme swaps the map style and keeps the project and overlap layers and the selection', () => {
    const props = { projects: [], overlaps: [], selectedId: 'OVL_3', onSelect: () => {}, focusedProject: null }
    const { rerender } = render(<ProjectMap {...props} theme="dark" />)
    expect(mapStyle()).toBe(BASEMAPS.dark.style)
    expect([...latestLayers().keys()]).toEqual(ALL_LAYERS)

    layers.rendered = []
    rerender(<ProjectMap {...props} theme="light" />)
    expect(mapStyle()).toBe(BASEMAPS.light.style)
    expect([...latestLayers().keys()]).toEqual(ALL_LAYERS)
    // The selected connector is still drawn as selected.
    expect(JSON.stringify(latestLayers().get('overlap-lines')?.paint?.['line-color'])).toContain('"OVL_3"')

    rerender(<ProjectMap {...props} theme="dark" />)
    expect(mapStyle()).toBe(BASEMAPS.dark.style)
  })

  it('keeps satellite when the theme changes, and returns to the theme\'s vector style from it', () => {
    const props = { projects: [], overlaps: [], selectedId: null, onSelect: () => {}, focusedProject: null }
    const { rerender } = render(<ProjectMap {...props} theme="dark" />)
    fireEvent.click(within(picker()).getByRole('button', { name: 'Satellite' }))
    expect(mapStyle()).toBe('raster')

    layers.rendered = []
    rerender(<ProjectMap {...props} theme="light" />)
    expect(mapStyle()).toBe('raster')
    expect(within(picker()).getByRole('button', { name: 'Satellite' })).toHaveAttribute('aria-pressed', 'true')
    expect(latestLayers().get('project-casing')?.paint?.['line-color']).toBe(HALO_COLOR_LIGHT)

    // #59: a second click on Satellite is the way back.
    fireEvent.click(within(picker()).getByRole('button', { name: 'Satellite' }))
    expect(mapStyle()).toBe(BASEMAPS.light.style)
  })

  it.each(['dark', 'light'] as const)('in the %s theme, Satellite toggles satellite on and back off to the theme\'s vector map (#59)', (theme) => {
    renderMap(theme)
    const satellite = within(picker()).getByRole('button', { name: 'Satellite' })
    expect(mapStyle()).toBe(BASEMAPS[theme].style)
    expect(satellite).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(satellite)
    expect(mapStyle()).toBe('raster')
    expect(satellite).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(satellite)
    expect(mapStyle()).toBe(BASEMAPS[theme].style)
    expect(satellite).toHaveAttribute('aria-pressed', 'false')
  })
})

describe('ProjectMap point outline follows the basemap (#47)', () => {
  beforeEach(() => { layers.rendered = [] })

  const picker = () => screen.getByRole('group', { name: 'Basemap' })
  /** The latest render's point outline: the confirmed point's circle-stroke-color, evaluated by MapLibre's own evaluator. */
  function confirmedPointStroke() {
    const value = latestLayers().get('project-points')?.paint?.['circle-stroke-color']
    const spec = (latest as unknown as Record<string, Record<string, never>>).paint_circle['circle-stroke-color']
    const feature = { type: 'Point' as const, properties: { utility: 'Georgia Power', location_confidence: 'confirmed' } }
    const result = normalizePropertyExpression(value as never, 'circle-stroke-color', spec).evaluate({ zoom: 8 }, feature)
    return (result as Color).toString()
  }
  const colorOf = (hex: string) => Color.parse(hex)!.toString()
  /** The low-confidence ring as rendered: its color, and whether MapLibre draws it. */
  function lowRing() {
    const ring = latestLayers().get('project-points-low-ring')
    return { color: ring?.paint?.['circle-stroke-color'], visibility: ring?.layout?.visibility }
  }

  it('outlines points white on Dark Matter, dark on Positron, and white on satellite, with the low-confidence ring only on Positron', () => {
    const props = { projects: [], overlaps: [], selectedId: null, onSelect: () => {}, focusedProject: null }
    const { rerender } = render(<ProjectMap {...props} theme="dark" />)
    expect(confirmedPointStroke()).toBe(colorOf(POINT_STROKE_COLOR))
    expect(lowRing().visibility).toBe('none')

    // Theme switch: Dark Matter -> Positron. No stale white outline.
    layers.rendered = []
    rerender(<ProjectMap {...props} theme="light" />)
    expect(confirmedPointStroke()).toBe(colorOf(HALO_COLOR_DARK))
    expect(confirmedPointStroke()).not.toBe(colorOf(POINT_STROKE_COLOR))
    expect(lowRing()).toEqual({ color: HALO_COLOR_DARK, visibility: 'visible' })

    // Basemap switch: Positron -> satellite -> Positron.
    layers.rendered = []
    fireEvent.click(within(picker()).getByRole('button', { name: 'Satellite' }))
    expect(confirmedPointStroke()).toBe(colorOf(POINT_STROKE_COLOR))
    expect(lowRing().visibility).toBe('none')

    layers.rendered = []
    fireEvent.click(within(picker()).getByRole('button', { name: 'Satellite' }))
    expect(confirmedPointStroke()).toBe(colorOf(HALO_COLOR_DARK))
    expect(lowRing()).toEqual({ color: HALO_COLOR_DARK, visibility: 'visible' })

    // And back to the dark theme: white again, ring hidden.
    layers.rendered = []
    rerender(<ProjectMap {...props} theme="dark" />)
    expect(confirmedPointStroke()).toBe(colorOf(POINT_STROKE_COLOR))
    expect(lowRing().visibility).toBe('none')
  })

  it('keeps white as the outline on Dark Matter and satellite (unchanged) and uses the one dark casing color on Positron', () => {
    expect(POINT_STROKE_COLOR).toBe('#ffffff')
    expect(HALO_COLOR_DARK).toBe('#020617')
    renderMap('light')
    // The outline on Positron is the same color as the line casing there.
    expect(latestLayers().get('project-casing')?.paint?.['line-color']).toBe(HALO_COLOR_DARK)
    expect(confirmedPointStroke()).toBe(colorOf(HALO_COLOR_DARK))
  })
})

describe('ProjectMap minimum-match slider (#54)', () => {
  const props = { projects: [], overlaps: [], selectedId: null, onSelect: () => {}, focusedProject: null, theme: 'dark' as Theme }
  const slider = () => screen.getByRole('slider', { name: 'Minimum match' })

  it('renders the slider, controlled by the minMatch it is given, and reports moves through onMinMatchChange', () => {
    const onMinMatchChange = vi.fn()
    const { rerender } = render(<ProjectMap {...props} minMatch={0.5} onMinMatchChange={onMinMatchChange} />)
    expect(slider()).toHaveValue('50')
    expect(screen.getByText('≥ 50% match')).toBeInTheDocument()
    fireEvent.input(slider(), { target: { value: '60' } })
    expect(onMinMatchChange).toHaveBeenCalledWith(0.6)
    rerender(<ProjectMap {...props} minMatch={0} onMinMatchChange={onMinMatchChange} />)
    expect(slider()).toHaveValue('0')
    expect(screen.getByText('All')).toBeInTheDocument()
  })

  it('puts the slider in its own floating control on the map, after the map (so above it) and outside the top-left toolbar', () => {
    render(<ProjectMap {...props} minMatch={0} onMinMatchChange={() => {}} />)
    const control = slider().closest('.match-slider') as HTMLElement
    expect(control).toHaveClass('map-control')
    const toolbar = screen.getByRole('group', { name: 'Basemap' }).parentElement!
    expect(toolbar).toHaveClass('map-toolbar')
    expect(toolbar).not.toContainElement(control)
    // A sibling of the toolbar, in the map's own box, after the MapLibre map (where the zoom buttons live).
    const map = screen.getByTestId('maplibre')
    expect(control.parentElement).toBe(toolbar.parentElement)
    expect(control.parentElement).toBe(map.parentElement)
    expect(map.compareDocumentPosition(control) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('shows no slider when nothing controls it', () => {
    render(<ProjectMap {...props} />)
    expect(screen.queryByRole('slider')).not.toBeInTheDocument()
  })
})