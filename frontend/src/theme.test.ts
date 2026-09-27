// The palette lives in theme.css only. These tests keep it that way: workspace.css and the map
// code read tokens instead of hard-coding colors, every token is documented, and the map's
// themeColor() fallbacks can't drift from theme.css.
/// <reference types="node" />
import { Color, latest, normalizePropertyExpression } from '@maplibre/maplibre-gl-style-spec'
import { readFileSync, readdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { projectsToGeoJSON } from './geo'
import { themeColor } from './theme'
import type { Project } from './types'

// Path-based on purpose: jsdom replaces the global URL, which node:fs rejects.
const SRC = dirname(fileURLToPath(import.meta.url))
const read = (file: string) => readFileSync(resolve(SRC, file), 'utf8')

const stripCssComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, '')
const COLOR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\b(?:white|black)\b(?![-\w])/

const themeCss = read('theme.css')
const workspaceCss = read('workspace.css')

/** theme.css's tokens: name -> { value, comment } (comment is the same-line comment, if any). */
function themeTokens(): Map<string, { value: string; comment: string }> {
  const tokens = new Map<string, { value: string; comment: string }>()
  for (const line of themeCss.split('\n')) {
    const m = line.match(/^\s*(--[\w-]+)\s*:\s*([^;]+);(.*)$/)
    if (m) tokens.set(m[1], { value: m[2].trim(), comment: m[3].trim() })
  }
  return tokens
}

// Every non-test source file under src/, as text (same glob as colors.test.ts).
const sources = import.meta.glob<string>(['./**/*.{ts,tsx}', '!./**/*.test.{ts,tsx}'], {
  query: '?raw',
  import: 'default',
  eager: true,
})

// Tokens the map reads through themeColor() (MapLibre paint can't use var()).
const MAP_TOKENS = [
  '--color-utility-desc',
  '--color-utility-gpc',
  '--color-utility-other',
  '--color-overlap',
  '--color-overlap-selected',
  '--color-point-stroke',
  '--color-legend-low-confidence',
  '--color-halo-dark',
  '--color-halo-light',
]
const MAP_FILES = ['./colors.ts', './components/mapStyle.ts', './components/MapLegend.tsx', './components/ProjectMap.tsx']

const THEME_COLOR_CALL = /themeColor\(\s*'(--[\w-]+)'\s*,\s*'([^']+)'\s*\)/g

afterEach(() => {
  document.documentElement.removeAttribute('style')
  vi.restoreAllMocks()
})

describe('themeColor', () => {
  it('returns the CSS variable set on the document root, trimmed', () => {
    document.documentElement.style.setProperty('--test-color', '  #123456 ')
    expect(themeColor('--test-color', '#000000')).toBe('#123456')
  })

  it('trims whitespace a browser keeps around a custom property value', () => {
    // jsdom already trims custom properties; real browsers may not, so feed the raw value.
    vi.spyOn(window, 'getComputedStyle').mockReturnValue({ getPropertyValue: () => '  #abcdef\n' } as unknown as CSSStyleDeclaration)
    expect(themeColor('--test-color', '#000000')).toBe('#abcdef')
  })

  it('returns the fallback when the variable is unset', () => {
    expect(themeColor('--test-unset-color', '#fedcba')).toBe('#fedcba')
  })
})

describe('theme.css', () => {
  it('declares every token in one :root rule, each with a one-line comment saying where it is used', () => {
    const rules = [...stripCssComments(themeCss).matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    expect(rules).toHaveLength(1)
    expect(rules[0][1].split(',').map((s) => s.trim())).toContain(':root')
    const declared = rules[0][2].match(/--[\w-]+\s*:/g) ?? []

    const tokens = themeTokens()
    expect(tokens.size).toBeGreaterThan(50)
    expect(declared).toHaveLength(tokens.size) // every declaration is on its own line, parsed above
    for (const [name, { value, comment }] of tokens) {
      expect(name, name).toMatch(/^--color-/)
      expect(value, name).toMatch(COLOR_LITERAL)
      expect(comment, `${name} needs a one-line comment`).toMatch(/^\/\*\s*\S.*\*\/$/)
    }
  })

  it('tells the reader to edit theme.css only to try a new color scheme', () => {
    expect(themeCss).toMatch(/to try a new color scheme, edit theme\.css only/i)
  })

  it('is the only stylesheet with color literals', () => {
    const stylesheets = (readdirSync(SRC, { recursive: true }) as string[]).filter((f) => f.endsWith('.css'))
    expect(stylesheets).toEqual(expect.arrayContaining(['theme.css', 'workspace.css', 'index.css']))
    for (const file of stylesheets.filter((f) => f !== 'theme.css')) {
      expect(stripCssComments(read(file)).match(COLOR_LITERAL), file).toBeNull()
    }
  })

  it('is imported by main.tsx before anything else', () => {
    const firstImport = read('main.tsx').match(/^import\s+(?:[^'"]*from\s+)?['"]([^'"]+)['"]/m)
    expect(firstImport?.[1]).toBe('./theme.css')
  })
})

describe('workspace.css', () => {
  it('has no hex, rgb() or hsl() color literals outside comments', () => {
    const css = stripCssComments(workspaceCss)
    expect(css).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(css).not.toMatch(/rgba?\(/)
    expect(css).not.toMatch(/hsla?\(/)
    expect(css.match(COLOR_LITERAL)).toBeNull()
    expect(css).toMatch(/var\(--color-accent\)/) // sanity: it really reads the palette
  })

  it('only uses tokens that theme.css or its own scoped aliases define', () => {
    const css = stripCssComments(workspaceCss)
    const theme = themeTokens()
    const local = new Set([...css.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]))
    // The palette namespace belongs to theme.css: no stylesheet redefines a --color-* token.
    expect([...local].filter((name) => name.startsWith('--color-'))).toEqual([])
    const used = new Set([...css.matchAll(/var\((--[\w-]+)/g)].map((m) => m[1]))
    expect(used.size).toBeGreaterThan(50)
    for (const name of used) {
      expect(theme.has(name) || local.has(name), `${name} is not defined`).toBe(true)
    }
  })

  it('keeps the short aliases pointing at the palette, with the sidebar card redefining them for its dark theme', () => {
    const css = stripCssComments(workspaceCss)
    // All declarations of the rules whose selector is exactly `selector`.
    const rule = (selector: string) =>
      [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter((m) => m[1].trim() === selector).map((m) => m[2]).join(';')
    expect(rule('.workspace')).toMatch(/--ink:\s*var\(--color-text\)/)
    expect(rule('.workspace')).toMatch(/--accent:\s*var\(--color-accent\)/)
    expect(rule('.sidebar-panel')).toMatch(/--ink:\s*var\(--color-sidebar-text\)/)
    expect(rule('.sidebar-panel')).toMatch(/--muted:\s*var\(--color-sidebar-muted\)/)
    expect(rule('.sidebar-panel')).toMatch(/--rule:\s*var\(--color-sidebar-rule\)/)
  })
})

describe('map colors', () => {
  it('reads every map token through themeColor() with a fallback equal to theme.css', () => {
    const theme = themeTokens()
    const called = new Set<string>()
    for (const [path, text] of Object.entries(sources)) {
      if (path === './theme.ts') continue
      const calls = [...text.matchAll(THEME_COLOR_CALL)]
      // Every call uses literal arguments, so none escapes this check.
      expect((text.match(/themeColor\(/g) ?? []).length, path).toBe(calls.length)
      for (const [, name, fallback] of calls) {
        called.add(name)
        expect(theme.get(name)?.value, `${path}: ${name} is not in theme.css`).toBeDefined()
        expect(fallback, `${path}: ${name} fallback drifted from theme.css`).toBe(theme.get(name)?.value)
      }
    }
    expect([...called].sort()).toEqual(expect.arrayContaining(MAP_TOKENS))
  })

  it('leaves no hex literals in the map code except as themeColor() fallbacks', () => {
    for (const path of MAP_FILES) {
      const text = sources[path]
      expect(text, path).toBeDefined()
      expect(text.replace(THEME_COLOR_CALL, '').match(/#[0-9a-fA-F]{3,8}\b/g), path).toBeNull()
    }
  })

  it('changing --color-utility-desc changes the color the map style and swatches use', async () => {
    document.documentElement.style.setProperty('--color-utility-desc', '#123456')
    document.documentElement.style.setProperty('--color-overlap', '#abcdef')
    vi.resetModules() // the map reads its tokens when its modules load, as on page load
    const { DESC, GPC, utilityColor } = await import('./colors')
    const { OVERLAP_COLOR, projectLayers } = await import('./components/mapStyle')

    const desc = { ...projectFixture, utility: DESC }
    const { lines } = projectLayers(null, '#ffffff')
    expect(lineColor((lines as { paint: Record<string, unknown> }).paint['line-color'], desc)).toBe(Color.parse('#123456')!.toString())
    expect(utilityColor(DESC)).toBe('#123456')
    expect(OVERLAP_COLOR).toBe('#abcdef')
    // Unset tokens still fall back to today's colors.
    expect(utilityColor(GPC)).toBe(themeTokens().get('--color-utility-gpc')?.value)
  })
})

const projectFixture: Project = {
  project_id: 'P1',
  utility: 'Georgia Power',
  state: 'SC',
  project_name: 'P1',
  name_a: 'A',
  lat_a: 32.1,
  lon_a: -81.1,
  name_b: 'B',
  lat_b: 32.3,
  lon_b: -81.5,
  lat_center: 32.2,
  lon_center: -81.3,
  in_service_date: '2026-01-01',
  est_cost_usd: null,
  location_confidence: 'confirmed',
}

/** Evaluate a line-color paint value for `project`'s map feature with MapLibre's own evaluator. */
function lineColor(value: unknown, project: Project): string {
  const feature = projectsToGeoJSON([project]).features[0]
  const spec = (latest as unknown as Record<string, Record<string, never>>).paint_line['line-color']
  const expr = normalizePropertyExpression(value as never, 'line-color', spec)
  const result: unknown = expr.evaluate({ zoom: 8 }, { type: feature.geometry.type, properties: feature.properties })
  return result instanceof Color ? result.toString() : String(result)
}
