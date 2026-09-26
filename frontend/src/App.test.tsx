import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.tsx'
import { fetchOverlaps, fetchProjects } from './api'
import { apiExample, expectProject } from './test/apiExamples'
import { makeOverlaps } from './test/overlapFixtures'

vi.mock('./api', () => ({
  fetchProjects: vi.fn(),
  fetchOverlaps: vi.fn(),
}))

// jsdom has no WebGL: replace the MapLibre map with a stub that exposes what it was given.
vi.mock('./components/ProjectMap', () => ({
  default: ({ projects, overlaps, selectedId }: { projects: unknown[]; overlaps: unknown[]; selectedId: string | null }) => (
    <div data-testid="project-map">
      {projects.length} projects, {overlaps.length} overlaps, selected {String(selectedId)}
    </div>
  ),
}))

function projectsExample() {
  const projects = apiExample('projects')
  if (!Array.isArray(projects)) throw new Error('projects example is not an array')
  projects.forEach((p) => expectProject(p))
  return projects
}

describe('App', () => {
  beforeEach(() => {
    vi.mocked(fetchProjects).mockReset().mockResolvedValue(projectsExample())
    vi.mocked(fetchOverlaps).mockReset().mockResolvedValue(makeOverlaps(6))
  })

  it('renders the GridWatch heading', () => {
    render(<App />)
    expect(screen.getByRole('heading', { level: 1, name: 'GridWatch' })).toBeInTheDocument()
  })

  it('renders one list item per overlap (6) from the API, rank 1 first, next to the map', async () => {
    render(<App />)

    const list = await screen.findByRole('list', { name: /coordination opportunities/i })
    const items = within(list).getAllByRole('button')
    expect(items).toHaveLength(6)
    expect(items[0]).toHaveTextContent('SC line 1')
    expect(items[5]).toHaveTextContent('SC line 6')
    expect(screen.getByTestId('project-map')).toHaveTextContent('2 projects, 6 overlaps')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('selecting a list item marks it and passes the selection to the map', async () => {
    render(<App />)

    const item = await screen.findByRole('button', { name: /SC line 4/ })
    fireEvent.click(item)
    expect(await screen.findByRole('button', { name: /SC line 4/, pressed: true })).toBeInTheDocument()
    expect(screen.getByTestId('project-map')).toHaveTextContent('selected OVL_4')
  })

  it('selecting an overlap in the ranked list opens its detail panel; closing hides it', async () => {
    render(<App />)
    expect(screen.queryByRole('region', { name: /opportunity #/i })).not.toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: /SC line 4/ }))

    // makeOverlaps: OVL_4 is rank 4, SC/GA line 4, distance_mi 4.25, time_gap_days 40.
    const panel = await screen.findByRole('region', { name: /opportunity #4/i })
    expect(within(panel).getByText('SC line 4')).toBeInTheDocument()
    expect(within(panel).getByText('GA line 4')).toBeInTheDocument()
    expect(within(panel).getByText('4.3 mi')).toBeInTheDocument()
    expect(within(panel).getByText('40 days')).toBeInTheDocument()
    expect(within(panel).queryByText('SC line 3')).not.toBeInTheDocument()

    fireEvent.click(within(panel).getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('region', { name: /opportunity #/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /SC line 4/ })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByTestId('project-map')).toHaveTextContent('selected null')
  })

  it('shows a visible error alert with the message when the API call fails', async () => {
    vi.mocked(fetchOverlaps).mockRejectedValue(new Error('GET http://api/overlaps failed with status 500'))
    render(<App />)

    const alert = await screen.findByRole('alert')
    expect(alert).toBeVisible()
    expect(alert).toHaveTextContent('GET http://api/overlaps failed with status 500')
    expect(screen.queryByTestId('project-map')).not.toBeInTheDocument()
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })
})
