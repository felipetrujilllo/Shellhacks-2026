// Single source of truth for utility colors: the map layers, the legend and every sidebar/detail
// swatch read these. Kept free of MapLibre imports so tests and non-map components can use it.
// The colors themselves live in theme.css (--color-utility-*); the hex here is only the
// fallback for when theme.css isn't loaded, and must match it (theme.test.ts checks).
import { themeColor } from './theme'

export const DESC = 'Dominion Energy South Carolina'
export const GPC = 'Georgia Power'

export const UTILITY_COLORS: Readonly<Record<string, string>> = {
  [DESC]: themeColor('--color-utility-desc', '#60a5fa'), // blue
  [GPC]: themeColor('--color-utility-gpc', '#f87171'), // red
}

/** Any utility we don't have a named color for (e.g. an uploaded proposal's utility). */
export const OTHER_UTILITY_COLOR = themeColor('--color-utility-other', '#a3be8c')

export function utilityColor(utility: string): string {
  return Object.hasOwn(UTILITY_COLORS, utility) ? UTILITY_COLORS[utility] : OTHER_UTILITY_COLOR
}
