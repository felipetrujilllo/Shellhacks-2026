import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { Theme } from '../theme'
import BasemapToggle from './BasemapToggle'
import { basemapOptions, type BasemapId } from './basemaps'

const THEMES: Theme[] = ['dark', 'light']
// Each theme's own vector map (Dark Matter / Positron): where turning satellite off goes back to.
const THEME_VECTOR: Record<Theme, BasemapId> = { dark: 'dark', light: 'light' }

/** The picker as ProjectMap wires it: controlled, starting on the theme's own vector map. */
function Picker({ theme, onChange }: { theme: Theme; onChange: (id: BasemapId) => void }) {
  const options = basemapOptions(theme)
  const [value, setValue] = useState<BasemapId>(options[0])
  return <BasemapToggle options={options} value={value} onChange={(id) => { onChange(id); setValue(id) }} />
}

describe.each(THEMES)('BasemapToggle in the %s theme (#59)', (theme) => {
  const vector = THEME_VECTOR[theme]

  it('shows only the Satellite toggle: no Dark or Light button', () => {
    render(<BasemapToggle options={basemapOptions(theme)} value={vector} onChange={() => {}} />)
    const group = screen.getByRole('group', { name: 'Basemap' })
    expect(group).toHaveClass('map-control', 'map-segmented')
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(['Satellite'])
    expect(screen.queryByRole('button', { name: 'Dark' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Light' })).not.toBeInTheDocument()
  })

  it('starts not pressed, turns satellite on with one click and back to the theme\'s vector map with a second', () => {
    const onChange = vi.fn()
    render(<Picker theme={theme} onChange={onChange} />)
    const satellite = screen.getByRole('button', { name: 'Satellite' })
    expect(satellite).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(satellite)
    expect(onChange).toHaveBeenLastCalledWith('satellite')
    expect(satellite).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(satellite)
    expect(onChange).toHaveBeenLastCalledWith(vector)
    expect(satellite).toHaveAttribute('aria-pressed', 'false')
  })
})
