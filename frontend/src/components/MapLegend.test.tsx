import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { UTILITY_COLORS } from '../colors'
import MapLegend from './MapLegend'

describe('MapLegend', () => {
  it('has a low-confidence location entry alongside the utilities and opportunity entries', () => {
    render(<MapLegend />)

    expect(screen.getByText('Low-confidence location (unconfirmed)')).toBeInTheDocument()
    for (const utility of Object.keys(UTILITY_COLORS)) expect(screen.getByText(utility)).toBeInTheDocument()
    expect(screen.getByText('Coordination opportunity')).toBeInTheDocument()
    expect(screen.getByText('Selected opportunity')).toBeInTheDocument()
  })

  it('draws the low-confidence swatch dotted, unlike the dashed opportunity swatch', () => {
    render(<MapLegend />)

    const low = screen.getByText('Low-confidence location (unconfirmed)')
    const opportunity = screen.getByText('Coordination opportunity')
    expect(low.querySelector('.border-dotted')).not.toBeNull()
    expect(low.querySelector('.border-dashed')).toBeNull()
    expect(opportunity.querySelector('.border-dashed')).not.toBeNull()
  })
})
