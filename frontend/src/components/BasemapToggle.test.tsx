import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import BasemapToggle from './BasemapToggle'

it('renders both labeled buttons and exposes the active basemap', () => {
  const onChange = vi.fn()
  const { rerender } = render(<BasemapToggle value="dark" onChange={onChange} />)
  expect(screen.getByRole('group', { name: 'Basemap' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Dark', pressed: true })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Satellite', pressed: false }))
  expect(onChange).toHaveBeenLastCalledWith('satellite')
  rerender(<BasemapToggle value="satellite" onChange={onChange} />)
  expect(screen.getByRole('button', { name: 'Satellite', pressed: true })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Dark', pressed: false }))
  expect(onChange).toHaveBeenLastCalledWith('dark')
})
