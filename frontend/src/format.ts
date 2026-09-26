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
