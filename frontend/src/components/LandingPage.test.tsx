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

  it('points the nav anchors at sections that exist, and has only one call-to-action button in the hero', () => {
    const { container } = render(<LandingPage />)
    // "See how it works" was removed: it went to #product, the same place as the Product nav link.
    expect(screen.queryByRole('link', { name: /see how it works/i })).toBeNull()
    const actions = container.querySelector('.landing-actions')!
    expect(within(actions as HTMLElement).getAllByRole('link').map((a) => a.textContent?.trim())).toEqual(['Try the map'])
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

  it('shows the Relay wordmark logo, and hides the illustration from assistive tech', () => {
    const { container } = render(<LandingPage />)
    // The traced wordmark image (gold R + ELAY) is the whole brand link now; its alt text names it.
    const brand = screen.getByRole('link', { name: 'Relay' })
    expect(brand.querySelector('img')).toHaveAttribute('src', '/relay-logo.svg')
    expect(brand.querySelectorAll('img')).toHaveLength(1)
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
  // Root.test.tsx covers the routing itself; this pins that the app entry actually renders Root.
  it('is the app entry: main.tsx renders Root, which routes between LandingPage and App', () => {
    const main = readSource('main.tsx')
    expect(main).toMatch(/import Root from '\.\/Root\.tsx'/)
    expect(main).toMatch(/<Root \/>/)
    expect(main).not.toMatch(/<App \/>/)
    expect(readSource('Root.tsx')).toMatch(/LandingPage/)
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

describe('brand assets', () => {
  const PUBLIC = resolve(SRC, '..', 'public')
  it('uses the square gold R mark as the favicon and ships the full wordmark; the old icon is gone', () => {
    const indexHtml = readFileSync(resolve(SRC, '..', 'index.html'), 'utf8')
    expect(indexHtml).toMatch(/<link rel="icon" type="image\/svg\+xml" href="\/relay-mark\.svg" \/>/)
    const logo = readFileSync(resolve(PUBLIC, 'relay-logo.svg'), 'utf8')
    const mark = readFileSync(resolve(PUBLIC, 'relay-mark.svg'), 'utf8')
    expect(logo).toMatch(/viewBox="0 0 1407 313"/)
    // The mark is the logo's gold R path, unchanged, in a square frame.
    const goldPath = (svg: string) => svg.match(/<path d="([^"]+)" fill="#FFC928"/)![1]
    expect(goldPath(mark)).toBe(goldPath(logo))
    const [, , w, h] = mark.match(/viewBox="([^"]+)"/)![1].split(' ').map(Number)
    expect(w).toBe(h)
    expect(() => readFileSync(resolve(PUBLIC, 'relay-icon.svg'), 'utf8')).toThrow()
  })
})
