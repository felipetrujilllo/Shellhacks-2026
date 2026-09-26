import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { makeOverlaps } from '../test/overlapFixtures'
import OverlapList from './OverlapList'

describe('OverlapList', () => {
  it('renders overlaps in rank order even when given out of order', () => {
    const overlaps = makeOverlaps(3)
    const shuffled = [overlaps[2], overlaps[0], overlaps[1]]
    render(<OverlapList overlaps={shuffled} selectedId={null} onSelect={() => {}} />)

    const items = screen.getAllByRole('button')
    expect(items).toHaveLength(3)
    expect(items.map((b) => within(b).getByText(/^#\d+$/).textContent)).toEqual(['#1', '#2', '#3'])
    expect(items[0]).toHaveTextContent('SC line 1')
    expect(items[2]).toHaveTextContent('SC line 3')
  })

  it('shows both project names, distance in miles and time gap in days for each item', () => {
    render(<OverlapList overlaps={makeOverlaps(2)} selectedId={null} onSelect={() => {}} />)
    const [first, second] = screen.getAllByRole('button')

    expect(first).toHaveTextContent('SC line 1')
    expect(first).toHaveTextContent('GA line 1')
    expect(first).toHaveTextContent('Dominion Energy South Carolina')
    expect(first).toHaveTextContent('Georgia Power')
    expect(first).toHaveTextContent('1.3 mi') // distance_mi 1.25 -> 1 decimal
    expect(first).toHaveTextContent('10 days')

    expect(second).toHaveTextContent('SC line 2')
    expect(second).toHaveTextContent('GA line 2')
    expect(second).toHaveTextContent('2.3 mi')
    expect(second).toHaveTextContent('20 days')
  })

  it('calls onSelect with the clicked item overlap_id', () => {
    const onSelect = vi.fn()
    render(<OverlapList overlaps={makeOverlaps(3)} selectedId={null} onSelect={onSelect} />)

    fireEvent.click(screen.getByRole('button', { name: /SC line 2/ }))
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onSelect).toHaveBeenCalledWith('OVL_2')
  })

  it('marks only the selected item as pressed', () => {
    render(<OverlapList overlaps={makeOverlaps(3)} selectedId="OVL_3" onSelect={() => {}} />)

    expect(screen.getByRole('button', { name: /SC line 3/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /SC line 1/ })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getAllByRole('button', { pressed: true })).toHaveLength(1)
  })

  it('shows an empty-state message when there are no overlaps', () => {
    render(<OverlapList overlaps={[]} selectedId={null} onSelect={() => {}} />)
    expect(screen.queryAllByRole('button')).toHaveLength(0)
    expect(screen.getByText(/no overlapping projects/i)).toBeInTheDocument()
  })
})
