// Detail panel for one coordination opportunity. Presentational only: the parent owns selection.
import { utilityColor } from '../colors'
import { formatDays, formatMiles, formatUsd } from '../format'
import type { Overlap, Project } from '../types'
import Icon from './Icon'

interface OverlapDetailProps {
  overlap: Overlap
  onClose: () => void
}

function ProjectCard({ project }: { project: Project }) {
  return (
    <div className="selection-project">
      <i style={{ background: utilityColor(project.utility) }} />
      <div>
        <strong>{project.project_name}</strong>
        <small>{project.utility}</small>
        <span>In service {project.in_service_date}</span>
      </div>
    </div>
  )
}

export default function OverlapDetail({ overlap, onClose }: OverlapDetailProps) {
  const distance = formatMiles(overlap.distance_mi)
  const gap = formatDays(overlap.time_gap_days)
  const savings = overlap.est_savings_usd

  return (
    <section aria-labelledby="overlap-detail-heading" className="overlap-detail">
      <div className="overlap-detail-top">
        <h2 id="overlap-detail-heading" className="overlap-detail-title">
          Opportunity #{overlap.rank}
          <span className="overlap-detail-score">score {overlap.score.toFixed(2)}</span>
        </h2>
        <button type="button" onClick={onClose} aria-label="Close" className="icon-button">
          <Icon name="close" size={16} />
        </button>
      </div>

      <div className="overlap-detail-projects">
        <ProjectCard project={overlap.project_a} />
        <ProjectCard project={overlap.project_b} />
      </div>

      <dl className="overlap-detail-metrics">
        <dt>Distance</dt>
        <dd>{distance}</dd>
        <dt>Time gap</dt>
        <dd>{gap}</dd>
        <dt>Est. savings</dt>
        <dd className="overlap-detail-savings">{savings === null ? 'Not estimated' : formatUsd(savings)}</dd>
      </dl>
      <p className="selection-footnote">{overlap.savings_basis}</p>

      <p className="overlap-detail-why">
        Why this matters: these projects are {distance} apart and enter service {gap} apart, so the
        utilities could share crews, equipment and right-of-way work instead of mobilizing twice.
      </p>
    </section>
  )
}
