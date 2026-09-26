// Ranked list of coordination opportunities. Presentational only: no fetching, no map logic.
import type { Overlap, Project } from '../types'

interface OverlapListProps {
  overlaps: Overlap[]
  selectedId: string | null
  onSelect: (overlapId: string) => void
}

function ProjectLine({ project }: { project: Project }) {
  return (
    <span className="mb-3 block">
      <span className="font-medium">{project.project_name}</span>{' '}
      <span className="mt-1 block text-xs text-slate-400">({project.utility})</span>
    </span>
  )
}

export default function OverlapList({ overlaps, selectedId, onSelect }: OverlapListProps) {
  // Don't trust input order: rank 1 is always first.
  const ranked = [...overlaps].sort((a, b) => a.rank - b.rank)

  if (ranked.length === 0) {
    return <p className="text-sm text-slate-400">No overlapping projects found.</p>
  }

  return (
    <ol className="flex flex-col gap-3" aria-label="Top coordination opportunities">
      {ranked.map((o) => {
        const selected = o.overlap_id === selectedId
        return (
          <li key={o.overlap_id}>
            <button
              type="button"
              onClick={() => onSelect(o.overlap_id)}
              aria-pressed={selected}
              className={`w-full rounded-xl border p-4 text-left text-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 ${
                selected
                  ? 'border-violet-400/70 bg-violet-400/10 shadow-lg shadow-violet-950/20'
                  : 'border-white/10 bg-slate-950/40 hover:border-slate-500 hover:bg-slate-800'
              }`}
            >
              <span className="mb-3 block text-xs font-semibold uppercase tracking-wide text-amber-400">
                #{o.rank}
              </span>
              <ProjectLine project={o.project_a} />
              <ProjectLine project={o.project_b} />
              <span className="mt-3 block border-t border-white/10 pt-3 text-xs text-slate-400">
                {o.distance_mi.toFixed(1)} mi apart · {o.time_gap_days} days apart in service
              </span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}
