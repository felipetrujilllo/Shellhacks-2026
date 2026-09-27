import { useEffect, useMemo, useState } from 'react'
import { fetchWorkspace } from './api'
import { utilityColor } from './colors'
import OverlapDetail from './components/OverlapDetail'
import ProjectMap from './components/ProjectMap'
import UploadProjects from './components/UploadProjects'
import Icon from './components/Icon'
import { formatPairs, formatScorePct, formatUsd, formatUsdCompact } from './format'
import { MAX_UPLOADED_PROJECTS, SUBMITTED_OVERLAP_PREFIX, SUBMITTED_PROJECT_PREFIX, type ImportBatch } from './importProjects'
import { summarizeSavings } from './savings'
import { DEFAULT_SORT_KEY, SORT_OPTIONS, sortOverlaps, type SortKey } from './sortOverlaps'
import type { Overlap, Project, Workspace } from './types'
import { loadUploads, saveUploads } from './uploadCache'
import './workspace.css'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; projects: Project[]; overlaps: Overlap[] }
type Tab = 'opportunities' | 'projects' | 'imports'

const errorMessage = (err: unknown) => err instanceof Error ? err.message : String(err)
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

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
  // False when the browser will not store them: they then last until a refresh.
  const [persisted, setPersisted] = useState(true)
  // Why this browser's uploads are not on the map (refused by the server, unreadable, ...).
  const [uploadProblem, setUploadProblem] = useState('')
  const [hidden, setHidden] = useState<string[]>([])
  const [notice, setNotice] = useState('')
  // The sidebar starts closed so the map fills the screen; the top bar's menu button toggles it.
  const [sidebarOpen, setSidebarOpen] = useState(false)
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
        setUploads(cached.uploads); setPersisted(cached.available); setUploadProblem(problem)
        setState({ status: 'ready', ...workspace })
      })
      .catch((err: unknown) => { if (!cancelled) setState({ status: 'error', message: errorMessage(err) }) })
    return () => { cancelled = true }
  }, [])
  const projects = useMemo(() => state.status === 'ready' ? state.projects : [], [state])
  const overlaps = useMemo(() => state.status === 'ready' ? state.overlaps : [], [state])
  const submitted = projects.filter(p => p.project_id.startsWith(SUBMITTED_PROJECT_PREFIX))
  const submittedUtilities = [...new Set(submitted.map(p => p.utility))]
  const utilities = [...new Set(projects.map(p => p.utility))]
  const visibleProjects = useMemo(() => projects.filter(p => !hidden.includes(p.utility)), [projects, hidden])
  const visibleOverlaps = useMemo(() => overlaps.filter(o => !hidden.includes(o.project_a.utility) && !hidden.includes(o.project_b.utility)), [overlaps, hidden])
  const savings = useMemo(() => summarizeSavings(visibleOverlaps), [visibleOverlaps])
  const selected = visibleOverlaps.find(o => o.overlap_id === selectedId)
  const search = query.toLowerCase().trim()
  const filteredProjects = visibleProjects.filter(p => `${p.project_name} ${p.utility}`.toLowerCase().includes(search))
  const filteredOverlaps = visibleOverlaps.filter(o => `${o.project_a.project_name} ${o.project_b.project_name} ${o.project_a.utility} ${o.project_b.utility}`.toLowerCase().includes(search))
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
    showWorkspace(workspace); setUploads(next); setPersisted(kept); setUploadProblem('')
    setBatches(current => [...current, batch]); setHidden([]); setQuery('')
    setTab('opportunities')
    setNotice(`${plural(added.length, 'proposal')} from ${batch.filename} added. ${keptNote(kept)} Comparisons updated.`)
  }
  /** Replaces this browser's uploads (the user removed some), then refreshes the comparisons. */
  async function keepUploads(next: Project[], done: string) {
    const kept = saveUploads(next)
    setUploads(next); setPersisted(kept); setUploadProblem('')
    try {
      showWorkspace(await fetchWorkspace(next)); setNotice(done)
    } catch (err) {
      setNotice(''); setUploadProblem(`${done} But the map could not refresh (${errorMessage(err)}). Reload the page.`)
    }
  }
  function clearUploads() {
    setBatches([])
    void keepUploads([], 'Your uploads were removed from this browser.')
  }
  function removeUtility(utility: string) {
    const ids = new Set(submitted.filter(p => p.utility === utility).map(p => p.project_id.slice(SUBMITTED_PROJECT_PREFIX.length)))
    void keepUploads(uploads.filter(u => !ids.has(u.project_id)), `${utility}'s uploads were removed from this browser.`)
  }
  return (
    <main className="workspace">
      <header className="workspace-header">
        {/* Three columns (1fr auto 1fr) keep the brand centered whatever the sides hold. Left: the
            icon-only menu button, right above the sidebar it opens (disabled until the data, and so the sidebar, exists). */}
        <div className="header-side"><button type="button" className="sidebar-toggle" disabled={state.status !== 'ready'} aria-label={sidebarOpen ? 'Close menu' : 'Open menu'} aria-expanded={sidebarOpen} aria-controls="workspace-sidebar" onClick={() => setSidebarOpen(open => !open)}><Icon name={sidebarOpen ? 'close' : 'menu'} size={20} /></button></div>
        <div className="brand"><span className="brand-symbol"><img src="/relay-icon.svg" alt="" width={28} height={28} /></span><h1>Relay</h1></div>
        <div className="header-side header-actions"><button className="primary-button" disabled={state.status !== 'ready'} onClick={() => setUploadOpen(true)}><Icon name="upload" size={16} /> <span className="header-button-label">Upload projects</span></button></div>
      </header>
      {state.status === 'loading' && <p className="workspace-message">Loading projects…</p>}
      {state.status === 'error' && <div role="alert" className="workspace-message">Could not load project data: {state.message}</div>}
      {state.status === 'ready' && <div className={`workspace-body${sidebarOpen ? '' : ' sidebar-closed'}`}>
        {/* Always mounted so it can slide: closed = zero width, and inert + aria-hidden so nothing inside is focusable or announced. */}
        <aside className="workspace-sidebar" id="workspace-sidebar" aria-label="Workspace sidebar" aria-hidden={!sidebarOpen} inert={!sidebarOpen}><div className="sidebar-panel">
          <div className="sidebar-intro"><p className="eyebrow">SHARED GROUND</p><h2>Regional plans.<br />Shared opportunities.</h2><p>See where your next project meets someone else’s.</p></div>
          <div className="workspace-metrics"><div><strong>{projects.length.toString().padStart(2, '0')}</strong><span>Projects</span></div><div><strong>{utilities.length.toString().padStart(2, '0')}</strong><span>Utilities</span></div><div><strong>{overlaps.length.toString().padStart(2, '0')}</strong><span>Nearby pairs</span></div></div>
          <div className="savings-headline" role="group" aria-label="Estimated savings" title={`${formatUsd(savings.totalUsd)} estimated across ${formatPairs(savings.estimatedCount)}`}><strong>{formatUsdCompact(savings.totalUsd)}</strong><div><span>est. savings · {formatPairs(savings.pairCount)} shown</span><small>{savings.notEstimatedCount} not estimated</small></div></div>
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
              <div className="project-pair">{[o.project_a, o.project_b].map(p => <div key={p.project_id}><i style={{ background: utilityColor(p.utility) }} /><div><strong>{p.project_name}</strong><small>{p.utility}</small></div></div>)}</div>
              <div className="opportunity-bottom"><span>{o.time_gap_days} days apart in service</span>{o.est_savings_usd === null ? <span>No estimate</span> : <span title={`${formatUsd(o.est_savings_usd)} est. savings`}>{formatUsdCompact(o.est_savings_usd)} est. savings</span>}{o.overlap_id.startsWith(SUBMITTED_OVERLAP_PREFIX) && <span className="new-tag">Uploaded</span>}</div>
            </button></li>)}</ol>{!filteredOverlaps.length && <div className="empty-state"><Icon name="search" size={24} /><strong>No matching pairs</strong><p>Try another search or turn on more utility layers. Projects must be within 25 miles to appear here.</p></div>}</>}
            {tab === 'projects' && <><div className="list-caption"><span>{filteredProjects.length} projects</span><span>All participating utilities</span></div>{filteredProjects.map(p => <button className={`project-row ${focusedProject?.project_id === p.project_id ? 'active' : ''}`} key={p.project_id} onClick={() => { setFocusedProject(p); setSelectedId(null) }}><i style={{ background: utilityColor(p.utility) }} /><div><strong>{p.project_name}</strong><small>{p.utility}</small><span>In service {p.in_service_date}</span></div><Icon name="arrow" size={14} /></button>)}{!filteredProjects.length && <p className="empty-state">No projects match your search.</p>}</>}
            {tab === 'imports' && <>{!batches.length && !submitted.length ? <div className="empty-state upload-empty"><Icon name="upload" size={30} /><strong>Your plans belong here.</strong><p>Add a project spreadsheet to find nearby work across utilities.</p><button className="secondary-button" onClick={() => setUploadOpen(true)}>Upload your first file <Icon name="arrow" size={16} /></button><small>CSV spreadsheets · only you can see them</small></div> : <>{batches.map(b => <div className="batch-card" key={b.id}><Icon name="file" /><strong>{b.filename}</strong><p>{b.rows.filter(r => r.project).length} mapped · {b.rows.filter(r => !r.project).length} flagged</p>{b.rows.filter(r => !r.project).map(r => <p className="flagged-reason" key={r.row}>Row {r.row}: {r.issues.join('; ')}</p>)}</div>)}{submittedUtilities.map(utility => <div className="batch-card" key={utility}><i style={{ background: utilityColor(utility) }} /><strong>{utility}</strong><p>{submitted.filter(p => p.utility === utility).length} uploaded projects</p><button className="text-link" aria-label={`Remove ${utility} uploads`} onClick={() => removeUtility(utility)}><Icon name="close" size={14} /> Remove</button></div>)}</>}{uploads.length > 0 && <button className="secondary-button clear-uploads" onClick={clearUploads}>Clear my uploads</button>}<p className="session-note">{persisted ? 'Your uploads stay in this browser, so they are still here after a refresh. Only you can see them.' : 'This browser is not saving site data, so your uploads last until you refresh. Only you can see them.'} Published utility plans are unchanged.</p></>}
          </div>
          <footer className="sidebar-footer"><span className="source-dot" /> {submitted.length ? 'Published plans + your uploads' : 'Published utility plans'}<span>{submitted.length ? 'PRIVATE' : 'SC / GA'}</span></footer>
        </div></aside>
        <section className="workspace-map" aria-label="Project map">
          <ProjectMap projects={visibleProjects} overlaps={visibleOverlaps} selectedId={selected?.overlap_id ?? null} onSelect={select} focusedProject={focusedProject} />
          <div className="map-context"><span className="source-dot" /><strong>Project coverage</strong><span>{visibleProjects.length} mapped projects</span></div>
          {uploadProblem && <div role="alert" className="workspace-notice upload-problem"><span>{uploadProblem}</span><button className="text-link" onClick={clearUploads}>Clear my uploads</button><button onClick={() => setUploadProblem('')} aria-label="Dismiss upload problem"><Icon name="close" size={14} /></button></div>}
          {notice && <div role="status" className="workspace-notice"><Icon name="check" size={16} /><span>{notice}</span><button onClick={() => setNotice('')} aria-label="Dismiss notification"><Icon name="close" size={14} /></button></div>}
          {selected && <div className="selection-panel"><OverlapDetail overlap={selected} onClose={() => setSelectedId(null)} /></div>}
          {!selected && focusedProject && <div className="selection-panel"><div className="selection-heading"><span>PROJECT DETAILS</span><button className="icon-button" aria-label="Close details" onClick={() => setFocusedProject(null)}><Icon name="close" size={16} /></button></div>
            <h3>{focusedProject.project_name}</h3>
            <div className="selection-project"><i style={{ background: utilityColor(focusedProject.utility) }} /><div><strong>{focusedProject.project_name}</strong><small>{focusedProject.utility}</small><span>In service <b>{focusedProject.in_service_date}</b></span></div></div>
            <div className="selection-footnote">{focusedProject.location_confidence === 'low' ? 'Location supplied or unverified. Confirm coordinates before planning.' : 'Location confirmed in the source dataset.'}</div>
          </div>}
        </section>
      </div>}
      {uploadOpen && <UploadProjects existing={projects} onClose={() => setUploadOpen(false)} onImport={addImport} />}
    </main>
  )
}
export default App
