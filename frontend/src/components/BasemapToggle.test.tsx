import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import BasemapToggle from './BasemapToggle'
import { BASEMAP_OPTIONS } from './basemaps'

const pressed = () => screen.getAllByRole('button').map((b) => b.getAttribute('aria-pressed'))

it('is a labeled "Basemap" group with Dark, Light and Satellite buttons, in that order, with moon/sun/layers icons', () => {
  render(<BasemapToggle options={BASEMAP_OPTIONS} value="dark" onChange={() => {}} />)
  const group = screen.getByRole('group', { name: 'Basemap' })
  expect(group).toHaveClass('map-control', 'map-segmented')
  const buttons = screen.getAllByRole('button')
  expect(buttons.map((b) => b.textContent)).toEqual(['Dark', 'Light', 'Satellite'])
  expect(buttons.map((b) => b.getAttribute('type'))).toEqual(['button', 'button', 'button'])
  expect(buttons.map((b) => b.querySelector('svg')?.getAttribute('data-icon'))).toEqual(['moon', 'sun', 'layers'])
})

it('presses only the option matching value', () => {
  const { rerender } = render(<BasemapToggle options={BASEMAP_OPTIONS} value="dark" onChange={() => {}} />)
  expect(pressed()).toEqual(['true', 'false', 'false'])
  rerender(<BasemapToggle options={BASEMAP_OPTIONS} value="light" onChange={() => {}} />)
  expect(pressed()).toEqual(['false', 'true', 'false'])
  rerender(<BasemapToggle options={BASEMAP_OPTIONS} value="satellite" onChange={() => {}} />)
  expect(pressed()).toEqual(['false', 'false', 'true'])
})

it('reports each click as that option\'s id, including a click on the pressed one, and leaves the state to its owner', () => {
  const onChange = vi.fn()
  render(<BasemapToggle options={BASEMAP_OPTIONS} value="satellite" onChange={onChange} />)
  fireEvent.click(screen.getByRole('button', { name: 'Light' }))
  expect(onChange).toHaveBeenLastCalledWith('light')
  fireEvent.click(screen.getByRole('button', { name: 'Dark' }))
  expect(onChange).toHaveBeenLastCalledWith('dark')
  fireEvent.click(screen.getByRole('button', { name: 'Satellite' }))
  expect(onChange).toHaveBeenLastCalledWith('satellite')
  expect(onChange).toHaveBeenCalledTimes(3)
  // Controlled: nothing changes until the owner passes a new value.
  expect(pressed()).toEqual(['false', 'false', 'true'])
})

it('offers exactly the options it is given, in order', () => {
  render(<BasemapToggle options={['light', 'satellite']} value="light" onChange={() => {}} />)
  expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(['Light', 'Satellite'])
  expect(screen.queryByRole('button', { name: 'Dark' })).not.toBeInTheDocument()
})
