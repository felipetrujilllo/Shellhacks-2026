import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { THEME_STORAGE_KEY, applyTheme, useTheme } from '../theme'
import ThemeToggle from './ThemeToggle'

// The toggle as App wires it: the real useTheme() state and the real DOM/storage side effects.
function WiredToggle() {
  const [theme, toggle] = useTheme()
  return <ThemeToggle theme={theme} onToggle={toggle} />
}

function memoryStorage(): Storage {
  const data = new Map<string, string>()
  return {
    get length() { return data.size },
    clear: () => data.clear(),
    getItem: (key: string) => data.get(key) ?? null,
    key: (i: number) => [...data.keys()][i] ?? null,
    removeItem: (key: string) => { data.delete(key) },
    setItem: (key: string, value: string) => { data.set(key, String(value)) },
  }
}

const toggle = () => screen.getByRole('button', { name: 'Light theme' })
const icon = () => toggle().querySelector('[data-icon]')?.getAttribute('data-icon')

describe('ThemeToggle (#45)', () => {
  let storage: Storage
  beforeEach(() => {
    storage = memoryStorage()
    vi.stubGlobal('localStorage', storage)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    document.documentElement.removeAttribute('data-theme')
  })

  it('is a toggle button named "Light theme", not pressed in the dark theme, offering the switch to light', () => {
    render(<WiredToggle />)
    expect(toggle()).toHaveAttribute('aria-pressed', 'false')
    expect(toggle()).toHaveAttribute('type', 'button')
    expect(toggle()).toHaveAttribute('title', 'Switch to light theme')
    expect(icon()).toBe('sun')
  })

  it('clicking sets data-theme on <html>, persists the choice, and flips the pressed state, tooltip and icon', () => {
    render(<WiredToggle />)
    fireEvent.click(toggle())
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    expect(storage.getItem(THEME_STORAGE_KEY)).toBe('light')
    expect(screen.getByRole('button', { name: 'Light theme', pressed: true })).toBe(toggle())
    expect(toggle()).toHaveAttribute('title', 'Switch to dark theme')
    expect(icon()).toBe('moon')

    fireEvent.click(toggle())
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(storage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(screen.getByRole('button', { name: 'Light theme', pressed: false })).toBe(toggle())
    expect(toggle()).toHaveAttribute('title', 'Switch to light theme')
    expect(icon()).toBe('sun')
  })

  it('starts pressed when the page already shows the light theme (applied before the first render)', () => {
    applyTheme('light')
    render(<WiredToggle />)
    expect(toggle()).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(toggle())
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
  })

  it('still switches the theme when the browser refuses storage', () => {
    const refuse = () => { throw new DOMException('The operation is insecure.', 'SecurityError') }
    vi.stubGlobal('localStorage', { getItem: refuse, setItem: refuse, removeItem: refuse, clear: refuse, key: refuse, get length() { return refuse() } })
    render(<WiredToggle />)
    expect(() => fireEvent.click(toggle())).not.toThrow()
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    expect(toggle()).toHaveAttribute('aria-pressed', 'true')
  })

  it('reports clicks to its owner and renders whatever theme it is given', () => {
    const onToggle = vi.fn()
    const { rerender } = render(<ThemeToggle theme="dark" onToggle={onToggle} />)
    fireEvent.click(toggle())
    expect(onToggle).toHaveBeenCalledTimes(1)
    expect(toggle()).toHaveAttribute('aria-pressed', 'false') // presentational: its owner holds the state
    rerender(<ThemeToggle theme="light" onToggle={onToggle} />)
    expect(toggle()).toHaveAttribute('aria-pressed', 'true')
  })
})
