import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.tsx'
import { fetchOverlaps, fetchProjects, submitProjects } from './api'
import { apiExample, expectProject } from './test/apiExamples'
import { makeOverlaps } from './test/overlapFixtures'

vi.mock('./api', () => ({
  fetchProjects: vi.fn(),
  fetchOverlaps: vi.fn(),
  submitProjects: vi.fn(),
}))

// jsdom has no WebGL: replace the MapLibre map with a stub that exposes what it was given.
vi.mock('./components/ProjectMap', () => ({
  default: ({ projects, overlaps, selectedId }: { projects: unknown[]; overlaps: unknown[]; selectedId: string | null }) => (
    <div data-testid="project-map">
      {projects.length} projects, {overlaps.length} overlaps, selected {String(selectedId)}
    </div>
  ),
}))

// jsdom has no modal dialogs: open the upload <dialog> in place so its contents are accessible.
HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) { this.open = true }

async function chooseUpload(file: File) {
  await screen.findByRole('list', { name: /coordination opportunities/i })
  fireEvent.click(screen.getByRole('button', { name: 'Upload projects' }))
  fireEvent.change(screen.getByLabelText('Project CSV'), { target: { files: [file] } })
}

// The sidebar starts closed (map full screen); most tests exercise its contents, so open it.
const renderClosedApp = () => render(<App />)
// The menu button floats on the map, which appears once the data has loaded.
async function renderApp() {
  const result = renderClosedApp()
  fireEvent.click(await screen.findByRole('button', { name: 'Open menu' }))
  return result
}

function projectsExample() {
  const projects = apiExample('projects')
  if (!Array.isArray(projects)) throw new Error('projects example is not an array')
  projects.forEach((p) => expectProject(p))
  return projects
}

// One valid row placed on GPC_2 (0 mi from it, 5.65 mi from DESC_3) and one row with a bad latitude.
const UPLOAD_CSV = 'utility,project_name,lat_center,lon_center,in_service_date,est_cost_usd\n' +
  'Savannah Water,Water main replacement,32.352116,-81.175112,2026-06-01,2000000\n' +
  'Savannah Water,Bad row,abc,-81.1,2026-06-01,\n'

/** What the server holds once UPLOAD_CSV's valid row is saved: the project, and its pair ranked first. */
function savedUpload() {
  const gpc = projectsExample().find(p => p.project_id === 'GPC_2')!
  const stored = { ...gpc, project_id: 'SUB-abc-1', utility: 'Savannah Water', state: 'Unknown',
    project_name: 'Water main replacement', name_a: null, lat_a: null, lon_a: null, name_b: null,
    lat_b: null, lon_b: null, est_cost_usd: 2000000, location_confidence: 'low' as const }
  const pair = { ...makeOverlaps(1)[0], overlap_id: 'SUB:GPC_2|SUB-abc-1', rank: 1, score: 1,
    distance_mi: 0, time_gap_days: 0, project_a: gpc, project_b: stored, est_savings_usd: 100000 }
  return { stored, pair }
}

describe('App', () => {
  beforeEach(() => {
    vi.mocked(fetchProjects).mockReset().mockResolvedValue(projectsExample())
    vi.mocked(fetchOverlaps).mockReset().mockResolvedValue(makeOverlaps(6))
    vi.mocked(submitProjects).mockReset()
  })

  describe('sidebar toggle', () => {
    it('starts closed, so the map is the only thing on screen', async () => {
      renderClosedApp()
      expect(await screen.findByTestId('project-map')).toBeInTheDocument()
      expect(screen.queryByRole('complementary', { name: 'Workspace sidebar' })).not.toBeInTheDocument()
      expect(screen.queryByRole('list', { name: /coordination opportunities/i })).not.toBeInTheDocument()
      const toggle = screen.getByRole('button', { name: 'Open menu' })
      expect(toggle).toHaveAttribute('aria-expanded', 'false')
      expect(screen.getByRole('region', { name: 'Project map' }).parentElement).toHaveClass('sidebar-closed')
    })

    it('keeps the sidebar mounted so it can slide, but hides it from keyboard and screen readers while closed', async () => {
      const { container } = renderClosedApp()
      await screen.findByTestId('project-map')
      const sidebar = container.querySelector('#workspace-sidebar')!
      expect(sidebar).toHaveAttribute('aria-hidden', 'true')
      expect(sidebar).toHaveAttribute('inert')
      fireEvent.click(screen.getByRole('button', { name: 'Open menu' }))
      expect(sidebar).toHaveAttribute('aria-hidden', 'false')
      expect(sidebar).not.toHaveAttribute('inert')
      expect(screen.getByRole('complementary', { name: 'Workspace sidebar' })).toBe(sidebar)
    })

    it('floats the menu button on the map, not in the header', async () => {
      renderClosedApp()
      await screen.findByTestId('project-map')
      const toggle = screen.getByRole('button', { name: 'Open menu' })
      expect(within(screen.getByRole('region', { name: 'Project map' })).getByRole('button', { name: 'Open menu' })).toBe(toggle)
      expect(within(screen.getByRole('banner')).queryByRole('button', { name: /menu/i })).not.toBeInTheDocument()
      expect(toggle).toHaveTextContent('Open menu')
    })

    it('opens from the floating menu button and stays open until closed again', async () => {
      renderClosedApp()
      await screen.findByTestId('project-map')
      fireEvent.click(screen.getByRole('button', { name: 'Open menu' }))
      const sidebar = screen.getByRole('complementary', { name: 'Workspace sidebar' })
      expect(within(sidebar).getByText('SHARED GROUND')).toBeInTheDocument()
      expect(screen.getByRole('list', { name: /coordination opportunities/i })).toBeInTheDocument()
      const toggle = screen.getByRole('button', { name: 'Close menu' })
      expect(toggle).toHaveAttribute('aria-expanded', 'true')
      expect(toggle).toHaveAttribute('aria-controls', sidebar.id)
      expect(screen.getByRole('region', { name: 'Project map' }).parentElement).not.toHaveClass('sidebar-closed')

      // Using the sidebar doesn't close it.
      fireEvent.click(screen.getByRole('tab', { name: 'Projects' }))
      expect(screen.getByRole('complementary', { name: 'Workspace sidebar' })).toBeInTheDocument()

      fireEvent.click(toggle)
      expect(screen.queryByRole('complementary', { name: 'Workspace sidebar' })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Open menu' })).toHaveAttribute('aria-expanded', 'false')
      expect(screen.getByRole('region', { name: 'Project map' }).parentElement).toHaveClass('sidebar-closed')
    })

    it('keeps the sidebar state (tab, search) when it is closed and reopened', async () => {
      await renderApp()
      await screen.findByRole('list', { name: /coordination opportunities/i })
      fireEvent.click(screen.getByRole('tab', { name: 'Projects' }))
      fireEvent.change(screen.getByRole('textbox', { name: 'Search workspace' }), { target: { value: 'GA' } })
      fireEvent.click(screen.getByRole('button', { name: 'Close menu' }))
      fireEvent.click(screen.getByRole('button', { name: 'Open menu' }))
      expect(screen.getByRole('tab', { name: 'Projects' })).toHaveAttribute('aria-selected', 'true')
      expect(screen.getByRole('textbox', { name: 'Search workspace' })).toHaveValue('GA')
    })
  })

  it('renders the Relay heading', () => {
    renderClosedApp()
    expect(screen.getByRole('heading', { level: 1, name: 'Relay' })).toBeInTheDocument()
  })

  it('shows the Relay logo next to the heading, decorative so the name is read once', () => {
    renderClosedApp()
    const heading = screen.getByRole('heading', { level: 1, name: 'Relay' })
    const logo = heading.parentElement?.querySelector('img')
    expect(logo).toHaveAttribute('src', '/relay-icon.svg')
    expect(logo).toHaveAttribute('alt', '')
  })

  describe('top bar', () => {
    it('lays out three regions in order left / center / right, with the brand in the center', async () => {
      renderClosedApp()
      await screen.findByTestId('project-map')
      const regions = Array.from(screen.getByRole('banner').children)
      expect(regions).toHaveLength(3)
      const [left, center, right] = regions

      // Left is reserved: an empty plain div, nothing focusable.
      expect(left.tagName).toBe('DIV')
      expect(left).toBeEmptyDOMElement()

      expect(within(center as HTMLElement).getByRole('heading', { level: 1, name: 'Relay' })).toBeInTheDocument()
      expect(center.querySelector('img')).toHaveAttribute('src', '/relay-icon.svg')
      // The logo comes before the wordmark.
      const img = center.querySelector('img')!
      expect(img.compareDocumentPosition(within(center as HTMLElement).getByRole('heading', { level: 1 })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

      expect(within(right as HTMLElement).getByRole('button', { name: 'Upload projects' })).toBeEnabled()
      expect(within(center as HTMLElement).queryByRole('button')).not.toBeInTheDocument()
    })

    it('keeps the upload button in the right region, disabled until the data is ready', async () => {
      renderClosedApp()
      const right = screen.getByRole('banner').children[2] as HTMLElement
      expect(within(right).getByRole('button', { name: 'Upload projects' })).toBeDisabled()
      await screen.findByTestId('project-map')
      expect(within(right).getByRole('button', { name: 'Upload projects' })).toBeEnabled()
    })

    it('no longer shows the workspace title, subtitle or shared-workspace badge', async () => {
      renderClosedApp()
      await screen.findByTestId('project-map')
      expect(screen.queryByText('Planning workspace')).not.toBeInTheDocument()
      expect(screen.queryByText('Regional coordination')).not.toBeInTheDocument()
      expect(screen.queryByText('Shared workspace')).not.toBeInTheDocument()
      expect(screen.queryByText('Local session')).not.toBeInTheDocument()
    })
  })

  it('renders one list item per overlap (6) from the API, rank 1 first, next to the map', async () => {
    await renderApp()

    const list = await screen.findByRole('list', { name: /coordination opportunities/i })
    const items = within(list).getAllByRole('button')
    expect(items).toHaveLength(6)
    expect(items[0]).toHaveTextContent('SC line 1')
    expect(items[5]).toHaveTextContent('SC line 6')
    expect(screen.getByTestId('project-map')).toHaveTextContent('2 projects, 6 overlaps')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows each opportunity card\'s score as a whole-number percentage', async () => {
    // Descending, as the API ranks them (the list re-sorts by score, so rank order = score order).
    const scores = [1, 0.8311, 0.7055, 0.5, 0.25, 0]
    vi.mocked(fetchOverlaps).mockResolvedValue(makeOverlaps(6).map((o, i) => ({ ...o, score: scores[i] })))
    await renderApp()

    const items = within(await screen.findByRole('list', { name: /coordination opportunities/i })).getAllByRole('button')
    expect(items).toHaveLength(6)
    // Anchored on the separator so "0%" can't pass by matching inside "100%".
    const expected = ['100%', '83%', '71%', '50%', '25%', '0%']
    items.forEach((item, i) => expect(item).toHaveTextContent(`· ${expected[i]} match`))
    expect(items[1]).not.toHaveTextContent('0.83')
  })

  it('selecting a list item marks it and passes the selection to the map', async () => {
    await renderApp()

    const item = await screen.findByRole('button', { name: /SC line 4/ })
    fireEvent.click(item)
    expect(await screen.findByRole('button', { name: /SC line 4/, pressed: true })).toBeInTheDocument()
    expect(screen.getByTestId('project-map')).toHaveTextContent('selected OVL_4')
  })

  it('selecting an overlap in the ranked list opens its detail panel; closing hides it', async () => {
    await renderApp()
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
    renderClosedApp() // no data, so no map and no menu button to open

    const alert = await screen.findByRole('alert')
    expect(alert).toBeVisible()
    expect(alert).toHaveTextContent('GET http://api/overlaps failed with status 500')
    expect(screen.queryByTestId('project-map')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Upload projects' })).toBeDisabled()
    expect(screen.queryByRole('list', { name: /coordination opportunities/i })).not.toBeInTheDocument()
  })

  it('searches opportunities and resets search when changing data tabs', async () => {
    await renderApp()
    await screen.findByRole('list', { name: /coordination opportunities/i })
    fireEvent.change(screen.getByRole('textbox', { name: 'Search workspace' }), { target: { value: 'SC line 4' } })
    expect(within(screen.getByRole('list')).getAllByRole('button')).toHaveLength(1)
    fireEvent.click(screen.getByRole('tab', { name: 'Projects' }))
    expect(screen.getByRole('textbox', { name: 'Search workspace' })).toHaveValue('')
    expect(screen.getByRole('tab', { name: 'Projects' })).toHaveAttribute('aria-selected', 'true')
  })

  it('toggles utility layers in the map and opportunity list', async () => {
    await renderApp()
    await screen.findByRole('list', { name: /coordination opportunities/i })
    fireEvent.click(screen.getByRole('checkbox', { name: /Georgia Power/ }))
    expect(screen.getByTestId('project-map')).toHaveTextContent('1 projects, 0 overlaps')
    expect(screen.getByText('No matching pairs')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /Georgia Power/ }))
    expect(screen.getByTestId('project-map')).toHaveTextContent('2 projects, 6 overlaps')
  })

  it('uploads a CSV, saves only the valid rows for everyone, and shows the server\'s ranked pairs', async () => {
    const { stored, pair } = savedUpload()
    await renderApp()
    await chooseUpload(new File([UPLOAD_CSV], 'savannah-water.csv', { type: 'text/csv' }))
    const add = await screen.findByRole('button', { name: /Add 1 project & compare/ })
    expect(screen.getByText('lat_center is invalid')).toBeInTheDocument()

    // From here on the server holds the upload, so a reload returns it.
    vi.mocked(submitProjects).mockResolvedValue([stored])
    vi.mocked(fetchProjects).mockResolvedValue([...projectsExample(), stored])
    vi.mocked(fetchOverlaps).mockResolvedValue([pair, ...makeOverlaps(6).map(o => ({ ...o, rank: o.rank + 1 }))])
    fireEvent.click(add)

    expect(await screen.findByRole('status')).toHaveTextContent('1 proposal from savannah-water.csv saved for everyone. Comparisons updated.')
    expect(submitProjects).toHaveBeenCalledTimes(1)
    const [[sent]] = vi.mocked(submitProjects).mock.calls
    expect(sent).toHaveLength(1)
    expect(sent[0]).toMatchObject({ utility: 'Savannah Water', project_name: 'Water main replacement', state: 'Unknown',
      lat_center: 32.352116, lon_center: -81.175112, in_service_date: '2026-06-01', est_cost_usd: 2000000 })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    expect(screen.getByTestId('project-map')).toHaveTextContent('3 projects, 7 overlaps')
    const items = within(screen.getByRole('list', { name: /coordination opportunities/i })).getAllByRole('button')
    expect(items).toHaveLength(7)
    expect(items[0]).toHaveTextContent('Water main replacement')
    expect(items[0]).toHaveTextContent('0.0 mi apart')
    expect(items.filter(item => within(item).queryByText('Uploaded'))).toHaveLength(1)

    fireEvent.click(screen.getByRole('tab', { name: /Uploads/ }))
    expect(screen.getByText('1 mapped · 1 flagged')).toBeInTheDocument()
    expect(screen.getByText('1 uploaded projects')).toBeInTheDocument()
    // Saved for everyone, so there is no per-tab "remove" any more.
    expect(screen.queryByRole('button', { name: 'Remove upload' })).not.toBeInTheDocument()
  })

  it('keeps the dialog open with the server\'s reason when an upload is refused, and changes nothing', async () => {
    await renderApp()
    await chooseUpload(new File([UPLOAD_CSV], 'savannah-water.csv', { type: 'text/csv' }))
    vi.mocked(submitProjects).mockRejectedValue(new Error("project 1 ('Water main replacement' by 'Savannah Water') already exists"))
    fireEvent.click(await screen.findByRole('button', { name: /Add 1 project & compare/ }))

    expect(await screen.findByRole('alert')).toHaveTextContent('already exists')
    expect(screen.getByRole('button', { name: /Add 1 project & compare/ })).toBeEnabled()
    expect(fetchOverlaps).toHaveBeenCalledTimes(1) // the initial load only: no refresh
    expect(screen.getByTestId('project-map')).toHaveTextContent('2 projects, 6 overlaps')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('shows projects other people uploaded earlier as soon as the workspace loads', async () => {
    const { stored, pair } = savedUpload()
    vi.mocked(fetchProjects).mockResolvedValue([...projectsExample(), stored])
    vi.mocked(fetchOverlaps).mockResolvedValue([pair, ...makeOverlaps(6).map(o => ({ ...o, rank: o.rank + 1 }))])
    await renderApp()

    expect(await screen.findByTestId('project-map')).toHaveTextContent('3 projects, 7 overlaps')
    expect(screen.getByText('Published plans + uploaded proposals')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /Uploads/ }))
    expect(screen.getByText('1 uploaded projects')).toBeInTheDocument()
    expect(screen.queryByText('Your plans belong here.')).not.toBeInTheDocument()
  })

  it('rejects a non-CSV upload with an alert and adds nothing', async () => {
    await renderApp()
    await chooseUpload(new File(['%PDF'], 'plan.pdf', { type: 'application/pdf' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Choose a CSV spreadsheet')
    expect(screen.queryByRole('button', { name: /& compare/ })).not.toBeInTheDocument()
    expect(screen.getByTestId('project-map')).toHaveTextContent('2 projects, 6 overlaps')
  })

  describe('opportunity sort', () => {
    // OVL_n has rank n. Every sort key orders these differently from rank order.
    //                  rank:   1        2       3        4        5
    const SCORES = [0.9, 0.8, 0.6, 0.5, 0.3]
    const DISTANCES = [9.5, 2.25, 14.0, 0.5, 6.75]
    const GAPS = [400, 20, 90, 700, 5]
    const SAVINGS = [null, 120000, 1500000, null, 709900]

    function sortFixture() {
      return makeOverlaps(5).map((o, i) => ({
        ...o, score: SCORES[i], distance_mi: DISTANCES[i], time_gap_days: GAPS[i], est_savings_usd: SAVINGS[i],
      }))
    }

    async function cards() {
      return within(await screen.findByRole('list', { name: /coordination opportunities/i })).getAllByRole('button')
    }
    const cardNames = (items: HTMLElement[]) => items.map(item => within(item).getByText(/^SC line \d$/).textContent)
    const sortSelect = () => screen.getByRole('combobox', { name: 'Sort by' })

    beforeEach(() => { vi.mocked(fetchOverlaps).mockResolvedValue(sortFixture()) })

    it('renders a "Sort by" control with exactly the four options, defaulting to Score', async () => {
      await renderApp()
      await cards()
      const select = sortSelect()
      expect(within(select).getAllByRole('option').map(o => o.textContent)).toEqual([
        'Score % (best first)', 'Distance (closest first)', 'Time gap (shortest first)', 'Est. savings (highest first)',
      ])
      expect(select).toHaveValue('score')
      expect(select).toHaveDisplayValue('Score % (best first)')
      // It takes the old caption's place; the pair count stays.
      expect(screen.queryByText('Ranked by proximity & timing')).not.toBeInTheDocument()
      expect(screen.getByText('5 nearby pairs')).toBeInTheDocument()
      expect(cardNames(await cards())).toEqual(['SC line 1', 'SC line 2', 'SC line 3', 'SC line 4', 'SC line 5'])
    })

    it('reorders the cards closest first when Distance is chosen, and shows the choice', async () => {
      await renderApp()
      await cards()
      fireEvent.change(sortSelect(), { target: { value: 'distance' } })
      expect(sortSelect()).toHaveDisplayValue('Distance (closest first)')
      // 0.5 (4), 2.25 (2), 6.75 (5), 9.5 (1), 14.0 (3)
      const items = await cards()
      expect(cardNames(items)).toEqual(['SC line 4', 'SC line 2', 'SC line 5', 'SC line 1', 'SC line 3'])
      // The badge keeps the score rank, so #01 is still identifiable.
      expect(items[3]).toHaveTextContent('#01 ·')
    })

    it('reorders the cards by savings, highest first, with no-estimate pairs last', async () => {
      await renderApp()
      await cards()
      fireEvent.change(sortSelect(), { target: { value: 'savings' } })
      expect(sortSelect()).toHaveDisplayValue('Est. savings (highest first)')
      const items = await cards()
      expect(cardNames(items)).toEqual(['SC line 3', 'SC line 5', 'SC line 2', 'SC line 1', 'SC line 4'])
      expect(within(items[3]).getByText('No estimate')).toBeInTheDocument()
      expect(within(items[4]).getByText('No estimate')).toBeInTheDocument()
    })

    it('reorders the cards shortest gap first when Time gap is chosen', async () => {
      await renderApp()
      await cards()
      fireEvent.change(sortSelect(), { target: { value: 'time_gap' } })
      // 5 (5), 20 (2), 90 (3), 400 (1), 700 (4)
      expect(cardNames(await cards())).toEqual(['SC line 5', 'SC line 2', 'SC line 3', 'SC line 1', 'SC line 4'])
    })

    it('composes with the search filter: only matching cards, in the chosen order', async () => {
      const overlaps = sortFixture().map((o, i) => ({
        ...o, project_b: { ...o.project_b, project_name: i % 2 === 0 ? `Match line ${i + 1}` : `Other line ${i + 1}` },
      }))
      vi.mocked(fetchOverlaps).mockResolvedValue(overlaps)
      await renderApp()
      await cards()
      fireEvent.change(screen.getByRole('textbox', { name: 'Search workspace' }), { target: { value: 'Match' } })
      fireEvent.change(sortSelect(), { target: { value: 'distance' } })
      // Matches are ranks 1, 3, 5 -> by distance: 6.75 (5), 9.5 (1), 14.0 (3)
      expect(cardNames(await cards())).toEqual(['SC line 5', 'SC line 1', 'SC line 3'])
      expect(screen.getByText('3 nearby pairs')).toBeInTheDocument()
    })

    it('shows distance, time gap, score % and est. savings (or "No estimate") on each card', async () => {
      await renderApp()
      const items = await cards()
      // Rank 3: 14.0 mi, 90 days, 60%, $1.5M
      expect(items[2]).toHaveTextContent('14.0 mi apart')
      expect(items[2]).toHaveTextContent('90 days apart in service')
      expect(items[2]).toHaveTextContent('· 60% match')
      expect(within(items[2]).getByText('$1.5M est. savings')).toHaveAttribute('title', '$1,500,000 est. savings')
      expect(within(items[2]).queryByText('No estimate')).not.toBeInTheDocument()
      // Rank 1: no savings estimate
      expect(items[0]).toHaveTextContent('9.5 mi apart')
      expect(items[0]).toHaveTextContent('400 days apart in service')
      expect(items[0]).toHaveTextContent('· 90% match')
      expect(within(items[0]).getByText('No estimate')).toBeInTheDocument()
      expect(items[0]).not.toHaveTextContent('est. savings')
    })

    it('still selects a clicked card (aria-pressed) under every sort order', async () => {
      await renderApp()
      await cards()
      // The top card differs per order, so each click selects a pair that was not selected yet.
      const topCardByOrder = [['score', 'OVL_1'], ['distance', 'OVL_4'], ['time_gap', 'OVL_5'], ['savings', 'OVL_3']]
      for (const [key, overlapId] of topCardByOrder) {
        fireEvent.change(sortSelect(), { target: { value: key } })
        const items = await cards()
        const target = items[0]
        expect(target).toHaveTextContent(`SC line ${overlapId.slice(-1)}`)
        expect(target).toHaveAttribute('aria-pressed', 'false')
        fireEvent.click(target)
        expect(target).toHaveAttribute('aria-pressed', 'true')
        expect(items.filter(item => item.getAttribute('aria-pressed') === 'true')).toEqual([target])
        expect(screen.getByTestId('project-map')).toHaveTextContent(`selected ${overlapId}`)
      }
    })
  })

  describe('savings headline', () => {
    const SANTEE = 'Santee Cooper'

    // Adds a third utility so hiding one layer leaves a non-empty, non-trivial subset.
    function withThirdUtility() {
      const projects = projectsExample()
      const santee = { ...projects[0], project_id: 'SC_9', utility: SANTEE, project_name: 'Santee line 9' }
      const [a, b, c, d] = makeOverlaps(4)
      return {
        projects: [...projects, santee],
        overlaps: [
          { ...a, est_savings_usd: 1200000 }, // DESC–GPC
          { ...b, est_savings_usd: null }, // DESC–GPC, not estimated
          { ...c, project_b: santee, est_savings_usd: 300000 }, // DESC–Santee
          { ...d, project_b: santee, est_savings_usd: null }, // DESC–Santee, not estimated
        ],
      }
    }

    async function headline() {
      await screen.findByRole('list', { name: /coordination opportunities/i })
      return screen.getByRole('group', { name: 'Estimated savings' })
    }

    it('shows the total of known est_savings_usd and the pair count', async () => {
      const overlaps = makeOverlaps(3).map((o, i) => ({ ...o, est_savings_usd: [709900, 1200000, 300000][i] }))
      vi.mocked(fetchOverlaps).mockResolvedValue(overlaps)
      await renderApp()

      const group = await headline()
      expect(within(group).getByText('$2.2M')).toBeInTheDocument() // 709,900 + 1,200,000 + 300,000
      expect(group).toHaveAttribute('title', '$2,209,900 estimated across 3 pairs')
      expect(group).toHaveTextContent('est. savings · 3 pairs shown')
      expect(within(group).getByText('0 not estimated')).toBeInTheDocument()
    })

    it('excludes null savings from the total and counts them as not estimated', async () => {
      const { projects, overlaps } = withThirdUtility()
      vi.mocked(fetchProjects).mockResolvedValue(projects)
      vi.mocked(fetchOverlaps).mockResolvedValue(overlaps)
      await renderApp()

      const group = await headline()
      expect(within(group).getByText('$1.5M')).toBeInTheDocument()
      expect(group).toHaveAttribute('title', '$1,500,000 estimated across 2 pairs')
      expect(group).toHaveTextContent('4 pairs shown')
      expect(within(group).getByText('2 not estimated')).toBeInTheDocument()
    })

    it('recomputes the total and counts when a utility layer is hidden and shown again', async () => {
      const { projects, overlaps } = withThirdUtility()
      vi.mocked(fetchProjects).mockResolvedValue(projects)
      vi.mocked(fetchOverlaps).mockResolvedValue(overlaps)
      await renderApp()
      const group = await headline()

      fireEvent.click(screen.getByRole('checkbox', { name: /Georgia Power/ }))
      expect(within(group).getByText('$300K')).toBeInTheDocument()
      expect(group).toHaveTextContent('2 pairs shown')
      expect(within(group).getByText('1 not estimated')).toBeInTheDocument()
      expect(screen.getByTestId('project-map')).toHaveTextContent('2 overlaps')

      fireEvent.click(screen.getByRole('checkbox', { name: new RegExp(SANTEE) }))
      expect(within(group).getByText('$0')).toBeInTheDocument()
      expect(group).toHaveTextContent('0 pairs shown')
      expect(within(group).getByText('0 not estimated')).toBeInTheDocument()

      fireEvent.click(screen.getByRole('checkbox', { name: /Georgia Power/ }))
      fireEvent.click(screen.getByRole('checkbox', { name: new RegExp(SANTEE) }))
      expect(within(group).getByText('$1.5M')).toBeInTheDocument()
      expect(within(group).getByText('2 not estimated')).toBeInTheDocument()
    })

    it('adds the savings the server estimates for an uploaded pair once it is saved', async () => {
      const overlaps = makeOverlaps(6).map((o, i) => ({ ...o, est_savings_usd: i < 2 ? 500000 : null }))
      vi.mocked(fetchOverlaps).mockResolvedValue(overlaps)
      await renderApp()
      const group = await headline()
      expect(within(group).getByText('$1M')).toBeInTheDocument()
      expect(within(group).getByText('4 not estimated')).toBeInTheDocument()

      const { stored, pair } = savedUpload()
      await chooseUpload(new File([UPLOAD_CSV], 'savannah-water.csv', { type: 'text/csv' }))
      vi.mocked(submitProjects).mockResolvedValue([stored])
      vi.mocked(fetchProjects).mockResolvedValue([...projectsExample(), stored])
      vi.mocked(fetchOverlaps).mockResolvedValue([pair, ...overlaps.map(o => ({ ...o, rank: o.rank + 1 }))])
      fireEvent.click(await screen.findByRole('button', { name: /Add 1 project & compare/ }))
      await screen.findByRole('status')

      const after = screen.getByRole('group', { name: 'Estimated savings' })
      expect(within(after).getByText('$1.1M')).toBeInTheDocument() // 500,000 × 2 + 100,000
      expect(after).toHaveTextContent('7 pairs shown')
      expect(within(after).getByText('4 not estimated')).toBeInTheDocument()
    })
  })
})
