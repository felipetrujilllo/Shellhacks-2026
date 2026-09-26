// Single source of truth for utility colors: the map layers, the legend and every sidebar/detail
// swatch read these. Kept free of MapLibre imports so tests and non-map components can use it.

export const DESC = 'Dominion Energy South Carolina'
export const GPC = 'Georgia Power'

export const UTILITY_COLORS: Readonly<Record<string, string>> = {
  [DESC]: '#60a5fa', // blue
  [GPC]: '#f87171', // red
}

/** Any utility we don't have a named color for (e.g. an uploaded proposal's utility). */
export const OTHER_UTILITY_COLOR = '#a3be8c'

export function utilityColor(utility: string): string {
  return Object.hasOwn(UTILITY_COLORS, utility) ? UTILITY_COLORS[utility] : OTHER_UTILITY_COLOR
}
