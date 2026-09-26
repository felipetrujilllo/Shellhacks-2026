import { useEffect, useMemo, useState } from 'react'
import { fetchOverlaps, fetchProjects } from './api'
import { utilityColor } from './colors'
import OverlapDetail from './components/OverlapDetail'
import ProjectMap from './components/ProjectMap'
import UploadProjects from './components/UploadProjects'
import Icon from './components/Icon'
import { compareImports, type ImportBatch } from './importProjects'
import type { Overlap, Project } from './types'
import './workspace.css'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; projects: Project[]; overlaps: Overlap[] }
type Tab = 'opportunities' | 'projects' | 'imports'

function App() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [focusedProject, setFocusedProject] = useState<Project | null>(null)
  const [tab, setTab] = useState<Tab>('opportunities')
  const [query, setQuery] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)
  const [batches, setBatches] = useState<ImportBatch[]>([])
  const [hidden, setHidden] = useState<string[]>([])
  const [notice, setNotice] = useState('')
  useEffect(() => {
    let cancelled = false
    Promise.all([fetchProjects(), fetchOverlaps()])
      .then(([projects, overlaps]) => { if (!cancelled) setState({ status: 'ready', projects, overlaps }) })
      .catch((err: unknown) => { if (!cancelled) setState({ status: 'error', message: err instanceof Error ? err.message : String(err) }) })
    return () => { cancelled = true }
  }, [])
  const imported = useMemo(() => batches.flatMap(b => b.rows.flatMap(r => r.project ? [r.project] : [])), [batches])
  const projects = useMemo(() => [...(state.status === 'ready' ? state.projects : []), ...imported], [state, imported])
  const overlaps = useMemo(() => compareImports(imported, projects, state.status === 'ready' ? state.overlaps : []), [state, imported, projects])
  const utilities = [...new Set(projects.map(p => p.utility))]
  const visibleProjects = useMemo(() => projects.filter(p => !hidden.includes(p.utility)), [projects, hidden])
  const visibleOverlaps = useMemo(() => overlaps.filter(o => !hidden.includes(o.project_a.utility) && !hidden.includes(o.project_b.utility)), [overlaps, hidden])
  const selected = visibleOverlaps.find(o => o.overlap_id === selectedId)
  const search = query.toLowerCase().trim()
  const filteredProjects = visibleProjects.filter(p => `${p.project_name} ${p.utility}`.toLowerCase().includes(search))
  const filteredOverlaps = visibleOverlaps.filter(o => `${o.project_a.project_name} ${o.project_b.project_name} ${o.project_a.utility} ${o.project_b.utility}`.toLowerCase().includes(search))
  function select(id: string) { setSelectedId(id); setFocusedProject(null) }
  function toggleUtility(utility: string) {
    setHidden(current => current.includes(utility) ? current.filter(u => u !== utility) : [...current, utility])
    setSelectedId(null); setFocusedProject(null)
  }
  function addImport(batch: ImportBatch) {
    setBatches(current => [...current, batch]); setHidden([]); setSelectedId(null); setFocusedProject(null); setQuery('')
    setTab('opportunities')
    const count = batch.rows.filter(r => r.project).length
    setNotice(`${count} proposal${count === 1 ? '' : 's'} added from ${batch.filename}. Comparisons updated.`)
  }
  return (
    <main className="workspace">
      <header className="workspace-header">
        <div className="brand"><span className="brand-symbol"><Icon name="grid" size={19} /></span><h1>GridWatch</h1></div>
        <span className="header-divider" />
        <div className="workspace-title"><span>Planning workspace</span><small>Regional coordination</small></div>
        <div className="header-actions"><span className="local-badge"><i /> Local session</span><button className="primary-button" disabled={state.status !== 'ready'} onClick={() => setUploadOpen(true)}><Icon name="upload" size={16} /> Upload projects</button></div>
      </header>
      {state.status === 'loading' && <p className="workspace-message">Loading projects…</p>}
      {state.status === 'error' && <div role="alert" className="workspace-message">Could not load project data: {state.message}</div>}
      {state.status === 'ready' && <div className="workspace-body">
        <aside className="workspace-sidebar">
          <div className="sidebar-intro"><p className="eyebrow">SHARED GROUND</p><h2>Regional plans.<br />Shared opportunities.</h2><p>See where your next project meets someone else’s.</p></div>
          <div className="workspace-metrics"><div><strong>{projects.length.toString().padStart(2, '0')}</strong><span>Projects</span></div><div><strong>{utilities.length.toString().padStart(2, '0')}</strong><span>Utilities</span></div><div><strong>{overlaps.length.toString().padStart(2, '0')}</strong><span>Nearby pairs</span></div></div>
          <details className="utility-filters"><summary><Icon name="layers" size={15} /> Map layers <span>{utilities.length}</span></summary><div>{utilities.map(utility => <label key={utility}><input type="checkbox" checked={!hidden.includes(utility)} onChange={() => toggleUtility(utility)} /><i style={{ background: utilityColor(utility) }} /><span>{utility}</span><small>{projects.filter(p => p.utility === utility).length}</small></label>)}</div></details>
          <div className="workspace-tabs" role="tablist" aria-label="Workspace data">{(['opportunities', 'projects', 'imports'] as Tab[]).map(t => <button key={t} role="tab" id={`tab-${t}`} aria-controls="workspace-panel" aria-selected={tab === t} tabIndex={tab === t ? 0 : -1} onKeyDown={e => {
              const tabs: Tab[] = ['opportunities', 'projects', 'imports']
              const direction = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
              if (!direction) return
              e.preventDefault()
              const next = tabs[(tabs.indexOf(t) + direction + tabs.length) % tabs.length]
              setTab(next); setQuery(''); document.getElementById(`tab-${next}`)?.focus()
            }} onClick={() => { setTab(t); setQuery('') }}>{t === 'opportunities' ? 'Opportunities' : t === 'projects' ? 'Projects' : 'Uploads'}{t === 'imports' && batches.length > 0 && <span>{batches.length}</span>}</button>)}</div>
          {tab !== 'imports' && <label className="workspace-search"><Icon name="search" size={16} /><input placeholder={tab === 'projects' ? 'Find a project or utility' : 'Find an opportunity'} aria-label="Search workspace" value={query} onChange={e => setQuery(e.target.value)} />{query && <button onClick={() => setQuery('')} aria-label="Clear search"><Icon name="close" size={14} /></button>}</label>}
          <div className="sidebar-content" id="workspace-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
            {tab === 'opportunities' && <><div className="list-caption"><span>{filteredOverlaps.length} nearby pairs</span><span>Ranked by proximity & timing</span></div><ol className="opportunity-list" aria-label="Top coordination opportunities">{filteredOverlaps.map(o => <li key={o.overlap_id}><button className={`opportunity-card ${selectedId === o.overlap_id ? 'selected' : ''}`} aria-pressed={selectedId === o.overlap_id} onClick={() => select(o.overlap_id)}>
              <div className="opportunity-top"><span>#{o.rank.toString().padStart(2, '0')}</span><span>{o.distance_mi.toFixed(1)} mi apart <Icon name="arrow" size={14} /></span></div>
              <div className="project-pair">{[o.project_a, o.project_b].map(p => <div key={p.project_id}><i style={{ background: utilityColor(p.utility) }} /><div><strong>{p.project_name}</strong><small>{p.utility}</small></div></div>)}</div>
              <div className="opportunity-bottom"><span>{o.time_gap_days} days apart in service</span>{o.overlap_id.startsWith('import:') && <span className="new-tag">New</span>}</div>
            </button></li>)}</ol>{!filteredOverlaps.length && <div className="empty-state"><Icon name="search" size={24} /><strong>No matching pairs</strong><p>Try another search or turn on more utility layers. Projects must be within 25 miles to appear here.</p></div>}</>}
            {tab === 'projects' && <><div className="list-caption"><span>{filteredProjects.length} projects</span><span>All participating utilities</span></div>{filteredProjects.map(p => <button className={`project-row ${focusedProject?.project_id === p.project_id ? 'active' : ''}`} key={p.project_id} onClick={() => { setFocusedProject(p); setSelectedId(null) }}><i style={{ background: utilityColor(p.utility) }} /><div><strong>{p.project_name}</strong><small>{p.utility}</small><span>In service {p.in_service_date}</span></div><Icon name="arrow" size={14} /></button>)}{!filteredProjects.length && <p className="empty-state">No projects match your search.</p>}</>}
            {tab === 'imports' && <>{!batches.length ? <div className="empty-state upload-empty"><Icon name="upload" size={30} /><strong>Your plans belong here.</strong><p>Add a project spreadsheet to find nearby work across utilities.</p><button className="secondary-button" onClick={() => setUploadOpen(true)}>Upload your first file <Icon name="arrow" size={16} /></button><small>CSV spreadsheets · local to this tab</small></div> : batches.map(b => <div className="batch-card" key={b.id}><Icon name="file" /><strong>{b.filename}</strong><p>{b.rows.filter(r => r.project).length} mapped · {b.rows.filter(r => !r.project).length} flagged</p>{b.rows.filter(r => !r.project).map(r => <p className="flagged-reason" key={r.row}>Row {r.row}: {r.issues.join('; ')}</p>)}<button className="text-link" onClick={() => { setBatches(current => current.filter(x => x.id !== b.id)); setSelectedId(null); setFocusedProject(null); setNotice('Upload removed from this session.') }}>Remove upload</button></div>)}<p className="session-note">Uploads stay in this tab and clear on refresh. Original project data is unchanged.</p></>}
          </div>
          <footer className="sidebar-footer"><span className="source-dot" /> {batches.length ? 'Published plans + your proposals' : 'Published utility plans'}<span>{batches.length ? 'LOCAL' : 'SC / GA'}</span></footer>
        </aside>
        <section className="workspace-map" aria-label="Project map">
          <ProjectMap projects={visibleProjects} overlaps={visibleOverlaps} selectedId={selected?.overlap_id ?? null} onSelect={select} focusedProject={focusedProject} />
          <div className="map-context"><span className="source-dot" /><strong>Project coverage</strong><span>{visibleProjects.length} mapped projects</span></div>
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
