import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import LandingPage, { MAP_HREF } from './LandingPage'
import { PULSE_LINES, PULSE_LINE_OFFSET_SECONDS, PULSE_SPAN_SECONDS } from './LandingHero'

// Path-based on purpose: jsdom replaces the global URL, which node:fs rejects.
const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const readSource = (file: string) => readFileSync(resolve(SRC, file), 'utf8')

const SUBLINE = "Relay finds where neighboring utilities' planned transmission projects overlap, before the digging starts."
const FEATURE_TITLES = ['Visualize projects', 'Find overlaps', 'Prioritize opportunities', 'Estimate impact']

describe('LandingPage', () => {
  it('renders a single h1 with both headline lines', () => {
    render(<LandingPage />)
    const h1s = screen.getAllByRole('heading', { level: 1 })
    expect(h1s).toHaveLength(1)
    expect(h1s[0]).toHaveTextContent('Plan together.')
    expect(h1s[0]).toHaveTextContent('Build once.')
  })

  it('renders the subline exactly', () => {
    render(<LandingPage />)
    expect(screen.getByText(SUBLINE)).toBeInTheDocument()
  })

  it('links "Try the map" and "Get Started" to #/map by default', () => {
    render(<LandingPage />)
    expect(MAP_HREF).toBe('#/map')
    expect(screen.getByRole('link', { name: /try the map/i })).toHaveAttribute('href', '#/map')
    expect(screen.getByRole('link', { name: 'Get Started' })).toHaveAttribute('href', '#/map')
  })

  it('uses a custom mapHref when passed', () => {
    render(<LandingPage mapHref="/map" />)
    expect(screen.getByRole('link', { name: /try the map/i })).toHaveAttribute('href', '/map')
    expect(screen.getByRole('link', { name: 'Get Started' })).toHaveAttribute('href', '/map')
  })

  it('points "See how it works" and the nav anchors at sections that exist', () => {
    const { container } = render(<LandingPage />)
    expect(screen.getByRole('link', { name: 'See how it works' })).toHaveAttribute('href', '#product')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    for (const [label, id] of [['Product', 'product'], ['Data', 'data'], ['About', 'about']]) {
      expect(within(nav).getByRole('link', { name: label })).toHaveAttribute('href', `#${id}`)
      expect(container.querySelector(`#${id}`), id).not.toBeNull()
    }
  })

  it('has no login or sign-in anywhere', () => {
    const { container } = render(<LandingPage />)
    expect(container.textContent).not.toMatch(/log\s*-?\s*in|sign\s*-?\s*in/i)
  })

  it('renders the four feature titles in the #product row', () => {
    const { container } = render(<LandingPage />)
    const product = container.querySelector('#product') as HTMLElement
    for (const title of FEATURE_TITLES) expect(within(product).getByRole('heading', { name: title })).toBeInTheDocument()
  })

  it('shows the logo and the RELAY wordmark, and hides the illustration from assistive tech', () => {
    const { container } = render(<LandingPage />)
    const brand = screen.getByRole('link', { name: 'RELAY' })
    expect(brand.querySelector('img')).toHaveAttribute('src', '/relay-icon.svg')
    const art = container.querySelector('svg.landing-hero-art')
    expect(art).not.toBeNull()
    expect(art).toHaveAttribute('aria-hidden', 'true')
  })

  it('labels the nav "Primary"', () => {
    render(<LandingPage />)
    expect(screen.getByRole('navigation', { name: 'Primary' })).toBeInTheDocument()
  })
})

describe('landing page wiring', () => {
  it('is not wired into the app yet: main.tsx and App.tsx do not import LandingPage', () => {
    for (const file of ['main.tsx', 'App.tsx']) expect(readSource(file), file).not.toMatch(/LandingPage/)
  })
})

describe('landing page motion', () => {
  it('runs a chain of gold pulses along two wires, span by span, inside the decorative scene', () => {
    const { container } = render(<LandingPage />)
    const pulses = [...container.querySelectorAll('path.landing-hero-pulse')]
    const spans = pulses.length / PULSE_LINES.length
    expect(pulses.length).toBeGreaterThan(0)
    expect(Number.isInteger(spans)).toBe(true)
    for (const pulse of pulses) {
      expect(pulse).toHaveAttribute('pathLength', '100')
      expect(pulse.closest('svg')).toHaveAttribute('aria-hidden', 'true')
    }
    // Each span starts when the previous one ends; the second wire starts PULSE_LINE_OFFSET_SECONDS later.
    const delays = pulses.map((p) => parseFloat((p as SVGPathElement).style.animationDelay))
    const expected = PULSE_LINES.flatMap((_, line) =>
      Array.from({ length: spans }, (_, i) => line * PULSE_LINE_OFFSET_SECONDS + i * PULSE_SPAN_SECONDS))
    delays.forEach((d, i) => expect(d).toBeCloseTo(expected[i], 5))
  })

  it('switches every animation off for prefers-reduced-motion, and hides the pulses', () => {
    const css = readSource('landing.css')
    const reduced = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)', css.indexOf('/* Motion')))
    expect(reduced).toMatch(/\.landing \*[^{]*\{[^}]*animation:\s*none !important/)
    expect(reduced).toMatch(/transition:\s*none !important/)
    expect(reduced).toMatch(/\.landing-hero-pulses\s*\{\s*display:\s*none/)
  })

  it('keeps the pulse timing in landing.css in step with PULSE_SPAN_SECONDS (15% of a 4s cycle)', () => {
    const css = readSource('landing.css')
    expect(css).toMatch(/animation:landing-pulse 4s linear infinite/)
    expect(css).toMatch(/15%, 100% \{ stroke-dashoffset:-100; \}/)
    expect(PULSE_SPAN_SECONDS).toBeCloseTo(0.15 * 4, 5)
  })
})
