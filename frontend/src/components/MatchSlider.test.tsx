/// <reference types="node" />
import { fireEvent, render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { DEFAULT_MIN_MATCH, MATCH_STEPS, matchLabel } from '../matchFilter'
import MatchSlider from './MatchSlider'

// Path-based, as in theme.test.ts (vitest stubs CSS imports, and jsdom replaces the global URL).
const workspaceCss = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../workspace.css'), 'utf8')

const slider = () => screen.getByRole('slider', { name: 'Minimum match' }) as HTMLInputElement

/** What the browser does after moving a native range (drag or key): it fires `input` with the new value. */
function moved(input: HTMLInputElement, value = input.value) {
  fireEvent.input(input, { target: { value } })
}

/** The slider as App uses it: controlled, holding the value it reports. */
function Controlled({ onChange, initial = DEFAULT_MIN_MATCH }: { onChange: (min: number) => void; initial?: number }) {
  const [value, setValue] = useState(initial)
  return <MatchSlider value={value} onChange={(min) => { setValue(min); onChange(min) }} />
}

describe('MatchSlider (#54)', () => {
  it('renders a range input labelled "Minimum match", 0–90 in steps of 5 (one stop per MATCH_STEPS entry)', () => {
    render(<MatchSlider value={DEFAULT_MIN_MATCH} onChange={() => {}} />)
    const input = slider()
    expect(input).toHaveAttribute('type', 'range')
    expect(input).toHaveAccessibleName('Minimum match')
    expect([input.min, input.max, input.step]).toEqual(['0', '90', '5'])
    // Exactly the MATCH_STEPS stops, as whole percents.
    const stops = Array.from({ length: (90 - 0) / 5 + 1 }, (_, i) => i * 5)
    expect(stops.map((pct) => pct / 100)).toEqual(MATCH_STEPS)
  })

  it('shows the value next to the track with matchLabel: "All" at the default, "≥ 70% match" at 0.7', () => {
    const { rerender } = render(<MatchSlider value={0} onChange={() => {}} />)
    expect(slider()).toHaveValue('0')
    expect(screen.getByText('All')).toBeInTheDocument()
    expect(slider()).toHaveAttribute('aria-valuetext', 'All')

    rerender(<MatchSlider value={0.7} onChange={() => {}} />)
    expect(slider()).toHaveValue('70')
    expect(screen.getByText('≥ 70% match')).toBeInTheDocument()
    expect(slider()).toHaveAttribute('aria-valuetext', matchLabel(0.7))
    expect(screen.queryByText('All')).not.toBeInTheDocument()
  })

  it('calls onChange with the exact MATCH_STEPS value for every stop, live on input (no Apply step)', () => {
    const onChange = vi.fn()
    render(<MatchSlider value={0} onChange={onChange} />)
    MATCH_STEPS.forEach((step, i) => {
      if (i === 0) return // already at 0: the browser fires nothing
      fireEvent.input(slider(), { target: { value: String(i * 5) } })
      expect(onChange).toHaveBeenLastCalledWith(step)
      // The very same number as the stop (e.g. 0.7, never 0.7000000000000001).
      expect(Object.is(onChange.mock.lastCall![0], MATCH_STEPS[i])).toBe(true)
    })
    expect(onChange).toHaveBeenCalledTimes(MATCH_STEPS.length - 1)
    expect(screen.queryByRole('button')).not.toBeInTheDocument() // nothing to apply
  })

  it('keyboard: the arrow keys step by 5% and Home/End jump to All/90%, as the browser moves a native range', () => {
    // jsdom does not move a range on key presses; the browser does it with the input's own step,
    // min and max (arrows = stepUp/stepDown, Home/End = min/max), then fires input. Replay that.
    const onChange = vi.fn()
    render(<Controlled onChange={onChange} initial={0.5} />)
    const input = slider()

    input.stepUp() // ArrowRight / ArrowUp
    moved(input)
    expect(onChange).toHaveBeenLastCalledWith(0.55)
    expect(screen.getByText('≥ 55% match')).toBeInTheDocument()

    input.stepDown(); input.stepDown() // ArrowLeft / ArrowDown, twice
    moved(input)
    expect(onChange).toHaveBeenLastCalledWith(0.45)

    moved(input, input.max) // End
    expect(onChange).toHaveBeenLastCalledWith(0.9)
    expect(screen.getByText('≥ 90% match')).toBeInTheDocument()

    input.stepUp() // past the end: stays on the last stop
    moved(input)
    expect(input).toHaveValue('90')

    moved(input, input.min) // Home
    expect(onChange).toHaveBeenLastCalledWith(0)
    expect(screen.getByText('All')).toBeInTheDocument()
    for (const [value] of onChange.mock.calls) expect(MATCH_STEPS).toContain(value)
  })

  it('is its own floating map control (the toolbar\'s .map-control style)', () => {
    render(<MatchSlider value={0} onChange={() => {}} />)
    expect(slider().parentElement).toHaveClass('match-slider', 'map-control')
  })

  it('fails loud on a value that is not a slider stop', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {}) // React logs the render error
    expect(() => render(<MatchSlider value={0.07} onChange={() => {}} />)).toThrow(RangeError)
    vi.restoreAllMocks()
  })
})

describe('MatchSlider placement and style (workspace.css, #54)', () => {
  const css = workspaceCss.replace(/\/\*[\s\S]*?\*\//g, '')
  /** A rule body's declarations, property -> value. */
  const declarations = (body: string) => new Map(body.split(';').map((d) => d.split(':').map((s) => s.trim())).filter((d) => d.length === 2) as [string, string][])
  /** The declarations of the base (not @container / @media) rules whose selector is exactly `selector`, later ones winning. */
  function baseRule(selector: string) {
    const base = css.replace(/@(?:media|container)[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}/g, '')
    const rules = [...base.matchAll(new RegExp(`(?:^|[\\r\\n}])\\s*${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')} \\{([^{}]*)\\}`, 'g'))]
    expect(rules.length, `a base "${selector}" rule`).toBeGreaterThan(0)
    return new Map(rules.flatMap((m) => [...declarations(m[1])]))
  }

  it('sits at the top right, on the toolbar\'s row, left of the zoom buttons', () => {
    const rule = baseRule('.match-slider')
    expect(rule.get('position')).toBe('absolute')
    expect(rule.get('top')).toBe('var(--space-4)') // the top-left toolbar's row
    // MapLibre's top-right zoom group is 10px from the edge and 29px wide: stay clear of it, like the toolbar's padding-right.
    expect(rule.get('right')).toBe('48px')
    expect(parseFloat(rule.get('right')!)).toBeGreaterThan(10 + 29)
    expect(rule.has('left')).toBe(false)
    // Same height as the toolbar's Fit to data button (min-h-11), so the two rows line up.
    expect(rule.get('min-height')).toBe('44px')
  })

  /** Every block of an at-rule (e.g. `@media(max-width:700px)`), selector -> declarations, later blocks winning. */
  function atRules(prelude: RegExp) {
    const blocks = [...css.matchAll(new RegExp(`${prelude.source}\\s*\\{((?:[^{}]*\\{[^{}]*\\})*)[^{}]*\\}`, 'g'))]
    expect(blocks.length, `an ${prelude.source} rule`).toBeGreaterThan(0)
    const rules = new Map<string, Map<string, string>>()
    for (const block of blocks) {
      for (const m of block[1].matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
        const selector = m[1].trim()
        rules.set(selector, new Map([...(rules.get(selector) ?? []), ...declarations(m[2])]))
      }
    }
    return rules
  }

  // Measured in headless Edge (#54 re-gate): the toolbar's first row ends 379px from the map's left edge at every width
  // until it wraps, and the slider is 216px wide on that row. MapLibre's zoom group is 10px from the right, 29px wide.
  const TOOLBAR_RIGHT = 379
  const SLIDER_WIDTH = 216
  const GAP = 8

  it('stays on the toolbar\'s row for every map wider than the narrow breakpoint, without touching the toolbar', () => {
    expect(baseRule('.workspace-map').get('container-type')).toBe('inline-size') // the map is the query container
    const breakpoint = Number(css.match(/@container \(max-width:(\d+)px\)/)?.[1])
    expect(breakpoint, 'a narrow-map @container breakpoint').toBeGreaterThan(0)
    const right = parseFloat(baseRule('.match-slider').get('right')!)
    const narrowestRowOneMap = breakpoint + 1
    // The slider's left edge on the narrowest map that keeps it on row 1 is still clear of the toolbar.
    expect(narrowestRowOneMap - right - SLIDER_WIDTH).toBeGreaterThanOrEqual(TOOLBAR_RIGHT + GAP)
    // And a 1024px window with the sidebar open (a 660px map) keeps it on row 1: the case that used to overlap.
    expect(660).toBeGreaterThan(breakpoint)
  })

  it('on a narrow map in a wider-than-phone window moves to the bottom-left corner, away from the Legend popover and the notice', () => {
    const slider = atRules(/@container \(max-width:\d+px\)/).get('.match-slider')!
    expect(slider.get('top')).toBe('auto')
    expect(slider.get('bottom')).toBe('var(--space-3)')
    expect(slider.get('left')).toBe('var(--space-4)')
    expect(slider.get('right')).toBe('auto')
    expect(slider.get('max-width')).toBe('calc(100% - 32px)') // never wider than the map
    // A full-height selection panel stops (160 - 112)px above the map's bottom; the slider (12px up, min-height tall) ends there.
    const panel = baseRule('.selection-panel')
    const panelGap = Number(panel.get('max-height')!.match(/calc\(100% - (\d+)px\)/)![1]) - parseFloat(panel.get('top')!)
    const space3 = 12 // --space-3 (theme.css)
    expect(space3 + parseFloat(slider.get('min-height')!)).toBeLessThanOrEqual(panelGap)
  })

  it('on a phone keeps it on the second row, left of the zoom column, above the phone notice', () => {
    const phone = atRules(/@media\(max-width:700px\)/)
    const slider = phone.get('.match-slider')!
    expect(slider.get('top')).toBe('72px') // toolbar top 16 + its 48px first row + an 8px gap
    expect(slider.get('bottom')).toBe('auto')
    expect(slider.get('right')).toBe('48px')
    expect(slider.get('left')).toBe('auto')
    expect(slider.get('max-width')).toBe('calc(100% - 170px)') // never reaches the Legend button wrapped at the left
    // The phone rule already puts the notice at 125px and the selection panel at the bottom: the slider ends above the notice.
    const noticeTop = parseFloat(phone.get('.workspace-notice')!.get('top')!)
    expect(parseFloat(slider.get('top')!) + parseFloat(slider.get('min-height')!)).toBeLessThan(noticeTop)
    expect(phone.get('.selection-panel')!.get('top')).toBe('auto')
  })

  it('never moves the upload notice: only the pre-existing phone rule positions it', () => {
    expect(baseRule('.workspace-notice').get('top')).toBe('76px')
    expect(atRules(/@container \(max-width:\d+px\)/).has('.workspace-notice')).toBe(false)
  })

  it('reads its colors from theme tokens: the navy map chip, and the gold accent for the thumb and the active track', () => {
    const rule = baseRule('.match-slider')
    expect(rule.get('background')).toBe('var(--color-map-context-bg)')
    expect(rule.get('color')).toBe('var(--color-map-context-text)')
    expect(baseRule('.match-slider input::-webkit-slider-runnable-track').get('background'))
      .toBe('linear-gradient(to right,var(--color-accent) var(--match-fill),var(--color-map-context-divider) var(--match-fill))')
    expect(baseRule('.match-slider input::-moz-range-progress').get('background')).toBe('var(--color-accent)')
    for (const thumb of ['.match-slider input::-webkit-slider-thumb', '.match-slider input::-moz-range-thumb']) {
      const t = baseRule(thumb)
      expect(t.get('background'), thumb).toBe('var(--color-accent)')
      expect(t.get('border-radius'), thumb).toBe('50%')
    }
  })

  it('fills the active track up to the thumb (--match-fill, 0% at All, 100% at 90%)', () => {
    const { rerender } = render(<MatchSlider value={0} onChange={() => {}} />)
    expect(slider().style.getPropertyValue('--match-fill')).toBe('0%')
    rerender(<MatchSlider value={0.45} onChange={() => {}} />)
    expect(slider().style.getPropertyValue('--match-fill')).toBe('50%')
    rerender(<MatchSlider value={0.9} onChange={() => {}} />)
    expect(slider().style.getPropertyValue('--match-fill')).toBe('100%')
  })
})