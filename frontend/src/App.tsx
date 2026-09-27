import { useEffect, useMemo, useState } from 'react'
import { fetchWorkspace } from './api'
import { utilityColor } from './colors'
import OverlapDetail from './components/OverlapDetail'
import ProjectMap from './components/ProjectMap'
import UploadProjects from './components/UploadProjects'
import Icon from './components/Icon'
import { formatPairs, formatScorePct, formatUsd, formatUsdCompact } from './format'
import { MAX_UPLOADED_PROJECTS, SUBMITTED_OVERLAP_PREFIX, SUBMITTED_PROJECT_PREFIX, type ImportBatch } from './importProjects'
import { DEFAULT_MIN_MATCH, filterByMinMatch, matchLabel } from './matchFilter'
import { summarizeSavings } from './savings'
import { tierLabel } from './tiers'
import { useTheme } from './theme'
import { DEFAULT_SORT_KEY, SORT_OPTIONS, sortOverlaps, type SortKey } from './sortOverlaps'
import type { Overlap, Project, Workspace } from './types'
import { loadUploadFiles, loadUploads, saveUploadFiles, saveUploads, type UploadFiles } from './uploadCache'
import { ownUploads, uploadCards } from './uploadCards'
import './workspace.css'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; projects: Project[]; overlaps: Overlap[] }
type Tab = 'opportunities' | 'projects' | 'imports'

const errorMessage = (err: unknown) => err instanceof Error ? err.message : String(err)
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`
/** How long a success notice stays on the map before closing itself (#58). Upload problems stay until dismissed. */
const NOTICE_MS = 6000

function App() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [focusedProject, setFocusedProject] = useState<Project | null>(null)
  const [tab, setTab] = useState<Tab>('opportunities')
  const [query, setQuery] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>(DEFAULT_SORT_KEY)
  const [uploadOpen, setUploadOpen] = useState(false)
  // This tab's uploads, kept only to show which rows were flagged and left out.
  const [batches, setBatches] = useState<ImportBatch[]>([])
  // This browser's uploads as imported (client ids), mirrored in localStorage (uploadCache.ts).
  // The server never keeps them: they are sent with every POST /workspace.
  const [uploads, setUploads] = useState<Project[]>([])
  // Which file each of those came from (upload id -> file name), mirrored next to them in localStorage (#57).
  const [uploadFiles, setUploadFiles] = useState<UploadFiles>({})
  // False when the browser will not store them: they then last until a refresh.
  const [persisted, setPersisted] = useState(true)
  // Why this browser's uploads are not on the map (refused by the server, unreadable, ...).
  const [uploadProblem, setUploadProblem] = useState('')
  const [hidden, setHidden] = useState<string[]>([])
  // The map's minimum-match slider (#54): 0 ("All") shows everything, exactly as before it existed.
  const [minMatch, setMinMatch] = useState(DEFAULT_MIN_MATCH)
  // An object, not the bare text, so a new notice with the same text is still a new value and restarts the timer.
  const [notice, setNotice] = useState<{ text: string } | null>(null)
  const showNotice = (text: string) => setNotice({ text })
  // Each notice closes itself after NOTICE_MS; closing it sooner (X) or unmounting clears the timer.
  useEffect(() => {
    if (!notice) return
    const timer = setTimeout(() => setNotice(null), NOTICE_MS)
    return () => clearTimeout(timer)
  }, [notice])
  // The sidebar starts closed so the map fills the screen; the top bar's menu button toggles it.
  const [sidebarOpen, setSidebarOpen] = useState(false)
  // Light or dark (#45): main.tsx applied the initial one to <html> before this first render.
  const [theme, setTheme] = useTheme()
  useEffect(() => {
    let cancelled = false
    const cached = loadUploads()
    async function load(): Promise<[Workspace, string]> {
      try {
        return [await fetchWorkspace(cached.uploads), cached.problem ?? '']
      } catch (err) {
        if (!cached.uploads.length) throw err
        // E.g. a published project now has the same name as a saved upload: show the published
        // plans anyway and say why the uploads are missing, rather than no map at all.
        return [await fetchWorkspace([]), `Your saved uploads could not be added: ${errorMessage(err)}`]
      }
    }
    load()
      .then(([workspace, problem]) => {
        if (cancelled) return
        setUploads(cached.uploads); setUploadFiles(loadUploadFiles()); setPersisted(cached.available); setUploadProblem(problem)
        setState({ status: 'ready', ...workspace })
      })
      .catch((err: unknown) => { if (!cancelled) setState({ status: 'error', message: errorMessage(err) }) })
    return () => { cancelled = true }
  }, [])
  const projects = useMemo(() => state.status === 'ready' ? state.projects : [], [state])
  const overlaps = useMemo(() => state.status === 'ready' ? state.overlaps : [], [state])
  // Only this browser's own uploads; the rest of the SUB- projects are the server's standing sample submissions (#62).
  const submitted = ownUploads(projects, uploads)
  const sampleCount = projects.filter(p => p.project_id.startsWith(SUBMITTED_PROJECT_PREFIX)).length - submitted.length
  // One card per company (plus one per file for flagged rows with no company to go under): uploadCards.ts.
  const cards = uploadCards(submitted, uploadFiles, batches)
  const utilities = [...new Set(projects.map(p => p.utility))]
  const visibleProjects = useMemo(() => projects.filter(p => !hidden.includes(p.utility)), [projects, hidden])
  const visibleOverlaps = useMemo(() => overlaps.filter(o => !hidden.includes(o.project_a.utility) && !hidden.includes(o.project_b.utility)), [overlaps, hidden])
  // Then the minimum match (#54): everything below reads `matched`, so the map and the sidebar always agree.
  // At "All" these are the visible arrays themselves.
  const matched = useMemo(() => filterByMinMatch(visibleProjects, visibleOverlaps, minMatch), [visibleProjects, visibleOverlaps, minMatch])
  const savings = useMemo(() => summarizeSavings(matched.overlaps), [matched])
  // Both derived from what is shown, so a pair or project the filters hide closes its detail panel.
  const selected = matched.overlaps.find(o => o.overlap_id === selectedId)
  const focused = focusedProject && matched.projects.some(p => p.project_id === focusedProject.project_id) ? focusedProject : null
  // Nothing reaches the minimum, though the utility layers show some pairs: say so, not "no matching pairs".
  const belowMinMatch = minMatch !== DEFAULT_MIN_MATCH && visibleOverlaps.length > 0 && matched.overlaps.length === 0
  const search = query.toLowerCase().trim()
  const filteredProjects = matched.projects.filter(p => `${p.project_name} ${p.utility}`.toLowerCase().includes(search))
  const filteredOverlaps = matched.overlaps.filter(o => `${o.project_a.project_name} ${o.project_b.project_name} ${o.project_a.utility} ${o.project_b.utility}`.toLowerCase().includes(search))
  const sortedOverlaps = sortOverlaps(filteredOverlaps, sortKey)
  function select(id: string) { setSelectedId(id); setFocusedProject(null) }
  function toggleUtility(utility: string) {
    setHidden(current => current.includes(utility) ? current.filter(u => u !== utility) : [...current, utility])
    setSelectedId(null); setFocusedProject(null)
  }
  function showWorkspace(workspace: Workspace) {
    setState({ status: 'ready', ...workspace }); setSelectedId(null); setFocusedProject(null)
  }
  const keptNote = (kept: boolean) => kept ? 'They stay in this browser and only you can see them.' : 'This browser is not saving site data, so they last until you refresh.'
  /** Scores this browser's uploads plus the new ones; only if the server accepts them are they kept. Throws to the dialog. */
  async function addImport(batch: ImportBatch) {
    const added = batch.rows.flatMap(r => r.project ? [r.project] : [])
    const next = [...uploads, ...added]
    if (next.length > MAX_UPLOADED_PROJECTS) throw new Error(`This browser keeps up to 1,000 uploaded projects and already has ${uploads.length}. Clear some uploads first.`)
    const workspace = await fetchWorkspace(next)
    const kept = saveUploads(next)
    setUploadFiles(saveUploadFiles(next, { ...uploadFiles, ...Object.fromEntries(added.map(p => [p.project_id, batch.filename])) }))
    showWorkspace(workspace); setUploads(next); setPersisted(kept); setUploadProblem('')
    // Show every layer and match again, so the new pairs can't hide behind a filter.
    setBatches(current => [...current, batch]); setHidden([]); setMinMatch(DEFAULT_MIN_MATCH); setQuery('')
    setTab('opportunities')
    showNotice(`${plural(added.length, 'proposal')} from ${batch.filename} added. ${keptNote(kept)} Comparisons updated.`)
  }
  /** Replaces this browser's uploads (the user removed some), then refreshes the comparisons. */
  async function keepUploads(next: Project[], done: string) {
    const kept = saveUploads(next)
    setUploadFiles(saveUploadFiles(next, uploadFiles)) // drops the removed uploads' file names
    setUploads(next); setPersisted(kept); setUploadProblem('')
    try {
      showWorkspace(await fetchWorkspace(next)); showNotice(done)
    } catch (err) {
      setNotice(null); setUploadProblem(`${done} But the map could not refresh (${errorMessage(err)}). Reload the page.`)
    }
  }
  function clearUploads() {
    setBatches([])
    void keepUploads([], 'Your uploads were removed from this browser.')
  }
  function removeUtility(utility: string) {
    const ids = new Set(submitted.filter(p => p.utility === utility).map(p => p.project_id.slice(SUBMITTED_PROJECT_PREFIX.length)))
    // Its flagged rows go with its card, rather than reappearing under their file's name.
    setBatches(current => current.map(b => ({ ...b, rows: b.rows.filter(r => r.project || r.utility !== utility) })))
    void keepUploads(uploads.filter(u => !ids.has(u.project_id)), `${utility}'s uploads were removed from this browser.`)
  }
  return (
    <main className="workspace">
      <header className="workspace-header">
        {/* Three columns (1fr auto 1fr) keep the brand centered whatever the sides hold. Left: the
            icon-only menu button, right above the sidebar it opens (disabled until the data, and so the sidebar, exists).
            Right: Upload projects. The theme is picked in the map's Dark/Light/Satellite control. */}
        <div className="header-side"><button type="button" className="sidebar-toggle" disabled={state.status !== 'ready'} aria-label={sidebarOpen ? 'Close menu' : 'Open menu'} aria-expanded={sidebarOpen} aria-controls="workspace-sidebar" onClick={() => setSidebarOpen(open => !open)}><Icon name={sidebarOpen ? 'close' : 'menu'} size={20} /></button></div>
        <div className="brand"><h1 className="brand-logo"><img src="/relay-logo.svg" alt="Relay" width={126} height={28} /></h1></div>
        <div className="header-side header-actions"><button className="primary-button" disabled={state.status !== 'ready'} onClick={() => setUploadOpen(true)}><Icon name="upload" size={16} /> <span className="header-button-label">Upload projects</span></button></div>
      </header>
      {state.status === 'loading' && <p className="workspace-message">Loading projects…</p>}
      {state.status === 'error' && <div role="alert" className="workspace-message">Could not load project data: {state.message}</div>}
      {state.status === 'ready' && <div className={`workspace-body${sidebarOpen ? '' : ' sidebar-closed'}`}>
        {/* Always mounted so it can slide: closed = zero width, and inert + aria-hidden so nothing inside is focusable or announced. */}
        <aside className="workspace-sidebar" id="workspace-sidebar" aria-label="Workspace sidebar" aria-hidden={!sidebarOpen} inert={!sidebarOpen}><div className="sidebar-panel">
          <div className="sidebar-intro"><p className="eyebrow">SHARED GROUND</p><h2>Regional plans. Shared opportunities.</h2><p>See where your next project meets someone else’s.</p></div>
          {/* One row of four stats; the savings detail line sits under the whole row (CSS) but stays inside the savings group. */}
          <div className="workspace-metrics"><div><strong>{projects.length.toString().padStart(2, '0')}</strong><span>Projects</span></div><div><strong>{utilities.length.toString().padStart(2, '0')}</strong><span>Utilities</span></div><div><strong>{overlaps.length.toString().padStart(2, '0')}</strong><span>Nearby pairs</span></div>
            <div className="savings-headline" role="group" aria-label="Estimated savings" title={`${formatUsd(savings.totalUsd)} estimated across ${formatPairs(savings.estimatedCount)}`}><strong>{formatUsdCompact(savings.totalUsd)}</strong><span>est. savings</span><small>Savings across {formatPairs(savings.pairCount)} shown · <span>{savings.notEstimatedCount} not estimated</span></small></div></div>
          <details className="utility-filters"><summary><Icon name="layers" size={15} /> Map layers <span>{utilities.length}</span></summary><div>{utilities.map(utility => <label key={utility}><input type="checkbox" checked={!hidden.includes(utility)} onChange={() => toggleUtility(utility)} /><i style={{ background: utilityColor(utility) }} /><span>{utility}</span><small>{projects.filter(p => p.utility === utility).length}</small></label>)}</div></details>
          <div className="workspace-tabs" role="tablist" aria-label="Workspace data">{(['opportunities', 'projects', 'imports'] as Tab[]).map(t => <button key={t} role="tab" id={`tab-${t}`} aria-controls="workspace-panel" aria-selected={tab === t} tabIndex={tab === t ? 0 : -1} onKeyDown={e => {
              const tabs: Tab[] = ['opportunities', 'projects', 'imports']
              const direction = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
              if (!direction) return
              e.preventDefault()
              const next = tabs[(tabs.indexOf(t) + direction + tabs.length) % tabs.length]
              setTab(next); setQuery(''); document.getElementById(`tab-${next}`)?.focus()
            }} onClick={() => { setTab(t); setQuery('') }}>{t === 'opportunities' ? 'Opportunities' : t === 'projects' ? 'Projects' : 'Uploads'}{t === 'imports' && submitted.length > 0 && <span>{submitted.length}</span>}</button>)}</div>
          {tab !== 'imports' && <label className="workspace-search"><Icon name="search" size={16} /><input placeholder={tab === 'projects' ? 'Find a project or utility' : 'Find an opportunity'} aria-label="Search workspace" value={query} onChange={e => setQuery(e.target.value)} />{query && <button onClick={() => setQuery('')} aria-label="Clear search"><Icon name="close" size={14} /></button>}</label>}
          <div className="sidebar-content" id="workspace-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
            {tab === 'opportunities' && <><div className="list-caption"><span>{filteredOverlaps.length} nearby pairs</span><label className="list-sort"><span aria-hidden="true">Sort:</span><select aria-label="Sort by" value={sortKey} onChange={e => setSortKey(e.target.value as SortKey)}>{SORT_OPTIONS.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}</select></label></div><ol className="opportunity-list" aria-label="Top coordination opportunities">{sortedOverlaps.map(o => <li key={o.overlap_id}><button className={`opportunity-card ${selectedId === o.overlap_id ? 'selected' : ''}`} aria-pressed={selectedId === o.overlap_id} onClick={() => select(o.overlap_id)}>
              <div className="opportunity-top"><span>#{o.rank.toString().padStart(2, '0')} · {formatScorePct(o.score)} match</span><span>{o.distance_mi.toFixed(1)} mi apart <Icon name="arrow" size={14} /></span></div>
              <div className="opportunity-tier"><span className="tier-tag">{tierLabel(o.tier)}</span></div>
              <div className="project-pair">{[o.project_a, o.project_b].map(p => <div key={p.project_id}><i style={{ background: utilityColor(p.utility) }} /><div><strong>{p.project_name}</strong><small>{p.utility}</small></div></div>)}</div>
              <div className="opportunity-bottom"><span>{o.time_gap_days} days apart in service</span>{o.est_savings_usd === null ? <span>No estimate</span> : <span title={`${formatUsd(o.est_savings_usd)} est. savings`}>{formatUsdCompact(o.est_savings_usd)} est. savings</span>}{o.overlap_id.startsWith(SUBMITTED_OVERLAP_PREFIX) && <span className="new-tag">Uploaded</span>}</div>
            </button></li>)}</ol>{!filteredOverlaps.length && belowMinMatch && <div className="empty-state"><Icon name="search" size={24} /><strong>{`No pairs at ${matchLabel(minMatch)}; lower the minimum`}</strong><p>Drag the Minimum match slider on the map to the left to see more pairs.</p></div>}{!filteredOverlaps.length && !belowMinMatch && <div className="empty-state"><Icon name="search" size={24} /><strong>No matching pairs</strong><p>Try another search or turn on more utility layers. Projects must be within 25 miles to appear here.</p></div>}</>}
            {tab === 'projects' && <><div className="list-caption"><span>{filteredProjects.length} projects</span><span>All participating utilities</span></div>{filteredProjects.map(p => <button className={`project-row ${focused?.project_id === p.project_id ? 'active' : ''}`} key={p.project_id} onClick={() => { setFocusedProject(p); setSelectedId(null) }}><i style={{ background: utilityColor(p.utility) }} /><div><strong>{p.project_name}</strong><small>{p.utility}</small><span>In service {p.in_service_date}</span></div><Icon name="arrow" size={14} /></button>)}{!filteredProjects.length && <p className="empty-state">{belowMinMatch ? `No projects in pairs at ${matchLabel(minMatch)}; lower the minimum.` : 'No projects match your search.'}</p>}</>}
            {tab === 'imports' && <>{!cards.length ? <div className="empty-state upload-empty"><Icon name="upload" size={30} /><strong>Your plans belong here.</strong><p>Add a project spreadsheet to find nearby work across utilities.</p><button className="secondary-button" onClick={() => setUploadOpen(true)}>Upload your first file <Icon name="arrow" size={16} /></button><small>CSV spreadsheets · only you can see them</small></div> : <ul className="upload-cards" aria-label="Your uploads">{cards.map(card => card.kind === 'company'
              ? <li className="batch-card" key={`company:${card.utility}`}><i style={{ background: utilityColor(card.utility) }} /><strong>{card.utility}</strong>{card.files.map(file => <p className="batch-file" key={file}><Icon name="file" size={14} /><span>{file}</span></p>)}<p>{card.files.length ? `${plural(card.mapped, 'project')} mapped${card.flagged ? ` · ${card.flagged.length} flagged` : ''}` : plural(card.mapped, 'uploaded project')}</p>{card.flagged?.map((r, i) => <p className="flagged-reason" key={i}>Row {r.row}: {r.issues.join('; ')}</p>)}<button className="text-link" aria-label={`Remove ${card.utility} uploads`} onClick={() => removeUtility(card.utility)}><Icon name="close" size={14} /> Remove</button></li>
              : <li className="batch-card" key={`file:${card.id}`}><strong className="batch-file"><Icon name="file" size={14} /><span>{card.filename}</span></strong><p>{card.flagged.length === 1 ? '1 row needs' : `${card.flagged.length} rows need`} attention</p>{card.flagged.map(r => <p className="flagged-reason" key={r.row}>Row {r.row}: {r.issues.join('; ')}</p>)}</li>)}</ul>}{uploads.length > 0 && <button className="secondary-button clear-uploads" onClick={clearUploads}>Clear my uploads</button>}<p className="session-note">{persisted ? 'Your uploads stay in this browser, so they are still here after a refresh. Only you can see them.' : 'This browser is not saving site data, so your uploads last until you refresh. Only you can see them.'} Published utility plans are unchanged.</p>{sampleCount > 0 && <p className="session-note">{plural(sampleCount, 'made-up sample project')} uploaded for the demo {sampleCount === 1 ? 'is' : 'are'} also on the map, tagged Uploaded. {sampleCount === 1 ? 'It is' : 'They are'} not yours, so {sampleCount === 1 ? 'it is' : 'they are'} not listed here.</p>}</>}
          </div>
          <footer className="sidebar-footer"><span className="source-dot" /> {submitted.length ? 'Published plans + your uploads' : sampleCount ? 'Published plans + sample uploads' : 'Published utility plans'}<span>{submitted.length ? 'PRIVATE' : sampleCount ? 'SC / GA + SAMPLE' : 'SC / GA'}</span></footer>
        </div></aside>
        <section className="workspace-map" aria-label="Project map">
          <ProjectMap projects={matched.projects} overlaps={matched.overlaps} selectedId={selected?.overlap_id ?? null} onSelect={select} focusedProject={focused} theme={theme} onThemeChange={setTheme} minMatch={minMatch} onMinMatchChange={setMinMatch} />
          <div className="map-context"><span className="source-dot" /><strong>Project coverage</strong><span>{matched.projects.length} mapped projects</span></div>
          {uploadProblem && <div role="alert" className="workspace-notice upload-problem"><span>{uploadProblem}</span><button className="text-link" onClick={clearUploads}>Clear my uploads</button><button onClick={() => setUploadProblem('')} aria-label="Dismiss upload problem"><Icon name="close" size={14} /></button></div>}
          {notice && <div role="status" className="workspace-notice"><Icon name="check" size={16} /><span>{notice.text}</span><button onClick={() => setNotice(null)} aria-label="Dismiss notification"><Icon name="close" size={14} /></button></div>}
          {selected && <div className="selection-panel"><OverlapDetail overlap={selected} onClose={() => setSelectedId(null)} /></div>}
          {!selected && focused && <div className="selection-panel"><div className="selection-heading"><span>PROJECT DETAILS</span><button className="icon-button" aria-label="Close details" onClick={() => setFocusedProject(null)}><Icon name="close" size={16} /></button></div>
            <h3>{focused.project_name}</h3>
            <div className="selection-project"><i style={{ background: utilityColor(focused.utility) }} /><div><strong>{focused.project_name}</strong><small>{focused.utility}</small><span>In service <b>{focused.in_service_date}</b></span></div></div>
            <div className="selection-footnote">{focused.location_confidence === 'low' ? 'Location supplied or unverified. Confirm coordinates before planning.' : 'Location confirmed in the source dataset.'}</div>
          </div>}
        </section>
      </div>}
      {uploadOpen && <UploadProjects existing={projects} onClose={() => setUploadOpen(false)} onImport={addImport} />}
    </main>
  )
}
export default App
