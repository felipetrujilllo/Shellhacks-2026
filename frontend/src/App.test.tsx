import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.tsx'
import { fetchWorkspace } from './api'
import { apiExample, expectProject } from './test/apiExamples'
import { makeOverlaps } from './test/overlapFixtures'
import type { Overlap, Project, Workspace } from './types'
import { THEME_STORAGE_KEY } from './theme'
import { UNREADABLE_UPLOADS, UPLOAD_FILES_STORAGE_KEY, UPLOADS_STORAGE_KEY } from './uploadCache'

vi.mock('./api', () => ({
  fetchWorkspace: vi.fn(),
}))

// jsdom has no WebGL: replace the MapLibre map with a stub that exposes what it was given.
vi.mock('./components/ProjectMap', () => ({
  // Its Dark/Light basemap buttons call onThemeChange (ProjectMap.test.tsx checks the real picker).
  default: ({ projects, overlaps, selectedId, theme, onThemeChange }: { projects: unknown[]; overlaps: unknown[]; selectedId: string | null; theme: string; onThemeChange: (theme: 'dark' | 'light') => void }) => (
    <div data-testid="project-map" data-theme={theme}>
      {projects.length} projects, {overlaps.length} overlaps, selected {String(selectedId)}
      <button type="button" onClick={() => onThemeChange('dark')}>Map: Dark</button>
      <button type="button" onClick={() => onThemeChange('light')}>Map: Light</button>
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
async function renderApp() {
  const result = renderClosedApp()
  // The menu button is in the top bar but stays disabled until the data (and so the sidebar) is ready.
  await screen.findByTestId('project-map')
  fireEvent.click(screen.getByRole('button', { name: 'Open menu' }))
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

const uploadFile = () => new File([UPLOAD_CSV], 'savannah-water.csv', { type: 'text/csv' })

// What the fake server publishes; a test may replace either list before rendering.
let published: { projects: Project[]; overlaps: Overlap[] }

/**
 * POST /workspace in miniature (the real one: backend/app/routes.py): the published plans plus
 * each upload served as SUB-<client id> with 'low' confidence, and paired with GPC_2 at 0 mi,
 * ranked above the published pairs. Stateless, like the server: only what is sent comes back.
 */
function fakeWorkspace(uploads: Project[]): Workspace {
  const gpc = published.projects.find(p => p.project_id === 'GPC_2')!
  const served = uploads.map(u => ({ ...u, project_id: `SUB-${u.project_id}`, location_confidence: 'low' as const }))
  const pairs = served.map((p, i) => ({ ...makeOverlaps(1)[0], overlap_id: `SUB:GPC_2|${p.project_id}`, rank: i + 1,
    score: 1, distance_mi: 0, time_gap_days: 0, project_a: gpc, project_b: p,
    est_savings_usd: p.est_cost_usd === null ? null : p.est_cost_usd / 20 }))
  return { projects: [...published.projects, ...served],
    overlaps: [...pairs, ...published.overlaps.map(o => ({ ...o, rank: o.rank + pairs.length }))] }
}

/** An upload as this browser keeps it (client id, as reviewCsv builds it). */
function clientUpload(overrides: Partial<Project> = {}): Project {
  return { project_id: 'b1-1', utility: 'Savannah Water', state: 'Unknown', project_name: 'Water main replacement',
    name_a: null, lat_a: null, lon_a: null, name_b: null, lat_b: null, lon_b: null,
    lat_center: 32.352116, lon_center: -81.175112, in_service_date: '2026-06-01', est_cost_usd: 2000000,
    location_confidence: 'low', ...overrides }
}

/** A fresh in-memory localStorage: one per test, so no test sees another's uploads. */
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

/** A browser that refuses site data (private window, blocked storage): every call throws. */
function blockedStorage(): Storage {
  const refuse = () => { throw new DOMException('The operation is insecure.', 'SecurityError') }
  return { get length() { return refuse() }, clear: refuse, getItem: refuse, key: refuse, removeItem: refuse, setItem: refuse }
}

let storage: Storage
const savedUploads = () => {
  const raw = storage.getItem(UPLOADS_STORAGE_KEY)
  return raw === null ? null : JSON.parse(raw) as Project[]
}
const sentUploads = (call: number) => vi.mocked(fetchWorkspace).mock.calls[call][0]
const savedUploadFiles = () => {
  const raw = storage.getItem(UPLOAD_FILES_STORAGE_KEY)
  return raw === null ? null : JSON.parse(raw) as Record<string, string>
}
/** The Uploads tab's cards (#57), in order. */
const uploadCardItems = () => within(screen.getByRole('list', { name: 'Your uploads' })).getAllByRole('listitem')

/** Picks UPLOAD_CSV in the dialog and adds its one valid row. */
async function importUpload() {
  await chooseUpload(uploadFile())
  fireEvent.click(await screen.findByRole('button', { name: /Add 1 project & compare/ }))
  await screen.findByRole('status')
}

describe('App', () => {
  beforeEach(() => {
    published = { projects: projectsExample(), overlaps: makeOverlaps(6) }
    vi.mocked(fetchWorkspace).mockReset().mockImplementation(async uploads => fakeWorkspace(uploads))
    storage = memoryStorage()
    vi.stubGlobal('localStorage', storage)
  })
  afterEach(() => { vi.unstubAllGlobals() })

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

    it('puts the menu button first in the top bar\'s left region, not on the map', async () => {
      renderClosedApp()
      await screen.findByTestId('project-map')
      const toggle = screen.getByRole('button', { name: 'Open menu' })
      const left = screen.getByRole('banner').children[0] as HTMLElement
      expect(left.firstElementChild).toBe(toggle)
      expect(within(screen.getByRole('region', { name: 'Project map' })).queryByRole('button', { name: /menu/i })).not.toBeInTheDocument()
      expect(toggle).toHaveAccessibleName('Open menu')
    })

    it('keeps the menu button disabled until the data, and so the sidebar, is ready', async () => {
      renderClosedApp()
      expect(screen.getByRole('button', { name: 'Open menu' })).toBeDisabled()
      await screen.findByTestId('project-map')
      expect(screen.getByRole('button', { name: 'Open menu' })).toBeEnabled()
    })

    it('shows an icon-only menu button: no visible text, but named "Open menu"/"Close menu" with aria-expanded', async () => {
      renderClosedApp()
      await screen.findByTestId('project-map')
      const toggle = screen.getByRole('button', { name: 'Open menu' })
      expect(toggle).toHaveAttribute('aria-label', 'Open menu')
      expect(toggle).toHaveAttribute('aria-expanded', 'false')
      expect(toggle).toHaveAttribute('aria-controls', 'workspace-sidebar')
      expect(toggle.textContent).toBe('')
      expect(toggle.children).toHaveLength(1)
      expect(toggle.firstElementChild?.tagName.toLowerCase()).toBe('svg')
      expect(toggle.firstElementChild).toHaveAttribute('aria-hidden', 'true')
      expect(screen.queryByText(/open menu|close menu/i)).not.toBeInTheDocument()

      fireEvent.click(toggle)
      expect(toggle).toHaveAccessibleName('Close menu')
      expect(screen.getByRole('button', { name: 'Close menu' })).toBe(toggle)
      expect(toggle).toHaveAttribute('aria-expanded', 'true')
      expect(toggle.textContent).toBe('')
      expect(screen.queryByText(/open menu|close menu/i)).not.toBeInTheDocument()

      fireEvent.click(toggle)
      expect(toggle).toHaveAccessibleName('Open menu')
      expect(toggle).toHaveAttribute('aria-expanded', 'false')
    })

    it('opens from the top bar menu button and stays open until closed again', async () => {
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

  it('shows the Relay wordmark logo as the heading, so its alt text is the name read once', () => {
    renderClosedApp()
    // The traced wordmark (gold R + ELAY) replaced the square icon + typed "Relay": the image IS the name now,
    // so it carries alt="Relay" inside the h1 instead of being decorative next to text.
    const heading = screen.getByRole('heading', { level: 1, name: 'Relay' })
    const logo = heading.querySelector('img')
    expect(logo).toHaveAttribute('src', '/relay-logo.svg')
    expect(logo).toHaveAttribute('alt', 'Relay')
    expect(heading.textContent).toBe('')
  })

  describe('top bar', () => {
    it('lays out three regions in order left / center / right, with the brand in the center', async () => {
      renderClosedApp()
      await screen.findByTestId('project-map')
      const regions = Array.from(screen.getByRole('banner').children)
      expect(regions).toHaveLength(3)
      const [left, center, right] = regions

      // Left holds only the icon-only menu button (#44).
      expect(left.tagName).toBe('DIV')
      expect(left.children).toHaveLength(1)
      expect(within(left as HTMLElement).getByRole('button', { name: 'Open menu' })).toBe(left.firstElementChild)

      expect(within(center as HTMLElement).getByRole('heading', { level: 1, name: 'Relay' })).toBeInTheDocument()
      // The wordmark logo is the heading itself (no separate icon + text any more).
      const img = center.querySelector('img')!
      expect(img).toHaveAttribute('src', '/relay-logo.svg')
      expect(within(center as HTMLElement).getByRole('heading', { level: 1 })).toContainElement(img)
      expect(center.querySelectorAll('img')).toHaveLength(1)

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

    it('has no theme toggle in the top bar: the right region holds only Upload projects, and the brand is alone in the center', async () => {
      renderClosedApp()
      await screen.findByTestId('project-map')
      const [left, center, right] = Array.from(screen.getByRole('banner').children) as HTMLElement[]
      expect(Array.from(right.children)).toEqual([within(right).getByRole('button', { name: 'Upload projects' })])
      const banner = screen.getByRole('banner')
      expect(within(banner).queryByRole('button', { name: /light theme|dark theme/i })).not.toBeInTheDocument()
      expect(within(left).getAllByRole('button').map(b => b.getAttribute('aria-label'))).toEqual(['Open menu'])
      expect(within(center).queryByRole('button')).not.toBeInTheDocument()
      expect(within(center).getByRole('heading', { level: 1, name: 'Relay' })).toBeInTheDocument()
    })

    it('the map\'s Light/Dark picks switch <html> to the light theme and back, remember it, and the map follows (#45)', async () => {
      renderClosedApp()
      await screen.findByTestId('project-map')
      expect(document.documentElement).not.toHaveAttribute('data-theme', 'light')
      expect(screen.getByTestId('project-map')).toHaveAttribute('data-theme', 'dark')
      try {
        fireEvent.click(screen.getByRole('button', { name: 'Map: Light' }))
        expect(document.documentElement).toHaveAttribute('data-theme', 'light')
        expect(storage.getItem(THEME_STORAGE_KEY)).toBe('light')
        expect(screen.getByTestId('project-map')).toHaveAttribute('data-theme', 'light')

        fireEvent.click(screen.getByRole('button', { name: 'Map: Dark' }))
        expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
        expect(storage.getItem(THEME_STORAGE_KEY)).toBe('dark')
        expect(screen.getByTestId('project-map')).toHaveAttribute('data-theme', 'dark')
      } finally {
        document.documentElement.removeAttribute('data-theme')
      }
    })

    it('starts in the light theme when the page already shows it, and the map\'s Dark pick switches back', async () => {
      document.documentElement.dataset.theme = 'light'
      try {
        renderClosedApp()
        await screen.findByTestId('project-map')
        expect(screen.getByTestId('project-map')).toHaveAttribute('data-theme', 'light')
        fireEvent.click(screen.getByRole('button', { name: 'Map: Dark' }))
        expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
        expect(screen.getByTestId('project-map')).toHaveAttribute('data-theme', 'dark')
      } finally {
        document.documentElement.removeAttribute('data-theme')
      }
    })

    it('still switches the theme when the browser refuses storage', async () => {
      vi.stubGlobal('localStorage', blockedStorage())
      renderClosedApp()
      await screen.findByTestId('project-map')
      try {
        expect(() => fireEvent.click(screen.getByRole('button', { name: 'Map: Light' }))).not.toThrow()
        expect(document.documentElement).toHaveAttribute('data-theme', 'light')
        expect(screen.getByTestId('project-map')).toHaveAttribute('data-theme', 'light')
      } finally {
        document.documentElement.removeAttribute('data-theme')
      }
    })

    it('keeps the selected pair when the theme changes (#45)', async () => {
      await renderApp()
      const list = await screen.findByRole('list', { name: /coordination opportunities/i })
      fireEvent.click(within(list).getAllByRole('button')[1])
      const selectedBefore = screen.getByTestId('project-map').textContent
      expect(selectedBefore).toMatch(/selected OVL_/)
      try {
        fireEvent.click(screen.getByRole('button', { name: 'Map: Light' }))
        expect(screen.getByTestId('project-map')).toHaveAttribute('data-theme', 'light')
        expect(screen.getByTestId('project-map').textContent).toBe(selectedBefore)
        expect(within(list).getAllByRole('button')[1]).toHaveAttribute('aria-pressed', 'true')
      } finally {
        document.documentElement.removeAttribute('data-theme')
      }
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
    // Descending with rank, so the cards (in rank order by default) show them in this order.
    const scores = [1, 0.8311, 0.7055, 0.5, 0.25, 0]
    published.overlaps = makeOverlaps(6).map((o, i) => ({ ...o, score: scores[i] }))
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
    vi.mocked(fetchWorkspace).mockRejectedValue(new Error('POST http://api/workspace failed with status 500'))
    renderClosedApp() // no data, so no map and no menu button to open

    const alert = await screen.findByRole('alert')
    expect(alert).toBeVisible()
    expect(alert).toHaveTextContent('POST http://api/workspace failed with status 500')
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

  it('uploads a CSV, sends only the valid rows with this browser\'s uploads, and shows the server\'s ranked pairs', async () => {
    await renderApp()
    await chooseUpload(uploadFile())
    const add = await screen.findByRole('button', { name: /Add 1 project & compare/ })
    expect(screen.getByText('lat_center is invalid')).toBeInTheDocument()
    fireEvent.click(add)

    expect(await screen.findByRole('status')).toHaveTextContent(
      '1 proposal from savannah-water.csv added. They stay in this browser and only you can see them. Comparisons updated.')
    expect(fetchWorkspace).toHaveBeenCalledTimes(2) // the load (no uploads yet), then the upload
    expect(sentUploads(0)).toEqual([])
    const sent = sentUploads(1)
    expect(sent).toHaveLength(1)
    expect(sent[0]).toMatchObject({ utility: 'Savannah Water', project_name: 'Water main replacement', state: 'Unknown',
      lat_center: 32.352116, lon_center: -81.175112, in_service_date: '2026-06-01', est_cost_usd: 2000000 })
    // The id the server serves as SUB-<id>: must fit its UPLOAD_ID_PATTERN (backend/app/schemas.py).
    expect(sent[0].project_id).toMatch(/^[A-Za-z0-9_-]{1,64}$/)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    expect(screen.getByTestId('project-map')).toHaveTextContent('3 projects, 7 overlaps')
    const items = within(screen.getByRole('list', { name: /coordination opportunities/i })).getAllByRole('button')
    expect(items).toHaveLength(7)
    expect(items[0]).toHaveTextContent('Water main replacement')
    expect(items[0]).toHaveTextContent('0.0 mi apart')
    expect(items.filter(item => within(item).queryByText('Uploaded'))).toHaveLength(1)

    fireEvent.click(screen.getByRole('tab', { name: /Uploads/ }))
    // One card for the file's one company (#57), no longer a file card plus a utility card.
    const cards = uploadCardItems()
    expect(cards).toHaveLength(1)
    expect(cards[0].querySelector('strong')).toHaveTextContent('Savannah Water')
    expect(within(cards[0]).getByText('savannah-water.csv')).toBeInTheDocument()
    expect(within(cards[0]).getByText('1 project mapped · 1 flagged')).toBeInTheDocument()
    expect(within(cards[0]).getByText('Row 3: lat_center is invalid')).toBeInTheDocument()
    expect(within(cards[0]).getByRole('button', { name: 'Remove Savannah Water uploads' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear my uploads' })).toBeInTheDocument()
  })

  it('keeps the accepted uploads in this browser\'s storage, under one versioned key', async () => {
    await renderApp()
    expect(savedUploads()).toBeNull()
    await importUpload()

    expect(UPLOADS_STORAGE_KEY).toBe('relay.uploads.v1')
    expect(savedUploads()).toEqual(sentUploads(1))
    expect(savedUploads()![0]).toMatchObject({ utility: 'Savannah Water', project_name: 'Water main replacement' })
  })

  it('adds a second file to the uploads already in this browser', async () => {
    storage.setItem(UPLOADS_STORAGE_KEY, JSON.stringify([clientUpload({ project_id: 'old-1', project_name: 'Older line' })]))
    await renderApp()
    await importUpload()

    expect(sentUploads(1).map(u => u.project_name)).toEqual(['Older line', 'Water main replacement'])
    expect(savedUploads()!.map(u => u.project_name)).toEqual(['Older line', 'Water main replacement'])
    expect(screen.getByTestId('project-map')).toHaveTextContent('4 projects, 8 overlaps')
  })

  it('re-sends the saved uploads on reload and shows them again, under the same ids', async () => {
    const first = await renderApp()
    await importUpload()
    const kept = savedUploads()!
    fireEvent.click(screen.getByRole('button', { name: /Water main replacement/ }))
    const selectedBefore = screen.getByTestId('project-map').textContent
    first.unmount()
    vi.mocked(fetchWorkspace).mockClear()

    await renderApp()
    expect(await screen.findByTestId('project-map')).toHaveTextContent('3 projects, 7 overlaps')
    expect(fetchWorkspace).toHaveBeenCalledTimes(1)
    expect(sentUploads(0)).toEqual(kept)
    const items = within(screen.getByRole('list', { name: /coordination opportunities/i })).getAllByRole('button')
    expect(items[0]).toHaveTextContent('Water main replacement')
    expect(within(items[0]).getByText('Uploaded')).toBeInTheDocument()
    // Same client id -> same served pair id, so selecting it again selects the same pair.
    fireEvent.click(items[0])
    expect(screen.getByTestId('project-map').textContent).toBe(selectedBefore)
    expect(selectedBefore).toContain(`selected SUB:GPC_2|SUB-${kept[0].project_id}`)
    fireEvent.click(screen.getByRole('tab', { name: /Uploads/ }))
    // The file name was saved next to the uploads (#57), so the card still names it after the reload.
    const [card] = uploadCardItems()
    expect(card.querySelector('strong')).toHaveTextContent('Savannah Water')
    expect(within(card).getByText('savannah-water.csv')).toBeInTheDocument()
    expect(within(card).getByText('1 project mapped')).toBeInTheDocument()
  })

  it('shows another browser (empty storage) none of these uploads', async () => {
    // This browser has an upload...
    storage.setItem(UPLOADS_STORAGE_KEY, JSON.stringify([clientUpload()]))
    // ...but a teammate's browser has its own, empty storage.
    vi.stubGlobal('localStorage', memoryStorage())
    await renderApp()

    expect(await screen.findByTestId('project-map')).toHaveTextContent('2 projects, 6 overlaps')
    expect(fetchWorkspace).toHaveBeenCalledTimes(1)
    expect(sentUploads(0)).toEqual([])
    expect(screen.queryByText('Uploaded')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /Uploads/ }))
    expect(screen.getByText('Your plans belong here.')).toBeInTheDocument()
    expect(screen.queryByText(/uploaded projects/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Clear my uploads' })).not.toBeInTheDocument()
  })

  it('"Clear my uploads" empties this browser\'s storage and the view', async () => {
    storage.setItem(UPLOADS_STORAGE_KEY, JSON.stringify([clientUpload()]))
    await renderApp()
    expect(await screen.findByTestId('project-map')).toHaveTextContent('3 projects, 7 overlaps')

    fireEvent.click(screen.getByRole('tab', { name: /Uploads/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Clear my uploads' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Your uploads were removed from this browser.')
    expect(storage.getItem(UPLOADS_STORAGE_KEY)).toBeNull()
    expect(sentUploads(1)).toEqual([])
    expect(screen.getByTestId('project-map')).toHaveTextContent('2 projects, 6 overlaps')
    expect(screen.getByText('Your plans belong here.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Clear my uploads' })).not.toBeInTheDocument()
  })

  it('removes one utility\'s uploads and keeps the others', async () => {
    const other = clientUpload({ project_id: 'b2-1', utility: 'Tidewater Grid Co.', project_name: 'River crossing' })
    storage.setItem(UPLOADS_STORAGE_KEY, JSON.stringify([clientUpload(), other]))
    await renderApp()
    expect(await screen.findByTestId('project-map')).toHaveTextContent('4 projects, 8 overlaps')

    fireEvent.click(screen.getByRole('tab', { name: /Uploads/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove Savannah Water uploads' }))

    expect(await screen.findByRole('status')).toHaveTextContent("Savannah Water's uploads were removed from this browser.")
    expect(savedUploads()).toEqual([other])
    expect(sentUploads(1)).toEqual([other])
    expect(screen.getByTestId('project-map')).toHaveTextContent('3 projects, 7 overlaps')
    expect(screen.queryByRole('button', { name: 'Remove Savannah Water uploads' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove Tidewater Grid Co. uploads' })).toBeInTheDocument()
  })

  describe('standing sample submissions (#62)', () => {
    // What the server serves every visitor: a sample project as an upload (SUB- id, low confidence)
    // and its pair with GPC_2, although this browser never uploaded it.
    beforeEach(() => {
      const gpc = published.projects.find(p => p.project_id === 'GPC_2')!
      const sample = clientUpload({ project_id: 'SUB-7302', utility: 'Tallapoosa Grid Partners', state: 'AL',
        project_name: 'Roanoke - Wedowee 115 kV Reconductor' })
      const pair = { ...makeOverlaps(1)[0], overlap_id: 'SUB:GPC_2|SUB-7302', rank: 1, project_a: gpc, project_b: sample }
      published = { projects: [...published.projects, sample],
        overlaps: [pair, ...published.overlaps.map(o => ({ ...o, rank: o.rank + 1 }))] }
    })

    it('tags the sample\'s pair "Uploaded" but keeps the sample out of the visitor\'s Uploads tab', async () => {
      await renderApp()

      const items = within(screen.getByRole('list', { name: /coordination opportunities/i })).getAllByRole('button')
      expect(items[0]).toHaveTextContent('Roanoke - Wedowee 115 kV Reconductor')
      expect(within(items[0]).getByText('Uploaded')).toBeInTheDocument()
      // Not "your uploads", and not "published" alone: the footer admits the samples are on the map.
      expect(screen.getByText('Published plans + sample uploads')).toBeInTheDocument()
      expect(screen.getByText('SC / GA + SAMPLE')).toBeInTheDocument()
      expect(screen.queryByText('Published utility plans')).not.toBeInTheDocument()
      expect(screen.getByRole('tab', { name: 'Uploads' })).toBeInTheDocument() // no count badge

      fireEvent.click(screen.getByRole('tab', { name: /Uploads/ }))
      expect(screen.getByText('Your plans belong here.')).toBeInTheDocument()
      expect(screen.queryByRole('list', { name: 'Your uploads' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Remove/ })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Clear my uploads' })).not.toBeInTheDocument()
      expect(screen.getByText('1 made-up sample project uploaded for the demo is also on the map, tagged Uploaded. It is not yours, so it is not listed here.')).toBeInTheDocument()
    })

    it('lists only the visitor\'s own uploads next to the samples, and "Clear my uploads" leaves the samples', async () => {
      storage.setItem(UPLOADS_STORAGE_KEY, JSON.stringify([clientUpload()]))
      await renderApp()
      expect(screen.getByTestId('project-map')).toHaveTextContent('4 projects, 8 overlaps')

      fireEvent.click(screen.getByRole('tab', { name: /Uploads/ }))
      expect(screen.getByRole('tab', { name: /Uploads/ })).toHaveTextContent(/^Uploads1$/) // the badge counts only the visitor's
      const cards = uploadCardItems()
      expect(cards).toHaveLength(1)
      expect(cards[0].querySelector('strong')).toHaveTextContent('Savannah Water')
      expect(screen.queryByRole('button', { name: 'Remove Tallapoosa Grid Partners uploads' })).not.toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'Clear my uploads' }))
      expect(await screen.findByRole('status')).toHaveTextContent('Your uploads were removed from this browser.')
      expect(sentUploads(1)).toEqual([])
      // The sample is the server's, not this browser's: it and its pair are still on the map.
      expect(screen.getByTestId('project-map')).toHaveTextContent('3 projects, 7 overlaps')
      expect(screen.getByText('Your plans belong here.')).toBeInTheDocument()
      expect(screen.getByText(/1 made-up sample project uploaded for the demo is also on the map/)).toBeInTheDocument()
    })
  })

  describe('upload cards: one per company (#57)', () => {
    const HEADER = 'utility,project_name,lat_center,lon_center,in_service_date,est_cost_usd\n'
    /** Picks `csv` as `filename` and adds its valid rows. */
    async function importCsv(filename: string, csv: string, add: RegExp) {
      await chooseUpload(new File([csv], filename, { type: 'text/csv' }))
      fireEvent.click(await screen.findByRole('button', { name: add }))
      await screen.findByText(`from ${filename} added`, { exact: false }) // this file's notice, not an earlier one
      fireEvent.click(screen.getByRole('tab', { name: /Uploads/ }))
    }

    it('gives each company in a two-company file its own card, each naming the file', async () => {
      await renderApp()
      await importCsv('two-companies.csv', HEADER +
        'Savannah Water,Water main replacement,32.352116,-81.175112,2026-06-01,2000000\n' +
        'Tidewater Grid Co.,River crossing,32.36,-81.2,2027-01-01,\n' +
        'Tidewater Grid Co.,Late line,32.36,-81.2,2027-13-01,\n', /Add 2 projects & compare/)

      const cards = uploadCardItems()
      expect(cards).toHaveLength(2)
      expect(cards.map(c => c.querySelector('strong')!.textContent)).toEqual(['Savannah Water', 'Tidewater Grid Co.'])
      for (const card of cards) expect(within(card).getByText('two-companies.csv')).toBeInTheDocument()
      expect(within(cards[0]).getByText('1 project mapped · 0 flagged')).toBeInTheDocument()
      expect(within(cards[0]).queryByText(/^Row /)).not.toBeInTheDocument()
      expect(within(cards[1]).getByText('1 project mapped · 1 flagged')).toBeInTheDocument()
      expect(within(cards[1]).getByText('Row 4: Use a valid in-service date (YYYY-MM-DD)')).toBeInTheDocument()
      expect(within(cards[0]).getByRole('button', { name: 'Remove Savannah Water uploads' })).toBeInTheDocument()
      expect(within(cards[1]).getByRole('button', { name: 'Remove Tidewater Grid Co. uploads' })).toBeInTheDocument()
    })

    it('lists one company\'s projects from two files on one card naming both files', async () => {
      await renderApp()
      await importUpload()
      await importCsv('savannah-2027.csv', HEADER + 'Savannah Water,Pump station feeder,32.36,-81.2,2027-01-01,\n', /Add 1 project & compare/)

      const cards = uploadCardItems()
      expect(cards).toHaveLength(1)
      expect(within(cards[0]).getByText('savannah-water.csv')).toBeInTheDocument()
      expect(within(cards[0]).getByText('savannah-2027.csv')).toBeInTheDocument()
      expect(within(cards[0]).getByText('2 projects mapped · 1 flagged')).toBeInTheDocument()
    })

    it('puts flagged rows with no company to go under on a card headed by the file name', async () => {
      await renderApp()
      await importCsv('mixed.csv', HEADER +
        'Savannah Water,Water main replacement,32.352116,-81.175112,2026-06-01,2000000\n' +
        ',Nameless line,32.36,-81.2,2027-01-01,\n' + // no company at all
        'Ghost Co,Only row,32.36,-81.2,someday,\n', // a company whose every row was flagged
      /Add 1 project & compare/)

      const cards = uploadCardItems()
      expect(cards).toHaveLength(2)
      expect(cards[0].querySelector('strong')).toHaveTextContent('Savannah Water')
      expect(within(cards[0]).getByText('1 project mapped · 0 flagged')).toBeInTheDocument()
      const fileCard = cards[1]
      expect(fileCard.querySelector('strong')).toHaveTextContent('mixed.csv')
      expect(within(fileCard).getByText('2 rows need attention')).toBeInTheDocument()
      expect(within(fileCard).getByText('Row 3: Utility is missing')).toBeInTheDocument()
      expect(within(fileCard).getByText('Row 4: Use a valid in-service date (YYYY-MM-DD)')).toBeInTheDocument()
      expect(within(fileCard).queryByRole('button')).not.toBeInTheDocument() // nothing of it was uploaded, so nothing to remove
    })

    it('saves the file name next to the uploads, never on the projects sent to POST /workspace', async () => {
      const first = await renderApp()
      await importUpload()
      const sent = sentUploads(1)
      expect(Object.keys(sent[0]).sort()).toEqual(Object.keys(clientUpload()).sort())
      expect(JSON.stringify(sent)).not.toContain('savannah-water.csv')
      expect(savedUploads()).toEqual(sent)
      expect(savedUploadFiles()).toEqual({ [sent[0].project_id]: 'savannah-water.csv' })

      first.unmount()
      vi.mocked(fetchWorkspace).mockClear()
      await renderApp()
      await screen.findByRole('list', { name: /coordination opportunities/i })
      expect(sentUploads(0)).toEqual(sent) // the reload sends the same projects, still without the file name
      expect(JSON.stringify(sentUploads(0))).not.toContain('savannah-water.csv')
    })

    it('falls back to "N uploaded projects" for uploads saved without a file name', async () => {
      storage.setItem(UPLOADS_STORAGE_KEY, JSON.stringify([clientUpload(), clientUpload({ project_id: 'b1-2', project_name: 'Second main' })]))
      await renderApp()
      await screen.findByRole('list', { name: /coordination opportunities/i })
      fireEvent.click(screen.getByRole('tab', { name: /Uploads/ }))

      const cards = uploadCardItems()
      expect(cards).toHaveLength(1)
      expect(cards[0].querySelector('strong')).toHaveTextContent('Savannah Water')
      expect(within(cards[0]).getByText('2 uploaded projects')).toBeInTheDocument()
      expect(cards[0]).not.toHaveTextContent(/mapped|\.csv/)
      expect(within(cards[0]).getByRole('button', { name: 'Remove Savannah Water uploads' })).toBeInTheDocument()
    })

    it('drops the removed company\'s file names on Remove, and every file name on Clear my uploads', async () => {
      const other = clientUpload({ project_id: 'b2-1', utility: 'Tidewater Grid Co.', project_name: 'River crossing' })
      storage.setItem(UPLOADS_STORAGE_KEY, JSON.stringify([clientUpload(), other]))
      storage.setItem(UPLOAD_FILES_STORAGE_KEY, JSON.stringify({ 'b1-1': 'savannah.csv', 'b2-1': 'tidewater.csv' }))
      await renderApp()
      await screen.findByRole('list', { name: /coordination opportunities/i })
      fireEvent.click(screen.getByRole('tab', { name: /Uploads/ }))
      expect(uploadCardItems().map(c => within(c).getByText(/\.csv$/).textContent)).toEqual(['savannah.csv', 'tidewater.csv'])

      fireEvent.click(screen.getByRole('button', { name: 'Remove Savannah Water uploads' }))
      await screen.findByRole('status')
      expect(savedUploads()).toEqual([other])
      expect(savedUploadFiles()).toEqual({ 'b2-1': 'tidewater.csv' })
      const cards = uploadCardItems()
      expect(cards).toHaveLength(1)
      expect(within(cards[0]).getByText('tidewater.csv')).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'Clear my uploads' }))
      await screen.findByText('Your uploads were removed from this browser.')
      expect(storage.getItem(UPLOADS_STORAGE_KEY)).toBeNull()
      expect(storage.getItem(UPLOAD_FILES_STORAGE_KEY)).toBeNull()
      expect(screen.getByText('Your plans belong here.')).toBeInTheDocument()
    })

    it('still names the file for this tab when the browser refuses storage', async () => {
      vi.stubGlobal('localStorage', blockedStorage())
      await renderApp()
      await importUpload()
      fireEvent.click(screen.getByRole('tab', { name: /Uploads/ }))
      const [card] = uploadCardItems()
      expect(within(card).getByText('savannah-water.csv')).toBeInTheDocument()
      expect(within(card).getByText('1 project mapped · 1 flagged')).toBeInTheDocument()
    })
  })

  it('keeps working when the browser refuses storage: uploads last until a refresh', async () => {
    vi.stubGlobal('localStorage', blockedStorage())
    await renderApp()
    expect(await screen.findByTestId('project-map')).toHaveTextContent('2 projects, 6 overlaps')
    expect(sentUploads(0)).toEqual([])

    await importUpload()
    expect(screen.getByRole('status')).toHaveTextContent('This browser is not saving site data, so they last until you refresh.')
    expect(screen.getByTestId('project-map')).toHaveTextContent('3 projects, 7 overlaps')
    fireEvent.click(screen.getByRole('tab', { name: /Uploads/ }))
    expect(screen.getByText(/This browser is not saving site data, so your uploads last until you refresh\./)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Clear my uploads' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Your uploads were removed from this browser.')
    expect(screen.getByTestId('project-map')).toHaveTextContent('2 projects, 6 overlaps')
  })

  it('shows the published plans and a specific message when the server refuses the saved uploads', async () => {
    const reason = "project 1 ('Water main replacement' by 'Savannah Water') already exists"
    storage.setItem(UPLOADS_STORAGE_KEY, JSON.stringify([clientUpload()]))
    vi.mocked(fetchWorkspace).mockImplementation(async uploads => {
      if (uploads.length) throw new Error(reason)
      return fakeWorkspace(uploads)
    })
    renderClosedApp() // visible without opening the sidebar

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(`Your saved uploads could not be added: ${reason}`)
    expect(screen.getByTestId('project-map')).toHaveTextContent('2 projects, 6 overlaps')
    expect(sentUploads(0)).toEqual([clientUpload()])
    expect(sentUploads(1)).toEqual([])
    expect(savedUploads()).toEqual([clientUpload()]) // nothing deleted behind the user's back

    fireEvent.click(within(alert).getByRole('button', { name: 'Clear my uploads' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Your uploads were removed from this browser.')
    expect(storage.getItem(UPLOADS_STORAGE_KEY)).toBeNull()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('reports unreadable saved uploads instead of crashing, and can clear them', async () => {
    storage.setItem(UPLOADS_STORAGE_KEY, '{not json')
    renderClosedApp()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(UNREADABLE_UPLOADS)
    expect(screen.getByTestId('project-map')).toHaveTextContent('2 projects, 6 overlaps')
    expect(sentUploads(0)).toEqual([])
    fireEvent.click(within(alert).getByRole('button', { name: 'Clear my uploads' }))
    await screen.findByRole('status')
    expect(storage.getItem(UPLOADS_STORAGE_KEY)).toBeNull()
  })

  it('keeps the dialog open with the server\'s reason when an upload is refused, and changes nothing', async () => {
    await renderApp()
    await chooseUpload(uploadFile())
    vi.mocked(fetchWorkspace).mockRejectedValue(new Error("project 1 ('Water main replacement' by 'Savannah Water') already exists"))
    fireEvent.click(await screen.findByRole('button', { name: /Add 1 project & compare/ }))

    expect(await screen.findByRole('alert')).toHaveTextContent('already exists')
    expect(screen.getByRole('button', { name: /Add 1 project & compare/ })).toBeEnabled()
    expect(fetchWorkspace).toHaveBeenCalledTimes(2) // the load, then the refused upload
    expect(storage.getItem(UPLOADS_STORAGE_KEY)).toBeNull()
    expect(screen.getByTestId('project-map')).toHaveTextContent('2 projects, 6 overlaps')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('refuses an upload that would take this browser past 1,000 projects, without asking the server', async () => {
    const full = Array.from({ length: 1000 }, (_, i) => clientUpload({ project_id: `f-${i}`, project_name: `Line ${i}` }))
    storage.setItem(UPLOADS_STORAGE_KEY, JSON.stringify(full))
    vi.mocked(fetchWorkspace).mockImplementation(async () => fakeWorkspace([])) // keep the render small
    await renderApp()
    await chooseUpload(uploadFile())
    fireEvent.click(await screen.findByRole('button', { name: /Add 1 project & compare/ }))

    expect(await screen.findByRole('alert')).toHaveTextContent('This browser keeps up to 1,000 uploaded projects and already has 1000.')
    expect(fetchWorkspace).toHaveBeenCalledTimes(1)
    expect(savedUploads()).toHaveLength(1000)
  })

  it('says uploads are private to this browser, never shared with everyone', async () => {
    storage.setItem(UPLOADS_STORAGE_KEY, JSON.stringify([clientUpload()]))
    await renderApp()
    await screen.findByTestId('project-map')

    expect(screen.queryByText('Shared workspace')).not.toBeInTheDocument()
    expect(screen.getByText('PRIVATE')).toBeInTheDocument()
    expect(screen.getByText('Published plans + your uploads')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /Uploads/ }))
    expect(screen.getByText(/Your uploads stay in this browser, so they are still here after a refresh\. Only you can see them\./)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Upload projects' }))
    expect(screen.getByText('Kept in this browser. Only you see these projects.')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/everyone|shared workspace/i)
    expect(screen.queryByText('SHARED')).not.toBeInTheDocument() // the old footer tag
  })

  it('says uploads are private in the empty Uploads tab too', async () => {
    await renderApp()
    await screen.findByTestId('project-map')
    fireEvent.click(screen.getByRole('tab', { name: /Uploads/ }))
    expect(screen.getByText('CSV spreadsheets · only you can see them')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/everyone/i)
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

    beforeEach(() => { published.overlaps = sortFixture() })

    it('renders a "Sort by" control with exactly the four options, defaulting to Rank (tier, then score)', async () => {
      await renderApp()
      await cards()
      const select = sortSelect()
      expect(within(select).getAllByRole('option').map(o => o.textContent)).toEqual([
        'Rank (tier, then score)', 'Distance (closest first)', 'Time gap (shortest first)', 'Est. savings (highest first)',
      ])
      expect(select).toHaveValue('rank')
      expect(select).toHaveDisplayValue('Rank (tier, then score)')
      // It takes the old caption's place; the pair count stays.
      expect(screen.queryByText('Ranked by proximity & timing')).not.toBeInTheDocument()
      expect(screen.getByText('5 nearby pairs')).toBeInTheDocument()
      expect(cardNames(await cards())).toEqual(['SC line 1', 'SC line 2', 'SC line 3', 'SC line 4', 'SC line 5'])
    })

    it('keeps the server\'s tier-first rank order by default, even when a lower-scoring crossing pair leads', async () => {
      // Rank 1 is a crossing with the lowest score; rank 2 a crews pair with the highest.
      // Served out of order, so the list order comes from rank, not from the response order.
      const [crossing, crews, logistics] = makeOverlaps(3)
      published.overlaps = [
        { ...crews, tier: 'crews', score: 0.95 },
        { ...logistics, tier: 'site_logistics', score: 0.6 },
        { ...crossing, tier: 'crossing', score: 0.2 },
      ]
      await renderApp()
      const items = await cards()
      expect(sortSelect()).toHaveDisplayValue('Rank (tier, then score)')
      expect(cardNames(items)).toEqual(['SC line 1', 'SC line 2', 'SC line 3'])
      expect(items[0]).toHaveTextContent('#01 · 20% match')
      expect(within(items[0]).getByText('Crossing — must coordinate')).toHaveClass('tier-tag')
      expect(items[1]).toHaveTextContent('#02 · 95% match')
      expect(within(items[1]).getByText('Share crews & equipment')).toHaveClass('tier-tag')
    })

    it('shows each card\'s tier label as a chip, one per card, matching its tier', async () => {
      const tiers = ['crossing', 'shared_land', 'site_logistics', 'crews'] as const
      const labels = ['Crossing — must coordinate', 'Share land & permits', 'Share site logistics', 'Share crews & equipment']
      published.overlaps = makeOverlaps(4).map((o, i) => ({ ...o, tier: tiers[i] }))
      await renderApp()
      const items = await cards()
      expect(items).toHaveLength(4)
      items.forEach((item, i) => {
        const chips = item.querySelectorAll('.tier-tag')
        expect(chips).toHaveLength(1)
        expect(chips[0]).toHaveTextContent(new RegExp(`^${labels[i]}$`))
        for (const other of labels) if (other !== labels[i]) expect(item).not.toHaveTextContent(other)
      })
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
      published.overlaps = overlaps
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
      const topCardByOrder = [['rank', 'OVL_1'], ['distance', 'OVL_4'], ['time_gap', 'OVL_5'], ['savings', 'OVL_3']]
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
      published.overlaps = overlaps
      await renderApp()

      const group = await headline()
      expect(within(group).getByText('$2.2M')).toBeInTheDocument() // 709,900 + 1,200,000 + 300,000
      expect(group).toHaveAttribute('title', '$2,209,900 estimated across 3 pairs')
      expect(group).toHaveTextContent('Savings across 3 pairs shown · 0 not estimated')
      expect(within(group).getByText('0 not estimated')).toBeInTheDocument()
    })

    it('shows Projects, Utilities, Nearby pairs and est. savings in one row, with the savings detail line under it (#55)', async () => {
      const { projects, overlaps } = withThirdUtility()
      published = { projects, overlaps }
      await renderApp()
      const group = await headline()

      // One row: the four stats are sibling cells of the same container, in this order, each a number over its label.
      const row = group.parentElement!
      const cells = Array.from(row.children)
      expect(cells).toHaveLength(4)
      expect(cells.map(c => [c.querySelector('strong')?.textContent, c.querySelector(':scope > span')?.textContent])).toEqual([
        ['03', 'Projects'], ['03', 'Utilities'], ['04', 'Nearby pairs'], ['$1.5M', 'est. savings'],
      ])
      expect(cells[3]).toBe(group)
      // The detail line lives in the savings group, as one line with the pluralised pair count.
      const detail = within(group).getByText(/^Savings across/)
      expect(detail).toHaveTextContent(/^Savings across 4 pairs shown · 2 not estimated$/)
      expect(within(detail).getByText('2 not estimated')).toBeInTheDocument()
      // The title is one line now.
      expect(screen.getByRole('heading', { level: 2, name: 'Regional plans. Shared opportunities.' })).toBeInTheDocument()
    })

    it('uses the singular "pair" in the savings detail line for one pair', async () => {
      published.overlaps = makeOverlaps(1).map(o => ({ ...o, est_savings_usd: null }))
      await renderApp()
      const group = await headline()
      expect(within(group).getByText(/^Savings across/)).toHaveTextContent(/^Savings across 1 pair shown · 1 not estimated$/)
    })

    it('excludes null savings from the total and counts them as not estimated', async () => {
      const { projects, overlaps } = withThirdUtility()
      published = { projects, overlaps }
      await renderApp()

      const group = await headline()
      expect(within(group).getByText('$1.5M')).toBeInTheDocument()
      expect(group).toHaveAttribute('title', '$1,500,000 estimated across 2 pairs')
      expect(group).toHaveTextContent('4 pairs shown')
      expect(within(group).getByText('2 not estimated')).toBeInTheDocument()
    })

    it('recomputes the total and counts when a utility layer is hidden and shown again', async () => {
      const { projects, overlaps } = withThirdUtility()
      published = { projects, overlaps }
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

    it('adds the savings the server estimates for an uploaded pair once it is added', async () => {
      published.overlaps = makeOverlaps(6).map((o, i) => ({ ...o, est_savings_usd: i < 2 ? 500000 : null }))
      await renderApp()
      const group = await headline()
      expect(within(group).getByText('$1M')).toBeInTheDocument()
      expect(within(group).getByText('4 not estimated')).toBeInTheDocument()

      // The fake server estimates the uploaded pair at 5% of its $2M cost: 100,000.
      await chooseUpload(uploadFile())
      fireEvent.click(await screen.findByRole('button', { name: /Add 1 project & compare/ }))
      await screen.findByRole('status')

      const after = screen.getByRole('group', { name: 'Estimated savings' })
      expect(within(after).getByText('$1.1M')).toBeInTheDocument() // 500,000 × 2 + 100,000
      expect(after).toHaveTextContent('7 pairs shown')
      expect(within(after).getByText('4 not estimated')).toBeInTheDocument()
    })
  })

  describe('success notice auto-close (#58)', () => {
    // The app renders on real timers so findBy* works; fake timers start once it is ready, before the
    // first notice, so every notice timer is a fake one. Afterwards, act() flushes the mocked fetch.
    afterEach(() => { vi.useRealTimers() })
    const advance = (ms: number) => act(() => { vi.advanceTimersByTime(ms) })
    /** Lets file.text() and the mocked fetch resolve and React render, without moving the fake clock. */
    const settle = () => act(async () => { for (let i = 0; i < 10; i++) await Promise.resolve() })
    const notice = () => screen.queryByRole('status')
    const addedText = /1 proposal from savannah-water\.csv added\./

    async function renderWithFakeTimers() {
      const result = await renderApp()
      vi.useFakeTimers()
      return result
    }
    /** Adds a one-row savannah-water.csv: every call yields the same notice text, whatever the project name. */
    async function importFile(projectName = 'Water main replacement') {
      const csv = 'utility,project_name,lat_center,lon_center,in_service_date,est_cost_usd\n' +
        `Savannah Water,${projectName},32.352116,-81.175112,2026-06-01,2000000\n`
      fireEvent.click(screen.getByRole('button', { name: 'Upload projects' }))
      fireEvent.change(screen.getByLabelText('Project CSV'), { target: { files: [new File([csv], 'savannah-water.csv', { type: 'text/csv' })] } })
      await settle()
      fireEvent.click(screen.getByRole('button', { name: /Add 1 project & compare/ }))
      await settle()
      expect(screen.getByRole('status')).toHaveTextContent(addedText)
    }

    it('is still visible at 5.9 s and gone at 6.1 s', async () => {
      await renderWithFakeTimers()
      await importFile()

      advance(5900)
      expect(notice()).toHaveTextContent(addedText)
      advance(200)
      expect(notice()).not.toBeInTheDocument()
    })

    it('restarts the 6 seconds for a new notice', async () => {
      await renderWithFakeTimers()
      await importFile() // notice A at t=0

      advance(4000)
      fireEvent.click(screen.getByRole('tab', { name: /Uploads/ }))
      fireEvent.click(screen.getByRole('button', { name: 'Remove Savannah Water uploads' }))
      await settle() // notice B at t=4 s
      expect(notice()).toHaveTextContent("Savannah Water's uploads were removed from this browser.")

      advance(5900) // t=9.9 s: A's 6 s have passed, B's have not
      expect(notice()).toHaveTextContent("Savannah Water's uploads were removed from this browser.")
      advance(200) // t=10.1 s
      expect(notice()).not.toBeInTheDocument()
    })

    it('restarts the 6 seconds for a new notice with the same text', async () => {
      await renderWithFakeTimers()
      await importFile() // "1 proposal from savannah-water.csv added. ..." at t=0
      const first = screen.getByRole('status').textContent

      advance(4000)
      await importFile('Second water main') // the same text again at t=4 s
      expect(sentUploads(2)).toHaveLength(2)
      expect(screen.getByRole('status').textContent).toBe(first)

      advance(5900) // t=9.9 s
      expect(notice()).toHaveTextContent(addedText)
      advance(200) // t=10.1 s
      expect(notice()).not.toBeInTheDocument()
    })

    it('the X still dismisses it immediately, and clears its timer', async () => {
      await renderWithFakeTimers()
      await importFile()
      expect(vi.getTimerCount()).toBe(1)

      fireEvent.click(screen.getByRole('button', { name: 'Dismiss notification' }))
      expect(notice()).not.toBeInTheDocument()
      expect(vi.getTimerCount()).toBe(0)
    })

    it('clears its timer when the app unmounts', async () => {
      const { unmount } = await renderWithFakeTimers()
      await importFile()
      expect(vi.getTimerCount()).toBe(1)

      unmount()
      expect(vi.getTimerCount()).toBe(0)
    })

    it('does not auto-close the upload-problem alert', async () => {
      storage.setItem(UPLOADS_STORAGE_KEY, '{not json')
      renderClosedApp()
      expect(await screen.findByRole('alert')).toHaveTextContent(UNREADABLE_UPLOADS)

      vi.useFakeTimers()
      advance(60_000)
      expect(screen.getByRole('alert')).toHaveTextContent(UNREADABLE_UPLOADS)
      expect(within(screen.getByRole('alert')).getByRole('button', { name: 'Clear my uploads' })).toBeInTheDocument()
    })
  })
})
