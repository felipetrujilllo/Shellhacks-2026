import { render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import ProjectMap from './ProjectMap'

// jsdom has no WebGL: replace only the MapLibre boundary. ProjectMap, BasemapToggle and
// MapLegend stay real, so the map's own controls are exercised as rendered.
vi.mock('react-map-gl/maplibre', () => ({
  default: ({ children }: { children?: ReactNode }) => <div data-testid="maplibre">{children}</div>,
  NavigationControl: () => null,
  AttributionControl: () => null,
  Source: () => null,
  Layer: () => null,
}))
vi.mock('maplibre-gl', () => ({ setWorkerUrl: vi.fn() }))
vi.mock('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url', () => ({ default: '' }))

function renderMap() {
  return render(<ProjectMap projects={[]} overlaps={[]} selectedId={null} onSelect={() => {}} focusedProject={null} />)
}

describe('ProjectMap top-left toolbar (#44)', () => {
  it('holds the basemap picker, Fit to data and the legend, in that order', () => {
    renderMap()
    const basemap = screen.getByRole('group', { name: 'Basemap' })
    const toolbar = basemap.parentElement!
    expect(within(basemap).getByRole('button', { name: /dark/i })).toBeInTheDocument()
    expect(within(basemap).getByRole('button', { name: /satellite/i })).toBeInTheDocument()

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
