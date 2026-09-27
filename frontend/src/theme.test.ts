// The palette lives in theme.css only. These tests keep it that way: workspace.css and the map
// code read tokens instead of hard-coding colors, every token is documented, and the map's
// themeColor() fallbacks can't drift from theme.css.
/// <reference types="node" />
import { Color, latest, normalizePropertyExpression } from '@maplibre/maplibre-gl-style-spec'
import { readFileSync, readdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BASEMAPS } from './components/basemaps'
import { projectsToGeoJSON } from './geo'
import { THEME_STORAGE_KEY, applyTheme, currentTheme, getInitialTheme, storeTheme, themeColor, type Theme } from './theme'
import type { Project } from './types'

// Path-based on purpose: jsdom replaces the global URL, which node:fs rejects.
const SRC = dirname(fileURLToPath(import.meta.url))
const read = (file: string) => readFileSync(resolve(SRC, file), 'utf8')

const stripCssComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, '')
const COLOR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\b(?:white|black)\b(?![-\w])/

const themeCss = read('theme.css')
const workspaceCss = read('workspace.css')

type Tokens = Map<string, { value: string; comment: string }>
const THEMES: Theme[] = ['dark', 'light']

/** theme.css's rules in order: the selector list (comments stripped) and the raw body. */
const themeRules = [...themeCss.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
  selectors: stripCssComments(m[1]).split(',').map((s) => s.trim()),
  body: m[2],
}))
// The dark theme is the default :root rule; the light theme is the rule applyTheme('light') switches on (#45).
const DARK_SELECTORS = [':root', '::backdrop']
const LIGHT_SELECTORS = [':root[data-theme="light"]', '[data-theme="light"] ::backdrop']

/** A rule's declarations: name -> { value, comment } (comment is the same-line comment, if any). */
function ruleTokens(selectors: string[]): Tokens {
  const rule = themeRules.find((r) => r.selectors.join(',') === selectors.join(','))
  if (!rule) throw new Error(`theme.css has no rule for ${selectors.join(', ')}`)
  const tokens: Tokens = new Map()
  for (const line of rule.body.split('\n')) {
    const m = line.match(/^\s*(--[\w-]+)\s*:\s*([^;]+);(.*)$/)
    if (m) tokens.set(m[1], { value: m[2].trim(), comment: m[3].trim() })
  }
  return tokens
}
const darkDeclarations = ruleTokens(DARK_SELECTORS)
const lightDeclarations = ruleTokens(LIGHT_SELECTORS)

/** The tokens in effect in `theme`, as the cascade resolves them: the light rule overrides :root. */
function themeTokens(theme: Theme = 'dark'): Tokens {
  return theme === 'dark' ? darkDeclarations : new Map([...darkDeclarations, ...lightDeclarations])
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

describe('theme switching (#45)', () => {
  /** A fresh in-memory localStorage holding `entries`. */
  function memoryStorage(entries: Record<string, string> = {}): Storage {
    const data = new Map(Object.entries(entries))
    return {
      get length() { return data.size },
      clear: () => data.clear(),
      getItem: (key: string) => data.get(key) ?? null,
      key: (i: number) => [...data.keys()][i] ?? null,
      removeItem: (key: string) => { data.delete(key) },
      setItem: (key: string, value: string) => { data.set(key, String(value)) },
    }
  }
  /** A browser that refuses site data (private window, blocked storage): every call throws. */
  function blockedStorage(): Storage {
    const refuse = () => { throw new DOMException('The operation is insecure.', 'SecurityError') }
    return { get length() { return refuse() }, clear: refuse, getItem: refuse, key: refuse, removeItem: refuse, setItem: refuse }
  }
  /** The OS preference: 'light' or 'dark' answers prefers-color-scheme; 'none' matches neither query. */
  function prefers(scheme: 'light' | 'dark' | 'none') {
    vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
      matches: query === `(prefers-color-scheme: ${scheme})`,
      media: query, onchange: null, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    })))
  }
  afterEach(() => {
    vi.unstubAllGlobals()
    document.documentElement.removeAttribute('data-theme')
  })

  it('getInitialTheme returns the stored choice first, whatever the OS prefers', () => {
    prefers('dark')
    vi.stubGlobal('localStorage', memoryStorage({ [THEME_STORAGE_KEY]: 'light' }))
    expect(getInitialTheme()).toBe('light')
    prefers('light')
    vi.stubGlobal('localStorage', memoryStorage({ [THEME_STORAGE_KEY]: 'dark' }))
    expect(getInitialTheme()).toBe('dark')
  })

  it('getInitialTheme follows prefers-color-scheme when nothing is stored', () => {
    vi.stubGlobal('localStorage', memoryStorage())
    prefers('light')
    expect(getInitialTheme()).toBe('light')
    prefers('dark')
    expect(getInitialTheme()).toBe('dark')
  })

  it('getInitialTheme falls back to dark with no stored choice and no OS preference', () => {
    vi.stubGlobal('localStorage', memoryStorage())
    prefers('none')
    expect(getInitialTheme()).toBe('dark')
    vi.stubGlobal('matchMedia', undefined) // jsdom and other non-browsers have no matchMedia
    expect(getInitialTheme()).toBe('dark')
  })

  it('getInitialTheme ignores a stored value that is not a theme', () => {
    prefers('light')
    for (const garbage of ['blue', 'LIGHT', '"light"', '']) {
      vi.stubGlobal('localStorage', memoryStorage({ [THEME_STORAGE_KEY]: garbage }))
      expect(getInitialTheme(), garbage).toBe('light')
    }
  })

  it('getInitialTheme tolerates localStorage throwing: it uses the OS preference, else dark', () => {
    const storage = blockedStorage()
    vi.stubGlobal('localStorage', storage)
    expect(() => storage.getItem(THEME_STORAGE_KEY)).toThrow() // the mock really throws
    prefers('light')
    expect(getInitialTheme()).toBe('light')
    prefers('none')
    expect(getInitialTheme()).toBe('dark')
  })

  it('getInitialTheme tolerates the localStorage getter itself throwing', () => {
    // Some browsers throw on touching window.localStorage at all when site data is blocked.
    const original = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, get: () => { throw new DOMException('denied', 'SecurityError') } })
    try {
      expect(() => localStorage).toThrow() // the getter really throws
      prefers('light')
      expect(getInitialTheme()).toBe('light')
      expect(storeTheme('dark')).toBe(false)
    } finally {
      if (original) Object.defineProperty(globalThis, 'localStorage', original)
      else delete (globalThis as { localStorage?: Storage }).localStorage
    }
  })

  it('applyTheme sets data-theme on <html>, which currentTheme reads back (dark when unset)', () => {
    expect(currentTheme()).toBe('dark')
    applyTheme('light')
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    expect(currentTheme()).toBe('light')
    applyTheme('dark')
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(currentTheme()).toBe('dark')
  })

  it('storeTheme persists the choice for the next visit', () => {
    const storage = memoryStorage()
    vi.stubGlobal('localStorage', storage)
    prefers('dark')
    expect(storeTheme('light')).toBe(true)
    expect(storage.getItem(THEME_STORAGE_KEY)).toBe('light')
    expect(getInitialTheme()).toBe('light')
  })

  it('storeTheme reports false instead of throwing when the browser refuses storage', () => {
    vi.stubGlobal('localStorage', blockedStorage())
    expect(storeTheme('light')).toBe(false)
  })
})

describe('theme.css', () => {
  it('declares the dark tokens in one :root rule and the light ones in one [data-theme="light"] rule, each with a one-line comment saying where it is used', () => {
    // #45 changed this from "one :root rule": the light theme is a second rule. Same checks, per rule.
    const rules = [...stripCssComments(themeCss).matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    expect(rules).toHaveLength(2)
    expect(rules.map((r) => r[1].split(',').map((s) => s.trim()))).toEqual([DARK_SELECTORS, LIGHT_SELECTORS])
    expect(darkDeclarations.size).toBeGreaterThan(50)

    for (const [i, [theme, tokens]] of ([['dark', darkDeclarations], ['light', lightDeclarations]] as const).entries()) {
      const declared = rules[i][2].match(/--[\w-]+\s*:/g) ?? []
      expect(declared, theme).toHaveLength(tokens.size) // every declaration is on its own line, parsed above
      for (const [name, { value, comment }] of tokens) {
        expect(name, name).toMatch(/^--(?:palette|color)-/)
        // A color literal, or a var()/color-mix() built only from tokens defined here.
        if (!isDerived(value)) expect(value, name).toMatch(COLOR_LITERAL)
        expect(() => resolveToken(name, theme), `${theme} ${name}`).not.toThrow()
        expect(comment, `${theme} ${name} needs a one-line comment`).toMatch(/^\/\*\s*\S.*\*\/$/)
      }
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

  it('keeps map tokens as plain hex, since MapLibre cannot parse var() or color-mix()', () => {
    const theme = themeTokens()
    for (const name of MAP_TOKENS) expect(theme.get(name)?.value, name).toMatch(/^#[0-9a-fA-F]{3,8}$/)
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

describe('palette', () => {
  const tokens = themeTokens()
  const literalPalette = () =>
    Object.fromEntries([...tokens].filter(([name, { value }]) => name.startsWith('--palette-') && !isDerived(value)).map(([name, { value }]) => [name, value]))

  it('defines exactly the four base colors, and they are the only literal palette tokens', () => {
    expect(literalPalette()).toEqual(BASE_PALETTE)
  })

  it.each(THEMES)('builds every %s token that uses the palette from palette tokens only, with no new literals', (theme) => {
    for (const [name, { value }] of themeTokens(theme)) {
      if (!name.startsWith('--palette-') && !value.includes('var(--palette-')) continue
      if (!isDerived(value)) continue // one of the four base colors, checked above
      expect(value.replace(/var\(--palette-[\w-]+\)/g, '').match(COLOR_LITERAL), name).toBeNull()
      for (const [, ref] of value.matchAll(/var\((--[\w-]+)\)/g)) expect(ref, name).toMatch(/^--palette-/)
    }
  })

  it('points the accent, top bar and text-on-navy/gold roles at the palette', () => {
    for (const [name, palette] of Object.entries(PALETTE_ROLES)) {
      expect(tokens.get(name)?.value, name).toBe(`var(${palette})`)
    }
    // The translucent accent and white tints keep their old alpha (except accent-border, below), mixed from the palette.
    const mixes: Record<string, [string, number]> = {
      // Raised from the old 0x8c (55%) to 67% so the sidebar search focus border reaches 3:1 (#42).
      '--color-accent-border': ['--palette-gold', 0.67],
      '--color-accent-wash': ['--palette-gold', 0x1c / 255],
      '--color-header-border': ['--palette-white', 0x12 / 255],
    }
    for (const [name, [palette, alpha]] of Object.entries(mixes)) {
      expect(tokens.get(name)?.value, name).toMatch(new RegExp(`^color-mix\\(in srgb, var\\(${palette}\\) [\\d.]+%, transparent\\)$`))
      expectColor(resolveToken(name), { ...resolveToken(palette), a: alpha }, 2, name)
    }
  })

  it('keeps the sidebar card grey #47494d as the one documented exception to the palette', () => {
    const roles = [...Object.keys(PALETTE_ROLES), '--color-sidebar-bg']
    const literals = roles.filter((name) => !isDerived(tokens.get(name)!.value))
    expect(literals).toEqual(['--color-sidebar-bg'])
    expect(tokens.get('--color-sidebar-bg')).toEqual({ value: '#47494d', comment: expect.stringMatching(/not part of the gold\/navy palette/i) })
  })

  it.each(THEMES)('repeats no base color as a literal outside the palette in the %s theme, except in the map tokens MapLibre reads', (theme) => {
    const base = Object.values(BASE_PALETTE).map((hex) => JSON.stringify(rgbOf(parseColor(hex))))
    for (const [name, { value }] of themeTokens(theme)) {
      if (name.startsWith('--palette-') || isDerived(value) || MAP_TOKENS.includes(name)) continue
      expect(base, `${name}: ${value} repeats a palette color; use var(--palette-…)`).not.toContain(JSON.stringify(rgbOf(parseColor(value))))
    }
  })

  it('lists each base hex value in the palette note at the top of theme.css', () => {
    const note = themeCss.slice(0, themeCss.search(/^:root/m))
    for (const [name, hex] of Object.entries(BASE_PALETTE)) {
      expect(note).toMatch(new RegExp(`${hex} [\\w ]+\\(${name}\\): \\S`)) // "#FFC928 gold (--palette-gold): where it is used"
    }
    expect(note).toMatch(/#47494d/)
  })
})

describe('contrast (WCAG AA)', () => {
  it('computes WCAG contrast ratios and color-mix() like a browser', () => {
    expect(contrast(parseColor('#000'), parseColor('#ffffff'))).toBeCloseTo(21, 5)
    expect(contrast(parseColor('#777777'), parseColor('#ffffff'))).toBeCloseTo(4.48, 2)
    expectColor(parseColor('color-mix(in srgb, #ff0000 25%, #0000ff)'), { r: 63.75, g: 0, b: 191.25, a: 1 })
    expectColor(parseColor('color-mix(in srgb, #ffffff 7%, transparent)'), { r: 255, g: 255, b: 255, a: 0.07 })
    expectColor(parseColor('color-mix(in srgb, var(--palette-navy) 40%, transparent)'), { r: 0x0b, g: 0x1f, b: 0x3a, a: 0.4 })
    expectColor(composite([parseColor('#000000'), parseColor('#ffffff80')]), { r: 128, g: 128, b: 128, a: 1 })
    expect(() => parseColor('rebeccapurple')).toThrow()
  })

  // #45: the same list, run once per theme.
  it.each(THEMES.flatMap((theme) => CONTRAST_PAIRS.map((pair) => ({ theme, ...pair }))))('$theme theme: $name: $fg on $bg is at least $min:1', ({ theme, fg, bg, min }) => {
    expect(pairContrast(fg, bg, theme)).toBeGreaterThanOrEqual(min)
  })

  it('keeps the DESC and GPC map lines at least 3:1 against navy, the sidebar grey and the dark map', () => {
    for (const line of ['--color-utility-desc', '--color-utility-gpc']) {
      for (const bg of ['--palette-navy', '--color-sidebar-bg', '--color-map-bg', '--color-halo-dark']) {
        expect(contrast(resolveToken(line, 'dark'), resolveToken(bg, 'dark')), `${line} on ${bg}`).toBeGreaterThanOrEqual(3)
      }
    }
  })
  it('keeps the other-utility line, the overlap and the selected overlap at least 3:1 against navy, the sidebar grey and the dark map', () => {
    // --color-halo-dark stands in for the dark basemap; the satellite basemap is covered by the
    // light/dark halo casing under every line (mapStyle.ts).
    for (const line of ['--color-utility-other', '--color-overlap', '--color-overlap-selected']) {
      for (const bg of ['--palette-navy', '--color-sidebar-bg', '--color-map-bg', '--color-halo-dark']) {
        expect(contrast(resolveToken(line, 'dark'), resolveToken(bg, 'dark')), `${line} on ${bg}`).toBeGreaterThanOrEqual(3)
      }
    }
  })

  it('in the light theme, keeps every map line at least 3:1 against navy, the map before tiles load and the casing under it, and that casing at least 3:1 against the light basemap', () => {
    // On Positron (near-white) the lines themselves are about 2-3:1, so the light basemap draws the
    // dark casing under them (BASEMAPS.light.halo), and the line reads against that casing.
    expect(BASEMAPS.light.halo).toBe('dark')
    const casing = `--color-halo-${BASEMAPS.light.halo}`
    const lines = ['--color-utility-desc', '--color-utility-gpc', '--color-utility-other', '--color-overlap', '--color-overlap-selected']
    for (const line of lines) {
      for (const bg of ['--palette-navy', '--color-map-bg', casing]) {
        expect(contrast(resolveToken(line, 'light'), resolveToken(bg, 'light')), `${line} on ${bg}`).toBeGreaterThanOrEqual(3)
      }
    }
    // --color-halo-light (#ffffff) stands in for Positron's near-white land (#fafaf8).
    expect(contrast(resolveToken(casing, 'light'), resolveToken('--color-halo-light', 'light'))).toBeGreaterThanOrEqual(3)
  })
})

describe('no green (#43)', () => {
  it('removes the old green theme values from theme.css and workspace.css', () => {
    for (const [file, css] of [['theme.css', themeCss], ['workspace.css', workspaceCss]]) {
      for (const green of OLD_GREENS) expect(css.toLowerCase(), `${file} still has ${green}`).not.toContain(green)
    }
  })

  it('classifies greens by hue and saturation, letting neutral greys, the golds and navy through', () => {
    // The old greens, including the greenish greys and near-whites of the light theme.
    for (const green of [...OLD_GREENS, '#7b8c44', '#6a6e66', '#232722', '#f5f5f0', '#f9faf5', '#a3be8c', '#111b16']) {
      expect(isGreen(parseColor(green)), green).toBe(true)
    }
    for (const other of ['#FFC928', '#F4A900', '#0B1F3A', '#47494d', '#111', '#1c1d20', '#cc964c', '#22d3ee', '#ffffff', '#000a']) {
      expect(isGreen(parseColor(other)), other).toBe(false)
    }
  })

  it.each(THEMES)('leaves no %s token with a green hue, map tokens included', (theme) => {
    const greens = [...themeTokens(theme).keys()].filter((name) => isGreen(resolveToken(name, theme)))
    expect(greens).toEqual(GREEN_EXCEPTIONS)
  })

  it('points the primary accent at the logo gold and the top bar at navy', () => {
    const tokens = themeTokens()
    expect(tokens.get('--color-accent')?.value).toBe('var(--palette-gold)')
    expectColor(resolveToken('--color-accent'), parseColor('#FFC928'))
    // The header only: the sidebar card is the documented grey exception (#42), tested above.
    expect(tokens.get('--color-header-bg')?.value).toBe('var(--palette-navy)')
    expectColor(resolveToken('--color-header-bg'), parseColor('#0B1F3A'))
  })

  it('builds the light theme\'s neutral surfaces and greys from navy mixed with white', () => {
    const light = ['--color-surface', '--color-muted', '--color-rule', '--color-panel-bg', '--color-panel-heading', '--color-panel-meta', '--color-step', '--color-drop-zone-bg', '--color-drop-zone-text', '--color-focus-ring']
    for (const name of light) {
      expect(themeTokens().get(name)?.value, name).toMatch(/^color-mix\(in srgb, var\(--palette-navy\) [\d.]+%, var\(--palette-white\)\)$/)
    }
  })
})

describe('light theme (#45)', () => {
  // Map tokens stay out of the light rule: MapLibre reads them once, at page load (theme.ts).
  const semanticNames = [...darkDeclarations.keys()].filter((name) => name.startsWith('--color-') && !MAP_TOKENS.includes(name))

  it('defines every semantic token the dark theme defines, and redeclares no palette or map token', () => {
    expect(semanticNames.length).toBeGreaterThan(100)
    expect([...lightDeclarations.keys()].sort()).toEqual([...semanticNames].sort())
  })

  it('marks a light value "same as dark" exactly when it repeats the dark value, so the two cannot drift apart unnoticed', () => {
    for (const [name, { value, comment }] of lightDeclarations) {
      expect(/same as dark/.test(comment), `${name}: ${value} vs dark ${darkDeclarations.get(name)?.value}`).toBe(value === darkDeclarations.get(name)?.value)
    }
    // Sanity: the light theme really changes something.
    expect([...lightDeclarations.values()].filter(({ comment }) => !/same as dark/.test(comment)).length).toBeGreaterThan(25)
  })

  it('builds every light-only value from the palette or other tokens, adding no color literal of its own', () => {
    for (const [name, { value, comment }] of lightDeclarations) {
      if (/same as dark/.test(comment)) continue
      expect(isDerived(value), `${name}: ${value}`).toBe(true)
      expect(value.replace(/var\(--[\w-]+\)/g, '').match(COLOR_LITERAL), name).toBeNull()
    }
  })

  it('keeps the top bar navy with white text and the gold logo accent, and gold for the primary button fill', () => {
    for (const [name, palette] of Object.entries({
      '--color-header-bg': '--palette-navy',
      '--color-header-text': '--palette-white',
      '--color-accent': '--palette-gold',
      '--color-primary-button-text': '--palette-navy',
      '--color-primary-button-hover': '--palette-gold-dark',
    })) {
      expectColor(resolveToken(name, 'light'), resolveToken(palette), 6, name)
    }
  })

  it('makes the sidebar card white with navy text, and its accent text navy since gold is unreadable on white', () => {
    expectColor(resolveToken('--color-sidebar-bg', 'light'), parseColor('#FFFFFF'))
    expectColor(resolveToken('--color-sidebar-text', 'light'), parseColor('#0B1F3A'))
    expectColor(resolveToken('--color-sidebar-accent-text', 'light'), parseColor('#0B1F3A'))
    // Gold really is below 3:1 on the white card: the reason for the swap.
    expect(contrast(resolveToken('--palette-gold'), resolveToken('--color-sidebar-bg', 'light'))).toBeLessThan(3)
    // The accent lines stay a gold: the darker gold mixed with navy, still gold in hue (not navy, not green).
    expect(themeTokens('light').get('--color-sidebar-accent-line')?.value).toMatch(/^color-mix\(in srgb, var\(--palette-navy\) [\d.]+%, var\(--palette-gold-dark\)\)$/)
    // Every surface behind the card's content is near-white (the card, its cards, hovers, fields).
    for (const layer of ['--color-sidebar-card-bg', '--color-sidebar-card-hover-bg', '--color-sidebar-search-bg', '--color-sidebar-row-hover', '--color-sidebar-select-bg', '--color-sidebar-button-bg']) {
      const surface = composite([resolveToken('--color-sidebar-bg', 'light'), resolveToken(layer, 'light')])
      expect(contrast(surface, parseColor('#FFFFFF')), layer).toBeLessThan(1.15)
    }
  })
})

describe('dark theme unchanged by #45', () => {
  it('resolves every token that existed before #45 to exactly the color it had then', () => {
    const tokens = themeTokens('dark')
    for (const [name, before] of Object.entries(DARK_BEFORE_45)) {
      expect(tokens.has(name), `${name} was removed`).toBe(true)
      expect(hex8(resolveToken(name, 'dark')), name).toBe(before)
    }
    expect(Object.keys(DARK_BEFORE_45)).toHaveLength(133)
  })

  it('adds only the sidebar accent tokens, which resolve to the gold accent the sidebar painted before', () => {
    const added = [...darkDeclarations.keys()].filter((name) => !(name in DARK_BEFORE_45))
    expect(added).toEqual(['--color-sidebar-accent-text', '--color-sidebar-accent-line', '--color-sidebar-accent-border'])
    expect(darkDeclarations.get('--color-sidebar-accent-text')?.value).toBe('var(--color-accent)')
    expect(darkDeclarations.get('--color-sidebar-accent-line')?.value).toBe('var(--color-accent)')
    expect(darkDeclarations.get('--color-sidebar-accent-border')?.value).toBe('var(--color-accent-border)')
  })

  it('paints the sidebar\'s accent text and lines with the sidebar accent tokens (only the "new" tag keeps a gold fill)', () => {
    const css = stripCssComments(workspaceCss)
    const sidebarRules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter((m) => m[1].includes('.sidebar-panel'))
    const accentUses = sidebarRules.flatMap((m) => [...m[2].matchAll(/([\w-]+)\s*:[^;]*var\(--color-accent(?:-border)?\)/g)].map((d) => `${m[1].trim()} ${d[1]}`))
    expect(accentUses).toEqual(['.sidebar-panel .new-tag background'])
    for (const token of ['--color-sidebar-accent-text', '--color-sidebar-accent-line', '--color-sidebar-accent-border']) {
      expect(css, token).toContain(`var(${token})`)
    }
  })
})

/** A color as #rrggbbaa, each channel rounded: how DARK_BEFORE_45 records the pre-#45 values. */
const hex8 = ({ r, g, b, a }: Rgba) => '#' + [r, g, b, a * 255].map((c) => Math.round(c).toString(16).padStart(2, '0')).join('')

// Every theme.css token as it resolved before #45 (HEAD 54547fc), with this file's resolver.
// The dark theme is "today's look, unchanged": none of these may change.
const DARK_BEFORE_45: Record<string, string> = {
  '--palette-gold': '#ffc928ff',
  '--palette-gold-dark': '#f4a900ff',
  '--palette-navy': '#0b1f3aff',
  '--palette-white': '#ffffffff',
  '--color-surface': '#f5f6f7ff',
  '--color-text': '#0b1f3aff',
  '--color-muted': '#606d7fff',
  '--color-rule': '#dadde1ff',
  '--color-accent': '#ffc928ff',
  '--color-accent-border': '#ffc928ab',
  '--color-accent-wash': '#ffc9281c',
  '--color-accent-ink': '#0b1f3aff',
  '--color-focus-ring': '#717d8dff',
  '--color-header-bg': '#0b1f3aff',
  '--color-header-text': '#ffffffff',
  '--color-header-border': '#ffffff12',
  '--color-header-button-hover': '#ffffff1a',
  '--color-source-dot': '#ffc928ff',
  '--color-primary-button-text': '#0b1f3aff',
  '--color-primary-button-hover': '#f4a900ff',
  '--color-secondary-button-bg': '#ffffffff',
  '--color-secondary-button-border': '#c7cbd2ff',
  '--color-secondary-button-hover': '#eeeff1ff',
  '--color-icon-button-hover': '#00000008',
  '--color-link': '#0b1f3aff',
  '--color-body-bg': '#1c1d20ff',
  '--color-map-bg': '#111111ff',
  '--color-sidebar-bg': '#47494dff',
  '--color-sidebar-border': '#ffffff1c',
  '--color-sidebar-highlight': '#ffffff14',
  '--color-sidebar-shadow': '#0000008c',
  '--color-sidebar-shadow-near': '#00000059',
  '--color-sidebar-text': '#f2f3f5ff',
  '--color-sidebar-muted': '#cdd0d4ff',
  '--color-sidebar-rule': '#ffffff1a',
  '--color-sidebar-checkbox': '#ffc928ff',
  '--color-sidebar-tab-count-bg': '#ffffff17',
  '--color-sidebar-search-bg': '#ffffff12',
  '--color-sidebar-search-border': '#ffffff0f',
  '--color-sidebar-search-placeholder': '#cdd0d4ff',
  '--color-sidebar-scrollbar': '#ffffff33',
  '--color-sidebar-list-caption': '#d9dce0ff',
  '--color-sidebar-card-bg': '#ffffff0a',
  '--color-sidebar-card-border': '#ffffff14',
  '--color-sidebar-card-hover-bg': '#ffffff14',
  '--color-sidebar-card-hover-border': '#ffffff30',
  '--color-sidebar-pair-connector': '#ffffff26',
  '--color-sidebar-row-divider': '#ffffff12',
  '--color-sidebar-row-hover': '#ffffff12',
  '--color-sidebar-button-bg': '#ffffff14',
  '--color-sidebar-button-border': '#ffffff26',
  '--color-sidebar-button-hover': '#ffffff24',
  '--color-sidebar-flagged-text': '#f4be8cff',
  '--color-sidebar-select-bg': '#ffffff0a',
  '--color-sidebar-select-border': '#ffffff26',
  '--color-sidebar-option-bg': '#0b1f3aff',
  '--color-savings': '#0b1f3aff',
  '--color-checkbox': '#0b1f3aff',
  '--color-tab-underline': '#0b1f3aff',
  '--color-tab-count-bg': '#e4e6e9ff',
  '--color-search-bg': '#ebedefff',
  '--color-search-icon': '#7b8695ff',
  '--color-search-focus-border': '#aab1baff',
  '--color-search-placeholder': '#838d9bff',
  '--color-scrollbar': '#c9ced4ff',
  '--color-list-caption': '#48576bff',
  '--color-card-bg': '#fdfdfdff',
  '--color-card-border': '#dde0e3ff',
  '--color-card-hover-bg': '#ffffffff',
  '--color-card-hover-border': '#a2aab4ff',
  '--color-card-selected-bg': '#ffc9281c',
  '--color-card-selected-border': '#ffc928ab',
  '--color-card-selected-bar': '#ffc928ff',
  '--color-card-rank': '#747f8fff',
  '--color-card-divider': '#e4e6e9ff',
  '--color-pair-connector': '#dde0e3ff',
  '--color-tag-text': '#0b1f3aff',
  '--color-tag-bg': '#ffc928ff',
  '--color-row-hover': '#e9ebedff',
  '--color-batch-card-bg': '#ffffffff',
  '--color-flagged-text': '#98632fff',
  '--color-map-context-bg': '#0b1f3aed',
  '--color-map-context-border': '#ffffff1f',
  '--color-map-context-text': '#f3f4f5ff',
  '--color-map-context-muted': '#9da5b0ff',
  '--color-map-context-divider': '#ffffff20',
  '--color-notice-bg': '#e9ebedff',
  '--color-notice-text': '#304158ff',
  '--color-upload-problem-bg': '#f4e2d4ff',
  '--color-upload-problem-text': '#5b3419ff',
  '--color-upload-problem-link': '#7a3f14ff',
  '--color-floating-shadow': '#00000033',
  '--color-panel-bg': '#fafbfbff',
  '--color-panel-border': '#d6d9deff',
  '--color-panel-heading': '#657283ff',
  '--color-panel-meta': '#657283ff',
  '--color-panel-meta-strong': '#3c4c61ff',
  '--color-why-bg': '#eeeff1ff',
  '--color-why-border': '#ffc928ff',
  '--color-why-text': '#304158ff',
  '--color-dialog-border': '#dadde1ff',
  '--color-dialog-shadow': '#00000055',
  '--color-dialog-backdrop': '#0b1f3aa8',
  '--color-upload-symbol-bg': '#e9ebedff',
  '--color-upload-symbol-border': '#dadde1ff',
  '--color-upload-symbol-icon': '#5e6b7dff',
  '--color-step': '#657283ff',
  '--color-step-current': '#0b1f3aff',
  '--color-step-current-bar': '#0b1f3aff',
  '--color-drop-zone-bg': '#f3f4f5ff',
  '--color-drop-zone-border': '#b6bcc4ff',
  '--color-drop-zone-text': '#596779ff',
  '--color-drop-zone-title': '#3c4c61ff',
  '--color-drop-zone-hint': '#596779ff',
  '--color-drop-zone-hover-bg': '#e9ebedff',
  '--color-drop-zone-hover-border': '#768291ff',
  '--color-upload-footer-text': '#657283ff',
  '--color-error-bg': '#fff4e9ff',
  '--color-error-border': '#e5c7b1ff',
  '--color-error-text': '#a05225ff',
  '--color-review-divider': '#e7e9ebff',
  '--color-status-ready': '#0b1f3aff',
  '--color-status-flagged': '#cc964cff',
  '--color-review-note': '#657283ff',
  '--color-utility-desc': '#60a5faff',
  '--color-utility-gpc': '#f87171ff',
  '--color-utility-other': '#22d3eeff',
  '--color-overlap': '#f59e0bff',
  '--color-overlap-selected': '#c4b5fdff',
  '--color-point-stroke': '#ffffffff',
  '--color-legend-low-confidence': '#cbd5e1ff',
  '--color-halo-dark': '#020617ff',
  '--color-halo-light': '#ffffffff',
}

const BASE_PALETTE = {
  '--palette-gold': '#FFC928',
  '--palette-gold-dark': '#F4A900',
  '--palette-navy': '#0B1F3A',
  '--palette-white': '#FFFFFF',
}

// The green theme this palette replaced (#43): none of these may come back.
const OLD_GREENS = ['#d6ed8a', '#8fa36b', '#3f5a1d', '#273018', '#1d2614', '#20251f']

// Tokens allowed to stay green. Empty on purpose: add a token here only with a comment saying why.
const GREEN_EXCEPTIONS: string[] = []

/**
 * Green = HSL hue in [55°, 170°] with saturation above 3%. The hue band leaves out the golds
 * (~42-45°), the orange warnings (≤35°) and the cyan other-utility line (~189°). The 3% floor lets
 * true neutral greys (0%) through but catches the greenish greys the old theme used for text and
 * light surfaces (3.8-7%); a floor of 8-10% would let those back in unnoticed. Alpha is ignored.
 */
function isGreen({ r, g, b }: Rgba): boolean {
  const [max, min] = [Math.max(r, g, b) / 255, Math.min(r, g, b) / 255]
  const delta = max - min
  if (delta === 0) return false
  const saturation = delta / (1 - Math.abs(max + min - 1))
  const [R, G, B] = [r / 255, g / 255, b / 255]
  const sector = max === R ? ((G - B) / delta + 6) % 6 : max === G ? (B - R) / delta + 2 : (R - G) / delta + 4
  const hue = sector * 60
  return hue >= 55 && hue <= 170 && saturation > 0.03
}

// Semantic tokens that name a palette color directly.
const PALETTE_ROLES: Record<string, string> = {
  '--color-accent': '--palette-gold',
  '--color-sidebar-checkbox': '--palette-gold',
  '--color-primary-button-hover': '--palette-gold-dark',
  '--color-header-bg': '--palette-navy',
  '--color-accent-ink': '--palette-navy',
  '--color-primary-button-text': '--palette-navy',
  // #43: the former greens that now name a palette color directly.
  '--color-text': '--palette-navy',
  '--color-link': '--palette-navy',
  '--color-savings': '--palette-navy',
  '--color-checkbox': '--palette-navy',
  '--color-tab-underline': '--palette-navy',
  '--color-step-current': '--palette-navy',
  '--color-step-current-bar': '--palette-navy',
  '--color-status-ready': '--palette-navy',
  '--color-sidebar-option-bg': '--palette-navy',
  '--color-source-dot': '--palette-gold',
  '--color-why-border': '--palette-gold',
  '--color-header-text': '--palette-white',
  '--color-secondary-button-bg': '--palette-white',
  '--color-card-hover-bg': '--palette-white',
  '--color-batch-card-bg': '--palette-white',
}

// Text/background pairs as workspace.css paints them. `bg` lists the layers bottom to top
// (translucent fills are composited over what is under them). 4.5 for text, 3 for UI parts.
// Every pair is checked in both themes (#45). The sidebar accent pairs name what workspace.css
// paints since #45 (--color-sidebar-accent-*); in the dark theme those are the gold --color-accent*.
const SIDEBAR = '--color-sidebar-bg'
const CONTRAST_PAIRS: { name: string; fg: string; bg: string[]; min: number }[] = [
  { name: 'top bar text', fg: '--color-header-text', bg: ['--color-header-bg'], min: 4.5 },
  { name: 'primary button text', fg: '--color-primary-button-text', bg: ['--color-accent'], min: 4.5 },
  { name: 'primary button hover text', fg: '--color-primary-button-text', bg: ['--color-primary-button-hover'], min: 4.5 },
  // Top bar menu button (#44): icon-only, white on navy; gold while the sidebar is open.
  { name: 'top bar menu icon', fg: '--color-header-text', bg: ['--color-header-bg'], min: 3 },
  { name: 'top bar menu icon while hovered', fg: '--color-header-text', bg: ['--color-header-bg', '--color-header-button-hover'], min: 3 },
  { name: 'top bar menu icon while the sidebar is open', fg: '--color-accent', bg: ['--color-header-bg'], min: 3 },
  { name: 'top bar menu icon while open and hovered', fg: '--color-accent', bg: ['--color-header-bg', '--color-header-button-hover'], min: 3 },
  { name: 'sidebar "new" tag', fg: '--color-accent-ink', bg: [SIDEBAR, '--color-accent'], min: 4.5 },
  { name: 'sidebar text', fg: '--color-sidebar-text', bg: [SIDEBAR], min: 4.5 },
  { name: 'sidebar muted text', fg: '--color-sidebar-muted', bg: [SIDEBAR], min: 4.5 },
  { name: 'sidebar list caption', fg: '--color-sidebar-list-caption', bg: [SIDEBAR], min: 4.5 },
  { name: 'sidebar accent text (savings figure, text links)', fg: '--color-sidebar-accent-text', bg: [SIDEBAR], min: 4.5 },
  { name: 'sidebar sort select text', fg: '--color-sidebar-accent-text', bg: [SIDEBAR, '--color-sidebar-select-bg'], min: 4.5 },
  { name: 'sidebar sort options', fg: '--color-sidebar-text', bg: ['--color-sidebar-option-bg'], min: 4.5 },
  { name: 'sidebar card text', fg: '--color-sidebar-text', bg: [SIDEBAR, '--color-sidebar-card-bg'], min: 4.5 },
  { name: 'sidebar card muted text', fg: '--color-sidebar-muted', bg: [SIDEBAR, '--color-sidebar-card-bg'], min: 4.5 },
  { name: 'sidebar hovered card muted text', fg: '--color-sidebar-muted', bg: [SIDEBAR, '--color-sidebar-card-hover-bg'], min: 4.5 },
  { name: 'sidebar selected card text', fg: '--color-sidebar-text', bg: [SIDEBAR, '--color-accent-wash'], min: 4.5 },
  { name: 'sidebar selected card muted text', fg: '--color-sidebar-muted', bg: [SIDEBAR, '--color-accent-wash'], min: 4.5 },
  { name: 'sidebar project row hover muted text', fg: '--color-sidebar-muted', bg: [SIDEBAR, '--color-sidebar-row-hover'], min: 4.5 },
  { name: 'sidebar search text', fg: '--color-sidebar-text', bg: [SIDEBAR, '--color-sidebar-search-bg'], min: 4.5 },
  { name: 'sidebar search placeholder', fg: '--color-sidebar-search-placeholder', bg: [SIDEBAR, '--color-sidebar-search-bg'], min: 4.5 },
  { name: 'sidebar secondary button hover text', fg: '--color-sidebar-text', bg: [SIDEBAR, '--color-sidebar-button-hover'], min: 4.5 },
  { name: 'sidebar flagged import reason', fg: '--color-sidebar-flagged-text', bg: [SIDEBAR, '--color-sidebar-card-bg'], min: 4.5 },
  { name: 'sidebar focus outline', fg: '--color-sidebar-accent-line', bg: [SIDEBAR], min: 3 },
  { name: 'sidebar selected tab underline', fg: '--color-sidebar-accent-line', bg: [SIDEBAR], min: 3 },
  { name: 'sidebar selected card bar', fg: '--color-sidebar-accent-line', bg: [SIDEBAR, '--color-accent-wash'], min: 3 },
  { name: 'body text on the light surface', fg: '--color-text', bg: ['--color-surface'], min: 4.5 },
  { name: 'muted text on the light surface', fg: '--color-muted', bg: ['--color-surface'], min: 4.5 },
  { name: 'text on the selection panel and upload dialog', fg: '--color-text', bg: ['--color-panel-bg'], min: 4.5 },
  { name: 'muted text on the selection panel and upload dialog', fg: '--color-muted', bg: ['--color-panel-bg'], min: 4.5 },
  { name: 'secondary button text', fg: '--color-text', bg: ['--color-secondary-button-bg'], min: 4.5 },
  // Selection panel (opens when a pair or project is selected) and the upload dialog.
  { name: 'selection panel heading', fg: '--color-panel-heading', bg: ['--color-panel-bg'], min: 4.5 },
  { name: 'selection panel project meta', fg: '--color-panel-meta', bg: ['--color-panel-bg'], min: 4.5 },
  { name: 'upload step labels', fg: '--color-step', bg: ['--color-panel-bg'], min: 4.5 },
  { name: 'upload dialog footer note', fg: '--color-upload-footer-text', bg: ['--color-panel-bg'], min: 4.5 },
  { name: 'upload review footnote', fg: '--color-review-note', bg: ['--color-panel-bg'], min: 4.5 },
  { name: 'drop zone text', fg: '--color-drop-zone-text', bg: ['--color-drop-zone-bg'], min: 4.5 },
  { name: 'drop zone text while hovered/dragging', fg: '--color-drop-zone-text', bg: ['--color-drop-zone-hover-bg'], min: 4.5 },
  { name: 'drop zone hint', fg: '--color-drop-zone-hint', bg: ['--color-drop-zone-bg'], min: 4.5 },
  { name: 'drop zone hint while hovered/dragging', fg: '--color-drop-zone-hint', bg: ['--color-drop-zone-hover-bg'], min: 4.5 },
  // Sidebar details: the unselected Uploads count badge, and the search field's only focus indicator.
  { name: 'sidebar tab count badge (unselected)', fg: '--color-sidebar-muted', bg: [SIDEBAR, '--color-sidebar-tab-count-bg'], min: 4.5 },
  { name: 'sidebar tab count badge (selected)', fg: '--color-sidebar-text', bg: [SIDEBAR, '--color-sidebar-tab-count-bg'], min: 4.5 },
  { name: 'sidebar search focus border vs the card', fg: '--color-sidebar-accent-border', bg: [SIDEBAR], min: 3 },
  { name: 'sidebar search focus border vs the search field', fg: '--color-sidebar-accent-border', bg: [SIDEBAR, '--color-sidebar-search-bg'], min: 3 },
  { name: 'selected sidebar card border', fg: '--color-sidebar-accent-border', bg: [SIDEBAR, '--color-sidebar-card-bg'], min: 3 },
  // #43: combinations the green-to-navy swap changed. The sidebar's focus outline is gold (pair above).
  { name: 'focus outline on the selection panel and upload dialog', fg: '--color-focus-ring', bg: ['--color-panel-bg'], min: 3 },
  { name: 'focus outline on the navy top bar', fg: '--color-focus-ring', bg: ['--color-header-bg'], min: 3 },
  { name: 'focus outline on the light surface', fg: '--color-focus-ring', bg: ['--color-surface'], min: 3 },
  { name: 'focus outline on the status notice', fg: '--color-focus-ring', bg: ['--color-notice-bg'], min: 3 },
  { name: 'focus outline on the upload problem notice', fg: '--color-focus-ring', bg: ['--color-upload-problem-bg'], min: 3 },
  { name: 'focus outline over the map', fg: '--color-focus-ring', bg: ['--color-map-bg'], min: 3 },
  { name: 'text links on the upload dialog', fg: '--color-link', bg: ['--color-panel-bg'], min: 4.5 },
  { name: 'savings figure in the overlap detail', fg: '--color-savings', bg: ['--color-panel-bg'], min: 4.5 },
  { name: 'selection panel emphasized meta value', fg: '--color-panel-meta-strong', bg: ['--color-panel-bg'], min: 4.5 },
  { name: 'current upload step label', fg: '--color-step-current', bg: ['--color-panel-bg'], min: 4.5 },
  { name: 'current upload step underline', fg: '--color-step-current-bar', bg: ['--color-panel-bg'], min: 3 },
  { name: 'upload error text', fg: '--color-error-text', bg: ['--color-error-bg'], min: 4.5 },
  { name: 'overlap detail "why" text', fg: '--color-why-text', bg: ['--color-why-bg'], min: 4.5 },
  { name: 'status notice text', fg: '--color-notice-text', bg: ['--color-notice-bg'], min: 4.5 },
  { name: 'drop zone title', fg: '--color-drop-zone-title', bg: ['--color-drop-zone-bg'], min: 4.5 },
  { name: 'drop zone title while hovered/dragging', fg: '--color-drop-zone-title', bg: ['--color-drop-zone-hover-bg'], min: 4.5 },
  { name: 'drop zone border while hovered/dragging', fg: '--color-drop-zone-hover-border', bg: ['--color-panel-bg'], min: 3 },
  { name: 'map context chip text on the dark map', fg: '--color-map-context-text', bg: ['--color-map-bg', '--color-map-context-bg'], min: 4.5 },
  { name: 'map context chip muted text on the dark map', fg: '--color-map-context-muted', bg: ['--color-map-bg', '--color-map-context-bg'], min: 4.5 },
  // --color-halo-light (#ffffff) stands in for the light basemaps showing through the chip.
  { name: 'map context chip text on a light map', fg: '--color-map-context-text', bg: ['--color-halo-light', '--color-map-context-bg'], min: 4.5 },
  { name: 'map context chip muted text on a light map', fg: '--color-map-context-muted', bg: ['--color-halo-light', '--color-map-context-bg'], min: 4.5 },
  { name: 'data source dot on the map context chip', fg: '--color-source-dot', bg: ['--color-map-bg', '--color-map-context-bg'], min: 3 },
  { name: 'data source dot in the sidebar footer', fg: '--color-source-dot', bg: [SIDEBAR], min: 3 },
  { name: 'upload dialog icon on its tile', fg: '--color-upload-symbol-icon', bg: ['--color-panel-bg', '--color-upload-symbol-bg'], min: 3 },
  { name: 'close icon on a hovered icon button', fg: '--color-muted', bg: ['--color-panel-bg', '--color-icon-button-hover'], min: 3 },
  { name: '"ready" status dot in upload review', fg: '--color-status-ready', bg: ['--color-panel-bg'], min: 3 },
  { name: 'text on a hovered secondary button', fg: '--color-text', bg: ['--color-secondary-button-hover'], min: 4.5 },
  // #45: the top bar's theme toggle (icon-only, white on navy in both themes) and the sidebar pieces the light theme restyles.
  { name: 'top bar theme toggle icon', fg: '--color-header-text', bg: ['--color-header-bg'], min: 3 },
  { name: 'top bar theme toggle icon while hovered', fg: '--color-header-text', bg: ['--color-header-bg', '--color-header-button-hover'], min: 3 },
  { name: 'sidebar sort select hover border', fg: '--color-sidebar-accent-border', bg: [SIDEBAR, '--color-sidebar-select-bg'], min: 3 },
  { name: 'sidebar secondary button text', fg: '--color-sidebar-text', bg: [SIDEBAR, '--color-sidebar-button-bg'], min: 4.5 },
  { name: 'sidebar project row hover text', fg: '--color-sidebar-text', bg: [SIDEBAR, '--color-sidebar-row-hover'], min: 4.5 },
  { name: 'sidebar hovered card text', fg: '--color-sidebar-text', bg: [SIDEBAR, '--color-sidebar-card-hover-bg'], min: 4.5 },
]

type Rgba = { r: number; g: number; b: number; a: number } // channels 0-255, alpha 0-1

const isDerived = (value: string) => /^(?:var|color-mix)\(/.test(value)
const rgbOf = ({ r, g, b }: Rgba) => ({ r, g, b })

function expectColor(actual: Rgba, expected: Rgba, digits = 6, label = '') {
  for (const k of ['r', 'g', 'b', 'a'] as const) expect(actual[k], `${label} ${k}`).toBeCloseTo(expected[k], digits)
}

/** A theme.css token's color in `theme`, following var() references. Throws on anything it can't resolve. */
function resolveToken(name: string, theme: Theme = 'dark', seen: string[] = []): Rgba {
  if (seen.includes(name)) throw new Error(`circular reference: ${[...seen, name].join(' -> ')}`)
  const token = themeTokens(theme).get(name)
  if (!token) throw new Error(`${name} is not defined in theme.css`)
  return parseColor(token.value, [...seen, name], theme)
}

/** Parse the color syntaxes theme.css uses: hex, white, transparent, var(), color-mix(in srgb, …); var() resolves in `theme`. */
function parseColor(value: string, seen: string[] = [], theme: Theme = 'dark'): Rgba {
  const v = value.trim()
  const hex = v.match(/^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i)?.[1]
  if (hex) {
    const full = hex.length <= 4 ? [...hex].map((c) => c + c).join('') : hex
    const [r, g, b, a = 255] = full.match(/../g)!.map((pair) => parseInt(pair, 16))
    return { r, g, b, a: a / 255 }
  }
  if (v === 'white') return { r: 255, g: 255, b: 255, a: 1 }
  if (v === 'transparent') return { r: 0, g: 0, b: 0, a: 0 }
  const ref = v.match(/^var\((--[\w-]+)\)$/)?.[1]
  if (ref) return resolveToken(ref, theme, seen)
  const mix = v.match(/^color-mix\(in srgb,\s*(.+)\)$/)?.[1]
  if (mix) {
    const parts = splitTopLevel(mix)
    if (parts.length !== 2) throw new Error(`color-mix needs two colors: ${v}`)
    const [[c1, p1], [c2, p2]] = parts.map((part) => {
      const m = part.match(/^(.+?)(?:\s+([\d.]+)%)?$/)!
      return [parseColor(m[1], seen, theme), m[2] === undefined ? undefined : Number(m[2]) / 100] as const
    })
    return colorMix(c1, p1, c2, p2)
  }
  throw new Error(`unsupported color value: ${value}`)
}

/** CSS Color 5 color-mix() in srgb: premultiplied-alpha interpolation, missing percentages fill to 100%. */
function colorMix(c1: Rgba, p1: number | undefined, c2: Rgba, p2: number | undefined): Rgba {
  const w1 = p1 ?? (p2 === undefined ? 0.5 : 1 - p2)
  const w2 = p2 ?? 1 - w1
  const sum = w1 + w2
  const [n1, n2] = [w1 / sum, w2 / sum]
  const a = c1.a * n1 + c2.a * n2
  const channel = (k: 'r' | 'g' | 'b') => (a === 0 ? 0 : (c1[k] * c1.a * n1 + c2[k] * c2.a * n2) / a)
  return { r: channel('r'), g: channel('g'), b: channel('b'), a: a * Math.min(sum, 1) }
}

function splitTopLevel(list: string): string[] {
  const parts: string[] = []
  let depth = 0
  let start = 0
  for (let i = 0; i < list.length; i++) {
    if (list[i] === '(') depth++
    else if (list[i] === ')') depth--
    else if (list[i] === ',' && depth === 0) {
      parts.push(list.slice(start, i).trim())
      start = i + 1
    }
  }
  return [...parts, list.slice(start).trim()]
}

/** Paint `layers` bottom to top; the bottom layer is made opaque (it sits on an opaque page). */
function composite(layers: Rgba[]): Rgba {
  return layers.slice(1).reduce(
    (under, over) => ({
      r: over.r * over.a + under.r * (1 - over.a),
      g: over.g * over.a + under.g * (1 - over.a),
      b: over.b * over.a + under.b * (1 - over.a),
      a: 1,
    }),
    { ...layers[0], a: 1 },
  )
}

/** Contrast of `fg` painted over the `bg` layers (bottom to top), as CONTRAST_PAIRS lists them, in `theme`. */
function pairContrast(fg: string, bg: string[], theme: Theme): number {
  const background = composite(bg.map((name) => resolveToken(name, theme)))
  return contrast(composite([background, resolveToken(fg, theme)]), background)
}

/** WCAG 2 contrast ratio of two opaque colors. */
function contrast(x: Rgba, y: Rgba): number {
  const luminance = ({ r, g, b }: Rgba) => {
    const lin = (c: number) => (c / 255 <= 0.04045 ? c / 255 / 12.92 : ((c / 255 + 0.055) / 1.055) ** 2.4)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
  }
  const [hi, lo] = [luminance(x), luminance(y)].sort((m, n) => n - m)
  return (hi + 0.05) / (lo + 0.05)
}

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
