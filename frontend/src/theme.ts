// Reads palette tokens from theme.css for code that can't use CSS var() — MapLibre paint
// properties and inline swatch styles — and switches between its light and dark token sets.
import { useState } from 'react'

/**
 * The value of CSS custom property `name` on the document root (theme.css's `:root`), trimmed,
 * or `fallback` when the token is unset (e.g. in unit tests, where theme.css isn't loaded).
 * Pass today's color from theme.css as `fallback`; theme.test.ts checks every call site agrees.
 *
 * The map's color constants call this once, when their module loads. main.tsx imports theme.css
 * before App, so the tokens are applied by then; after editing a map token, reload the page.
 * Map tokens are the same in both themes, so switching theme never needs a re-read.
 */
export function themeColor(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

// Light/dark theme (#45). theme.css holds both token sets: the dark one on :root (the default)
// and the light one under [data-theme="light"] on <html>. Components never branch on the theme
// for colors; only the map picks its basemap from it (basemaps.ts).
export type Theme = 'dark' | 'light'

/** Where the user's choice is kept. Only an explicit choice is stored, never the OS preference. */
export const THEME_STORAGE_KEY = 'relay.theme'

const isTheme = (value: unknown): value is Theme => value === 'dark' || value === 'light'

/**
 * The theme to start in: the stored choice, else the OS preference (prefers-color-scheme), else
 * dark. Never throws: blocked storage and a garbage stored value both read as no choice.
 */
export function getInitialTheme(): Theme {
  let stored: string | null = null
  try {
    stored = localStorage.getItem(THEME_STORAGE_KEY)
  } catch { /* storage blocked (private window, site data off): fall through to the OS preference */ }
  if (isTheme(stored)) return stored
  // matchMedia is missing only outside real browsers (jsdom); then there is no OS preference.
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

/** Shows `theme`: sets data-theme on <html>, which switches theme.css's token set. */
export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
}

/** Remembers the user's choice. False when the browser will not store it; the theme still applies. */
export function storeTheme(theme: Theme): boolean {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
    return true
  } catch {
    return false
  }
}

/** The theme <html> shows now: light only when data-theme says so (main.tsx applies it before the first render). */
export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark'
}

/** The current theme and a toggle that applies the other one and remembers it. */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(currentTheme)
  function toggle() {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    applyTheme(next)
    storeTheme(next)
    setTheme(next)
  }
  return [theme, toggle]
}
