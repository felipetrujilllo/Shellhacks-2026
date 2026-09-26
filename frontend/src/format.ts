// Display formatting for API values: one place so every component words numbers the same way.

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })

/** `5.65` -> `"5.7 mi"` (1 decimal). */
export function formatMiles(distanceMi: number): string {
  return `${distanceMi.toFixed(1)} mi`
}

/** `152` -> `"152 days"`, `1` -> `"1 day"`. */
export function formatDays(days: number): string {
  return `${days} ${days === 1 ? 'day' : 'days'}`
}

/** `709900` -> `"$709,900"` (whole dollars). */
export function formatUsd(amount: number): string {
  return usd.format(amount)
}

const usdCompact = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 1 })

/** `1500000` -> `"$1.5M"`, `709900` -> `"$709.9K"`, `0` -> `"$0"` (for headline tiles; use formatUsd for exact figures). */
export function formatUsdCompact(amount: number): string {
  return usdCompact.format(amount)
}

/** `1` -> `"1 pair"`, `6` -> `"6 pairs"`. */
export function formatPairs(count: number): string {
  return `${count} ${count === 1 ? 'pair' : 'pairs'}`
}
