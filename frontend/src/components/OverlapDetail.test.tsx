import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { apiExample, expectOverlap } from '../test/apiExamples'
import type { CoordinationTier } from '../types'
import OverlapDetail from './OverlapDetail'

// The docs/api.md contract example: OVL_2, rank 2 (tier-first, behind the crossing OVL_1),
// score 0.8311, 5.65 mi, 152 days, $709,900.
function overlapExample() {
  const overlap = apiExample('overlap')
  expectOverlap(overlap)
  return overlap
}

const NO_FIGURE_BASIS = 'No figure: cost redacted in both utilities’ filings.'

function overlapWithoutSavings() {
  return { ...overlapExample(), est_savings_usd: null, savings_basis: NO_FIGURE_BASIS }
}

describe('OverlapDetail', () => {
  it('renders both project names, utilities and in-service dates', () => {
    render(<OverlapDetail overlap={overlapExample()} onClose={() => {}} />)

    expect(screen.getByText('Jasper - Okatie 230 kV #2: Construct')).toBeInTheDocument()
    expect(screen.getByText('SAV: MCINTOSH - PURRYSBURG 230KV REACTORS')).toBeInTheDocument()
    expect(screen.getByText('Dominion Energy South Carolina')).toBeInTheDocument()
    expect(screen.getByText('Georgia Power')).toBeInTheDocument()
    expect(screen.getByText('In service 2025-12-31')).toBeInTheDocument()
    expect(screen.getByText('In service 2026-06-01')).toBeInTheDocument()
  })

  it('renders distance in miles to 1 decimal, time gap in days, rank and score', () => {
    render(<OverlapDetail overlap={overlapExample()} onClose={() => {}} />)

    expect(screen.getByText('5.7 mi')).toBeInTheDocument() // distance_mi 5.65
    expect(screen.getByText('152 days')).toBeInTheDocument()
    const heading = screen.getByRole('heading', { name: /opportunity #2/i })
    expect(heading).toHaveTextContent('Opportunity #2')
    expect(heading).toHaveTextContent('83% match') // score 0.8311
    expect(screen.getByRole('region', { name: /opportunity #2/i })).toBeInTheDocument()
  })

  it('shows the score as a whole-number percentage, not the raw 0-1 decimal', () => {
    render(<OverlapDetail overlap={{ ...overlapExample(), score: 0.7055 }} onClose={() => {}} />)

    const heading = screen.getByRole('heading', { name: /opportunity #2/i })
    expect(heading).toHaveTextContent('71% match')
    expect(heading).not.toHaveTextContent('0.71')
    const panel = screen.getByRole('region', { name: /opportunity #2/i })
    expect(panel).not.toHaveTextContent('0.7055')
    expect(panel).not.toHaveTextContent('0.71')
  })

  it('shows the savings figure formatted as USD, with its basis, when present', () => {
    const overlap = overlapExample()
    render(<OverlapDetail overlap={overlap} onClose={() => {}} />)

    expect(screen.getByText('$709,900')).toBeInTheDocument()
    expect(screen.getByText(overlap.savings_basis)).toBeInTheDocument()
    expect(screen.queryByText('Not estimated')).not.toBeInTheDocument()
  })

  it('shows the savings_basis text and no dollar figure when est_savings_usd is null', () => {
    render(<OverlapDetail overlap={overlapWithoutSavings()} onClose={() => {}} />)

    expect(screen.getByText(NO_FIGURE_BASIS)).toBeInTheDocument()
    expect(screen.getByText('Not estimated')).toBeInTheDocument()
    expect(screen.queryByText(/\$\d/)).not.toBeInTheDocument()
  })

  it('"why this matters" sentence includes the distance and time gap', () => {
    render(<OverlapDetail overlap={overlapExample()} onClose={() => {}} />)

    const why = screen.getByText(/why this matters/i)
    expect(why).toHaveTextContent('5.7 mi apart')
    expect(why).toHaveTextContent('152 days apart')
  })

  // Spelled out (not read from tiers.ts) so a changed label fails here too.
  const TIER_CASES: [CoordinationTier, string][] = [
    ['crossing', 'Crossing — must coordinate'],
    ['shared_land', 'Share land & permits'],
    ['site_logistics', 'Share site logistics'],
    ['crews', 'Share crews & equipment'],
  ]

  it.each(TIER_CASES)('"why this matters" names the %s tier\'s label', (tier, label) => {
    render(<OverlapDetail overlap={{ ...overlapExample(), tier }} onClose={() => {}} />)

    const why = screen.getByText(/why this matters/i)
    expect(why).toHaveTextContent(`“${label}” tier`)
    expect(why).toHaveTextContent('share crews, equipment and right-of-way work')
    for (const [, other] of TIER_CASES) if (other !== label) expect(why).not.toHaveTextContent(other)
  })

  it('"why this matters" puts the tier down to the closest approach, not the center distance or gap', () => {
    // The contract example: closest_mi 2.99 (site_logistics), distance_mi 5.65, 152 days.
    render(<OverlapDetail overlap={overlapExample()} onClose={() => {}} />)

    const why = screen.getByText(/why this matters/i)
    expect(why).toHaveTextContent(
      'their closest points are 3.0 mi apart, which puts them in the “Share site logistics” tier.',
    )
    expect(why).toHaveTextContent('Their centers are 5.7 mi apart and they enter service 152 days apart')
    expect(why.textContent).not.toMatch(/(5\.7 mi|days) apart, which puts them/)
  })

  it('"why this matters" reads a crossing as 0.0 mi apart at the closest points', () => {
    render(<OverlapDetail overlap={{ ...overlapExample(), closest_mi: 0, tier: 'crossing' }} onClose={() => {}} />)

    expect(screen.getByText(/why this matters/i)).toHaveTextContent(
      'their closest points are 0.0 mi apart, which puts them in the “Crossing — must coordinate” tier.',
    )
  })

  it('shows "Center distance", "Closest approach" and the tier label as metric rows (no bare "Distance")', () => {
    // The contract example: distance_mi 5.65, closest_mi 2.99, tier site_logistics.
    render(<OverlapDetail overlap={overlapExample()} onClose={() => {}} />)

    const row = (term: string) => screen.getByText(term, { selector: 'dt' }).nextElementSibling
    expect(row('Center distance')).toHaveTextContent(/^5\.7 mi$/)
    expect(row('Closest approach')).toHaveTextContent(/^3\.0 mi$/)
    expect(row('Tier')).toHaveTextContent(/^Share site logistics$/)
    expect(screen.queryByText('Distance', { selector: 'dt' })).not.toBeInTheDocument()
  })

  it('reads a closest approach of 0 as touching, with the crossing tier label', () => {
    render(<OverlapDetail overlap={{ ...overlapExample(), closest_mi: 0, tier: 'crossing' }} onClose={() => {}} />)

    const row = (term: string) => screen.getByText(term, { selector: 'dt' }).nextElementSibling
    expect(row('Closest approach')).toHaveTextContent(/^0\.0 mi \(touching\)$/)
    expect(row('Tier')).toHaveTextContent(/^Crossing — must coordinate$/)
    expect(row('Center distance')).toHaveTextContent(/^5\.7 mi$/)
  })

  it('calls onClose when the close button is clicked', () => {
    const onClose = vi.fn()
    render(<OverlapDetail overlap={overlapExample()} onClose={onClose} />)

    expect(onClose).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
