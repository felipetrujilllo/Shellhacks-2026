// Headline savings aggregation: pure data logic, kept out of format.ts (which only words numbers)
// and out of App so it can be tested without rendering.
import type { Overlap } from './types'

export interface SavingsSummary {
  /** Pairs considered (estimated + not estimated). */
  pairCount: number
  /** Pairs with a known est_savings_usd. */
  estimatedCount: number
  /** Pairs whose est_savings_usd is null (e.g. Georgia Power-only costs, uploaded proposals). */
  notEstimatedCount: number
  /** Sum of the known est_savings_usd values, whole dollars; nulls are excluded, not counted as 0. */
  totalUsd: number
}

export function summarizeSavings(overlaps: Pick<Overlap, 'est_savings_usd'>[]): SavingsSummary {
  let totalUsd = 0
  let estimatedCount = 0
  for (const o of overlaps) {
    if (o.est_savings_usd === null) continue
    totalUsd += o.est_savings_usd
    estimatedCount += 1
  }
  return {
    pairCount: overlaps.length,
    estimatedCount,
    notEstimatedCount: overlaps.length - estimatedCount,
    totalUsd,
  }
}
