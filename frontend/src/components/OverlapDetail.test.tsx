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

  /** The yellow "why this matters" box (the whole paragraph, not just its bold lead-in). */
  function whyBox() {
    const lead = screen.getByText('Why this matters:')
    expect(lead.tagName).toBe('STRONG')
    const box = lead.closest('p')
    expect(box).not.toBeNull()
    return box as HTMLElement
  }

  const SHARE_WORK = 'share crews, equipment and right-of-way work instead of mobilizing twice.'

  it('"why this matters" explains the numbers without repeating any of them (#56)', () => {
    // The contract example: distance_mi 5.65, closest_mi 2.99, tier site_logistics, 152 days.
    render(<OverlapDetail overlap={overlapExample()} onClose={() => {}} />)

    expect(whyBox()).toHaveTextContent(
      `Why this matters: these lines pass close enough that the utilities could ${SHARE_WORK} ` +
        'They’re within about 5 months of each other, so the work can line up.',
    )
    const text = whyBox().textContent ?? ''
    expect(text).not.toMatch(/\bmi\b/) // no miles at all: not 5.7 (center), not 3.0 (closest)
    expect(text).not.toMatch(/5\.7|5\.65|3\.0|2\.99/)
    expect(text).not.toMatch(/\bdays?\b/)
    expect(text).not.toContain('152')
    expect(text).not.toContain('Share site logistics')
    expect(text).not.toMatch(/tier/i)
  })

  it('"why this matters" does not repeat a crossing\'s 0.0 mi, its center distance or its raw days', () => {
    render(<OverlapDetail overlap={{ ...overlapExample(), closest_mi: 0, tier: 'crossing', time_gap_days: 2709 }} onClose={() => {}} />)

    const text = whyBox().textContent ?? ''
    expect(text).not.toMatch(/\bmi\b|0\.0|5\.7|2709|\bdays?\b|touching/)
    expect(text).not.toContain('Crossing — must coordinate')
  })

  // Spelled out (not read from tiers.ts) so a changed label fails here too.
  const TIER_CASES: [CoordinationTier, string][] = [
    ['crossing', 'Crossing — must coordinate'],
    ['shared_land', 'Share land & permits'],
    ['site_logistics', 'Share site logistics'],
    ['crews', 'Share crews & equipment'],
  ]
  const CROSS = 'these lines cross, so the utilities must coordinate and could ' + SHARE_WORK
  const PASS_CLOSE = 'these lines pass close enough that the utilities could ' + SHARE_WORK

  it.each(TIER_CASES)('"why this matters" words the %s tier by what it means, not by its label', (tier, label) => {
    render(<OverlapDetail overlap={{ ...overlapExample(), tier }} onClose={() => {}} />)

    const why = whyBox()
    expect(why).toHaveTextContent(tier === 'crossing' ? CROSS : PASS_CLOSE)
    expect(why).not.toHaveTextContent(tier === 'crossing' ? 'pass close enough' : 'these lines cross')
    expect(why).toHaveTextContent('share crews, equipment and right-of-way work')
    for (const [, anyLabel] of TIER_CASES) expect(why).not.toHaveTextContent(anyLabel)
    // The label still shows in the table above.
    expect(screen.getByText('Tier', { selector: 'dt' }).nextElementSibling).toHaveTextContent(label)
  })

  it('"why this matters" follows the tier (from the closest approach), not the center distance or gap', () => {
    // Centers far apart and years apart, but the closest points touch: still the crossing wording.
    const { unmount } = render(
      <OverlapDetail overlap={{ ...overlapExample(), distance_mi: 24.9, closest_mi: 0, tier: 'crossing', time_gap_days: 3074 }} onClose={() => {}} />,
    )
    expect(whyBox()).toHaveTextContent(CROSS)
    unmount()

    // Centers nearly on top of each other and in service together, but the closest-approach tier is crews.
    render(<OverlapDetail overlap={{ ...overlapExample(), distance_mi: 0.1, closest_mi: 12, tier: 'crews', time_gap_days: 0 }} onClose={() => {}} />)
    expect(whyBox()).toHaveTextContent(PASS_CLOSE)
    expect(whyBox()).not.toHaveTextContent('these lines cross')
  })

  // Rounding rule: > 365 days -> Math.round(days / 365) years; <= 365 days -> Math.round(days * 12 / 365)
  // months, 0 months read as "within a month"; singular for 1.
  const GAP_CASES: [number, string][] = [
    [0, 'They’re within a month of each other, so the work can line up.'],
    [15, 'They’re within a month of each other, so the work can line up.'],
    [16, 'They’re within about 1 month of each other, so the work can line up.'],
    [45, 'They’re within about 1 month of each other, so the work can line up.'],
    [46, 'They’re within about 2 months of each other, so the work can line up.'],
    [152, 'They’re within about 5 months of each other, so the work can line up.'],
    [365, 'They’re within about 12 months of each other, so the work can line up.'],
    [366, 'They’re about 1 year apart in service, so one schedule would have to move.'],
    [547, 'They’re about 1 year apart in service, so one schedule would have to move.'],
    [548, 'They’re about 2 years apart in service, so one schedule would have to move.'],
    [2709, 'They’re about 7 years apart in service, so one schedule would have to move.'],
    [3074, 'They’re about 8 years apart in service, so one schedule would have to move.'],
  ]

  it.each(GAP_CASES)('"why this matters" words a %i-day time gap in plain words', (days, sentence) => {
    render(<OverlapDetail overlap={{ ...overlapExample(), time_gap_days: days }} onClose={() => {}} />)

    const why = whyBox()
    expect(why.textContent?.endsWith(` ${sentence}`)).toBe(true)
    expect(why.textContent).not.toMatch(/\b(?:0|1) (?:months|years)\b|\bdays?\b/)
    if (days > 365) expect(why).not.toHaveTextContent('month')
    else expect(why).not.toHaveTextContent('year')
  })

  it('"why this matters" fails loud on a time gap outside the API contract (integer >= 0)', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {}) // React logs the render error
    for (const bad of [-1, 1.5, Number.NaN]) {
      expect(() => render(<OverlapDetail overlap={{ ...overlapExample(), time_gap_days: bad }} onClose={() => {}} />)).toThrow(
        /time_gap_days must be a whole number >= 0/,
      )
    }
    vi.restoreAllMocks()
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
