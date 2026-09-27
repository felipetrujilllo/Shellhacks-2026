// Sperry's coordination tiers in plain words: the single place the tier labels live, so the
// cards, the detail panel and the "why" sentence all say the same thing.
import type { CoordinationTier } from './types'

/** One label per tier; `Record` makes a missing tier a compile error. */
export const TIER_LABELS: Readonly<Record<CoordinationTier, string>> = {
  crossing: 'Crossing — must coordinate',
  shared_land: 'Share land & permits',
  site_logistics: 'Share site logistics',
  crews: 'Share crews & equipment',
}

/** The label for `tier`; throws on a tier the frontend does not know (API drift), instead of showing nothing. */
export function tierLabel(tier: CoordinationTier): string {
  const label = Object.hasOwn(TIER_LABELS, tier) ? TIER_LABELS[tier] : undefined
  if (label === undefined) throw new Error(`unknown coordination tier: ${String(tier)}`)
  return label
}
