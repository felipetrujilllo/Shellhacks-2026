// Detail panel for one coordination opportunity. Presentational only: the parent owns selection.
import { utilityColor } from '../colors'
import { formatDays, formatMiles, formatScorePct, formatUsd } from '../format'
import { tierLabel } from '../tiers'
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
  // closest_mi is 0 exactly when the projects cross or touch (docs/api.md).
  const closest = overlap.closest_mi === 0 ? `${formatMiles(0)} (touching)` : formatMiles(overlap.closest_mi)
  const tier = tierLabel(overlap.tier)
  const gap = formatDays(overlap.time_gap_days)
  const savings = overlap.est_savings_usd

  return (
    <section aria-labelledby="overlap-detail-heading" className="overlap-detail">
      <div className="overlap-detail-top">
        <h2 id="overlap-detail-heading" className="overlap-detail-title">
          Opportunity #{overlap.rank}
          <span className="overlap-detail-score">{formatScorePct(overlap.score)} match</span>
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
        <dt>Tier</dt>
        <dd>{tier}</dd>
        <dt>Center distance</dt>
        <dd>{distance}</dd>
        <dt>Closest approach</dt>
        <dd>{closest}</dd>
        <dt>Time gap</dt>
        <dd>{gap}</dd>
        <dt>Est. savings</dt>
        <dd className="overlap-detail-savings">{savings === null ? 'Not estimated' : formatUsd(savings)}</dd>
      </dl>
      <p className="selection-footnote">{overlap.savings_basis}</p>

      {/* The tier follows from the closest approach alone, never the center distance or gap. */}
      <p className="overlap-detail-why">
        Why this matters: their closest points are {formatMiles(overlap.closest_mi)} apart, which
        puts them in the “{tier}” tier. Their centers are {distance} apart and they enter service{' '}
        {gap} apart, so the utilities could share crews, equipment and right-of-way work instead of
        mobilizing twice.
      </p>
    </section>
  )
}
