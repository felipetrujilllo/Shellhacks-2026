// The minimum-match slider (#54) end to end: App with the API mocked and the real ProjectMap and
// MatchSlider, only the MapLibre boundary replaced. A separate file from App.test.tsx because that
// file stubs ProjectMap (so it has no slider to move), and its existing tests stay as they are.
import type { ReactNode } from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.tsx'
import { fetchWorkspace } from './api'
import { makeOverlaps } from './test/overlapFixtures'
import type { Overlap, Project } from './types'

vi.mock('./api', () => ({ fetchWorkspace: vi.fn() }))

// jsdom has no WebGL. Each <Source> exposes the ids of the features it was given to draw.
vi.mock('react-map-gl/maplibre', () => ({
  default: ({ children }: { children?: ReactNode }) => <div data-testid="maplibre">{children}</div>,
  NavigationControl: () => null,
  AttributionControl: () => null,
  Source: ({ id, data, children }: { id: string; data: { features: { properties: { project_id?: string; overlap_id?: string } }[] }; children?: ReactNode }) => (
    <div data-testid={`source-${id}`} data-ids={data.features.map((f) => f.properties.overlap_id ?? f.properties.project_id).join(',')}>{children}</div>
  ),
  Layer: () => null,
}))
vi.mock('maplibre-gl', () => ({ setWorkerUrl: vi.fn() }))
vi.mock('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url', () => ({ default: '' }))

const SANTEE = 'Santee Cooper'

/**
 * Four pairs, each with its own two projects, plus LONE (in no pair). Rank order:
 *   OVL_1 95%  A1 – B1        9 mi   $1.0M
 *   OVL_2 72%  A2 – B2 Santee 2 mi   $500K
 *   OVL_3 50%  A3 – B3        5 mi   $200K
 *   OVL_4 30%  A4 – B4        1 mi   $300K
 */
function fixture() {
  const template = makeOverlaps(4)
  const scores = [0.95, 0.72, 0.5, 0.3]
  const distances = [9, 2, 5, 1]
  const savings = [1_000_000, 500_000, 200_000, 300_000]
  const overlaps: Overlap[] = template.map((o, i) => {
    const n = i + 1
    return {
      ...o, score: scores[i], distance_mi: distances[i], est_savings_usd: savings[i],
      project_a: { ...o.project_a, project_id: `A${n}` },
      project_b: { ...o.project_b, project_id: `B${n}`, ...(n === 2 ? { utility: SANTEE, project_name: 'Santee line 2' } : {}) },
    }
  })
  const lone: Project = { ...template[0].project_a, project_id: 'LONE', project_name: 'Lone line' }
  const projects = [...overlaps.flatMap((o) => [o.project_a, o.project_b]), lone]
  return { projects, overlaps }
}

let published: ReturnType<typeof fixture>

function memoryStorage(): Storage {
  const data = new Map<string, string>()
  return {
    get length() { return data.size },
    clear: () => data.clear(),
    getItem: (key: string) => data.get(key) ?? null,
    key: (i: number) => [...data.keys()][i] ?? null,
    removeItem: (key: string) => { data.delete(key) },
    setItem: (key: string, value: string) => { data.set(key, String(value)) },
  }
}

async function renderApp() {
  render(<App />)
  await screen.findByTestId('maplibre')
  fireEvent.click(screen.getByRole('button', { name: 'Open menu' }))
}

const slider = () => screen.getByRole('slider', { name: 'Minimum match' })
/** Drag the slider to a whole percent (0–90), as the browser reports it. */
const setMinMatch = (pct: number) => fireEvent.input(slider(), { target: { value: String(pct) } })
/** The ids the map was given to draw. */
const drawn = (source: 'projects' | 'overlaps') => (screen.getByTestId(`source-${source}`).dataset.ids ?? '').split(',').filter(Boolean)
const list = () => screen.getByRole('list', { name: /coordination opportunities/i })
/** The opportunity cards' pair numbers, in list order ("SC line 3" -> 3). */
const cardPairs = () => within(list()).queryAllByRole('button').map((b) => Number(b.textContent!.match(/SC line (\d)/)![1]))
const caption = () => screen.getByText(/^\d+ nearby pairs$/).textContent
const headline = () => screen.getByRole('group', { name: 'Estimated savings' })

describe('App minimum-match slider (#54)', () => {
  beforeEach(() => {
    published = fixture()
    vi.mocked(fetchWorkspace).mockReset().mockImplementation(async () => structuredClone(published))
    vi.stubGlobal('localStorage', memoryStorage())
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('at the default (All) passes every project and pair through, to the map and the list, as before', async () => {
    await renderApp()
    expect(slider()).toHaveValue('0')
    expect(within(slider().parentElement!).getByText('All')).toBeInTheDocument()
    expect(drawn('overlaps')).toEqual(['OVL_1', 'OVL_2', 'OVL_3', 'OVL_4'])
    expect(drawn('projects')).toEqual(['A1', 'B1', 'A2', 'B2', 'A3', 'B3', 'A4', 'B4', 'LONE']) // LONE too: nothing hidden
    expect(cardPairs()).toEqual([1, 2, 3, 4])
    expect(caption()).toBe('4 nearby pairs')
    expect(headline()).toHaveTextContent('$2M')
    expect(headline()).toHaveTextContent('4 pairs shown')
    expect(screen.getByText('9 mapped projects')).toBeInTheDocument()
  })

  it('at 50% removes the lower pairs from the map and the list, hides projects in no remaining pair, and updates the count and savings', async () => {
    await renderApp()
    setMinMatch(50)
    expect(slider()).toHaveValue('50')
    expect(within(slider().parentElement!).getByText('≥ 50% match')).toBeInTheDocument()
    // 50% is kept (inclusive); the 30% pair and its two projects go, and so does LONE.
    expect(drawn('overlaps')).toEqual(['OVL_1', 'OVL_2', 'OVL_3'])
    expect(drawn('projects')).toEqual(['A1', 'B1', 'A2', 'B2', 'A3', 'B3'])
    expect(cardPairs()).toEqual([1, 2, 3])
    expect(caption()).toBe('3 nearby pairs')
    expect(headline()).toHaveTextContent('$1.7M') // 1.0M + 500K + 200K
    expect(headline()).toHaveTextContent('3 pairs shown')
    expect(screen.getByText('6 mapped projects')).toBeInTheDocument()
    // The Projects tab lists the same projects the map draws.
    fireEvent.click(screen.getByRole('tab', { name: 'Projects' }))
    expect(screen.getByText('6 projects')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Lone line/ })).not.toBeInTheDocument()

    // Back to All: everything returns.
    setMinMatch(0)
    expect(drawn('projects')).toHaveLength(9)
    expect(screen.getByText('9 projects')).toBeInTheDocument()
  })

  it('works with the utility layers, search and sort: each applies on top of the others', async () => {
    await renderApp()
    fireEvent.click(screen.getByRole('checkbox', { name: new RegExp(SANTEE) }))
    expect(cardPairs()).toEqual([1, 3, 4])
    setMinMatch(50)
    // Santee's pair is hidden by its layer, the 30% pair by the minimum.
    expect(cardPairs()).toEqual([1, 3])
    expect(drawn('overlaps')).toEqual(['OVL_1', 'OVL_3'])
    fireEvent.change(screen.getByRole('combobox', { name: 'Sort by' }), { target: { value: 'distance' } })
    expect(cardPairs()).toEqual([3, 1]) // 5 mi, 9 mi
    fireEvent.change(screen.getByRole('textbox', { name: 'Search workspace' }), { target: { value: 'SC line 1' } })
    expect(cardPairs()).toEqual([1])
    expect(caption()).toBe('1 nearby pairs')
    // Search narrows the list only; the map keeps what the layers and the minimum show.
    expect(drawn('overlaps')).toEqual(['OVL_1', 'OVL_3'])

    fireEvent.change(screen.getByRole('textbox', { name: 'Search workspace' }), { target: { value: '' } })
    fireEvent.click(screen.getByRole('checkbox', { name: new RegExp(SANTEE) }))
    expect(cardPairs()).toEqual([2, 3, 1]) // Santee's 72% pair is back, still sorted by distance
    expect(slider()).toHaveValue('50') // the layer toggle leaves the minimum alone
  })

  it('closes the detail panel of a selected pair that falls below the minimum, and keeps one that passes', async () => {
    await renderApp()
    fireEvent.click(within(list()).getByRole('button', { name: /SC line 4/ }))
    expect(screen.getByRole('region', { name: /opportunity #4/i })).toBeInTheDocument()
    setMinMatch(50)
    expect(screen.queryByRole('region', { name: /opportunity #/i })).not.toBeInTheDocument()

    fireEvent.click(within(list()).getByRole('button', { name: /SC line 1/ }))
    setMinMatch(90)
    expect(screen.getByRole('region', { name: /opportunity #1/i })).toBeInTheDocument() // 95% passes 90%
  })

  it('closes the detail panel of a focused project that is in no remaining pair, and keeps one that is', async () => {
    await renderApp()
    fireEvent.click(screen.getByRole('tab', { name: 'Projects' }))
    fireEvent.click(screen.getByRole('button', { name: /Lone line/ }))
    expect(screen.getByText('PROJECT DETAILS')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: 'Lone line' })).toBeInTheDocument()
    setMinMatch(5) // LONE is in no pair, so any minimum hides it
    expect(screen.queryByText('PROJECT DETAILS')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /SC line 1/ }))
    setMinMatch(90)
    expect(screen.getByRole('heading', { level: 3, name: 'SC line 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /SC line 1/ })).toHaveClass('active')
  })

  it('shows a clear empty state when no pair reaches the minimum, and an empty map', async () => {
    published.overlaps[0].score = 0.88 // now nothing reaches 90%
    await renderApp()
    setMinMatch(90)
    expect(screen.getByText('No pairs at ≥ 90% match; lower the minimum')).toBeInTheDocument()
    expect(screen.queryByText('No matching pairs')).not.toBeInTheDocument()
    expect(cardPairs()).toEqual([])
    expect(caption()).toBe('0 nearby pairs')
    expect(drawn('overlaps')).toEqual([])
    expect(drawn('projects')).toEqual([])
    expect(headline()).toHaveTextContent('$0')
    expect(headline()).toHaveTextContent('0 pairs shown')
    fireEvent.click(screen.getByRole('tab', { name: 'Projects' }))
    expect(screen.getByText('No projects in pairs at ≥ 90% match; lower the minimum.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Opportunities' }))
    setMinMatch(85)
    expect(cardPairs()).toEqual([1])
    expect(screen.queryByText(/^No pairs at/)).not.toBeInTheDocument()
  })

  it('keeps the usual empty state when the utility layers, not the minimum, leave no pairs', async () => {
    await renderApp()
    setMinMatch(50)
    fireEvent.click(screen.getByRole('checkbox', { name: /Georgia Power/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: new RegExp(SANTEE) }))
    expect(screen.getByText('No matching pairs')).toBeInTheDocument()
    expect(screen.queryByText(/^No pairs at/)).not.toBeInTheDocument()
  })
})
