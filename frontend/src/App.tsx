// Page composition + state only: fetching lives in api.ts, rendering in components/.
import { useEffect, useState } from 'react'
import { fetchOverlaps, fetchProjects } from './api'
import OverlapList from './components/OverlapList'
import ProjectMap from './components/ProjectMap'
import type { Overlap, Project } from './types'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; projects: Project[]; overlaps: Overlap[] }

function App() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([fetchProjects(), fetchOverlaps()])
      .then(([projects, overlaps]) => {
        if (!cancelled) setState({ status: 'ready', projects, overlaps })
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({ status: 'error', message: err instanceof Error ? err.message : String(err) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <main className="flex h-screen flex-col">
      <header className="border-b border-slate-200 px-4 py-3">
        <h1 className="text-2xl font-bold">GridWatch</h1>
        <p className="text-sm text-slate-600">
          Overlapping transmission projects: Dominion Energy South Carolina × Georgia Power
        </p>
      </header>

      {state.status === 'loading' && <p className="p-4 text-slate-600">Loading projects…</p>}

      {state.status === 'error' && (
        <div role="alert" className="m-4 rounded-md border border-red-300 bg-red-50 p-4 text-red-800">
          Could not load project data: {state.message}
        </div>
      )}

      {state.status === 'ready' && (
        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <section className="h-[60vh] md:h-auto md:flex-1" aria-label="Project map">
            <ProjectMap
              projects={state.projects}
              overlaps={state.overlaps}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          </section>
          <aside className="overflow-y-auto border-slate-200 p-4 md:w-96 md:border-l">
            <h2 className="mb-3 text-lg font-semibold">Top coordination opportunities</h2>
            <OverlapList overlaps={state.overlaps} selectedId={selectedId} onSelect={setSelectedId} />
          </aside>
        </div>
      )}
    </main>
  )
}

export default App
