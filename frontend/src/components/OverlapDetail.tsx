// Detail panel for one coordination opportunity. Presentational only: the parent owns selection.
import { formatDays, formatMiles, formatUsd } from '../format'
import type { Overlap, Project } from '../types'

interface OverlapDetailProps {
  overlap: Overlap
  onClose: () => void
}

function ProjectCard({ project }: { project: Project }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <p className="font-medium">{project.project_name}</p>
      <p className="text-xs text-slate-500">{project.utility}</p>
      <p className="mt-1 text-xs text-slate-600">In service {project.in_service_date}</p>
    </div>
  )
}

export default function OverlapDetail({ overlap, onClose }: OverlapDetailProps) {
  const distance = formatMiles(overlap.distance_mi)
  const gap = formatDays(overlap.time_gap_days)
  const savings = overlap.est_savings_usd

  return (
    <section
      aria-labelledby="overlap-detail-heading"
      className="mb-4 rounded-lg border border-amber-500 bg-amber-50 p-4 text-sm shadow"
    >
      <div className="mb-3 flex items-start justify-between gap-2">
        <h2 id="overlap-detail-heading" className="text-lg font-semibold">
          Opportunity #{overlap.rank}
          <span className="ml-2 text-xs font-normal text-slate-600">score {overlap.score.toFixed(2)}</span>
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="rounded px-2 text-lg leading-none text-slate-500 hover:bg-amber-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
        >
          ×
        </button>
      </div>

      <div className="flex flex-col gap-2">
        <ProjectCard project={overlap.project_a} />
        <ProjectCard project={overlap.project_b} />
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1">
        <dt className="text-slate-600">Distance</dt>
        <dd>{distance}</dd>
        <dt className="text-slate-600">Time gap</dt>
        <dd>{gap}</dd>
        <dt className="text-slate-600">Est. savings</dt>
        <dd className="font-semibold">{savings === null ? 'Not estimated' : formatUsd(savings)}</dd>
      </dl>
      <p className="mt-1 text-xs text-slate-600">{overlap.savings_basis}</p>

      <p className="mt-3 font-medium">
        Why this matters: these projects are {distance} apart and enter service {gap} apart, so the
        utilities could share crews, equipment and right-of-way work instead of mobilizing twice.
      </p>
    </section>
  )
}
