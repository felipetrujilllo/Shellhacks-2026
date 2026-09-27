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

const SHARE_WORK = 'share crews, equipment and right-of-way work instead of mobilizing twice.'

/**
 * What the tier means, without naming it: the table above already shows the label and the miles.
 * `tier` is the server's, which follows from the closest approach alone (never the center distance or gap).
 */
function whyTier(tier: Overlap['tier']): string {
  return tier === 'crossing'
    ? `these lines cross, so the utilities must coordinate and could ${SHARE_WORK}`
    : `these lines pass close enough that the utilities could ${SHARE_WORK}`
}

/**
 * The in-service gap in plain words, not raw days. Rounding rule: over 365 days -> whole years,
 * Math.round(days / 365) (2709 -> 7, 366 -> 1); 365 days or less -> whole months,
 * Math.round(days * 12 / 365) (152 -> 5, 365 -> 12), with 0 months (15 days or less) read as
 * "within a month". Singular for 1. The API promises an integer >= 0 (docs/api.md); anything
 * else throws rather than printing nonsense.
 */
function whyTimeGap(days: number): string {
  if (!Number.isInteger(days) || days < 0) {
    throw new RangeError(`time_gap_days must be a whole number >= 0, got ${days}`)
  }
  const plural = (n: number, unit: string) => `${n} ${n === 1 ? unit : `${unit}s`}`
  if (days > 365) {
    return `They’re about ${plural(Math.round(days / 365), 'year')} apart in service, so one schedule would have to move.`
  }
  const months = Math.round((days * 12) / 365)
  const within = months === 0 ? 'within a month' : `within about ${plural(months, 'month')}`
  return `They’re ${within} of each other, so the work can line up.`
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

      <p className="overlap-detail-why">
        <strong>Why this matters:</strong> {whyTier(overlap.tier)} {whyTimeGap(overlap.time_gap_days)}
      </p>
    </section>
  )
}
