import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import BasemapToggle from './BasemapToggle'

// The dark theme's basemaps (basemapOptions('dark')), as before #45.
const DARK_OPTIONS = ['dark', 'satellite'] as const

it('renders both labeled buttons and exposes the active basemap', () => {
  const onChange = vi.fn()
  const { rerender } = render(<BasemapToggle options={DARK_OPTIONS} value="dark" onChange={onChange} />)
  expect(screen.getByRole('group', { name: 'Basemap' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Dark', pressed: true })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Satellite', pressed: false }))
  expect(onChange).toHaveBeenLastCalledWith('satellite')
  rerender(<BasemapToggle options={DARK_OPTIONS} value="satellite" onChange={onChange} />)
  expect(screen.getByRole('button', { name: 'Satellite', pressed: true })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Dark', pressed: false }))
  expect(onChange).toHaveBeenLastCalledWith('dark')
})

it('offers exactly the options it is given, in order: the light theme shows Light instead of Dark (#45)', () => {
  const onChange = vi.fn()
  render(<BasemapToggle options={['light', 'satellite']} value="light" onChange={onChange} />)
  const buttons = screen.getAllByRole('button')
  expect(buttons.map((b) => b.textContent)).toEqual(['Light', 'Satellite'])
  expect(screen.getByRole('button', { name: 'Light', pressed: true })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Dark' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Satellite', pressed: false }))
  expect(onChange).toHaveBeenLastCalledWith('satellite')
})
