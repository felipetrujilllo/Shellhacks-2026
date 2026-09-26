// Ranked list of coordination opportunities. Presentational only: no fetching, no map logic.
import type { Overlap, Project } from '../types'

interface OverlapListProps {
  overlaps: Overlap[]
  selectedId: string | null
  onSelect: (overlapId: string) => void
}

function ProjectLine({ project }: { project: Project }) {
  return (
    <span className="block">
      <span className="font-medium">{project.project_name}</span>{' '}
      <span className="text-xs text-slate-500">({project.utility})</span>
    </span>
  )
}

export default function OverlapList({ overlaps, selectedId, onSelect }: OverlapListProps) {
  // Don't trust input order: rank 1 is always first.
  const ranked = [...overlaps].sort((a, b) => a.rank - b.rank)

  if (ranked.length === 0) {
    return <p className="text-sm text-slate-500">No overlapping projects found.</p>
  }

  return (
    <ol className="flex flex-col gap-2" aria-label="Top coordination opportunities">
      {ranked.map((o) => {
        const selected = o.overlap_id === selectedId
        return (
          <li key={o.overlap_id}>
            <button
              type="button"
              onClick={() => onSelect(o.overlap_id)}
              aria-pressed={selected}
              className={`w-full rounded-lg border p-3 text-left text-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 ${
                selected
                  ? 'border-amber-500 bg-amber-50 shadow'
                  : 'border-slate-200 bg-white hover:bg-slate-50'
              }`}
            >
              <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-amber-700">
                #{o.rank}
              </span>
              <ProjectLine project={o.project_a} />
              <ProjectLine project={o.project_b} />
              <span className="mt-1 block text-xs text-slate-600">
                {o.distance_mi.toFixed(1)} mi apart · {o.time_gap_days} days apart in service
              </span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}
