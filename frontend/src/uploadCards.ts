// The Uploads tab's cards (#57): one per company, never one per file plus one per company.
// Pure, so App.tsx only renders what this returns.
import { SUBMITTED_PROJECT_PREFIX, type ImportBatch, type ImportRow } from './importProjects'
import type { Project } from './types'
import type { UploadFiles } from './uploadCache'

/** A company with uploaded projects on the map: the only card with Remove. */
export interface CompanyCard {
  kind: 'company'
  utility: string
  /** Its uploaded projects the server scored (the map shows exactly these). */
  mapped: number
  /** The files they came from, in upload order; empty when none is known (saved before #57). */
  files: string[]
  /** Its flagged rows from files uploaded in this tab; null when none of its files were (after a refresh). */
  flagged: ImportRow[] | null
}

/** Flagged rows of one file with no company card to go under (no utility, or no mapped project for it). */
export interface FileCard {
  kind: 'file'
  id: string
  filename: string
  flagged: ImportRow[]
}

export type UploadCard = CompanyCard | FileCard

/**
 * @param submitted the uploads as the server serves them (SUB-<client id>), in upload order
 * @param files client id -> file name (uploadCache.ts)
 * @param batches the files uploaded in this tab, with their flagged rows
 */
export function uploadCards(submitted: Project[], files: UploadFiles, batches: ImportBatch[]): UploadCard[] {
  const byUtility = new Map<string, CompanyCard>()
  for (const p of submitted) {
    const card = byUtility.get(p.utility) ?? { kind: 'company', utility: p.utility, mapped: 0, files: [], flagged: null }
    byUtility.set(p.utility, card)
    card.mapped++
    const file = files[p.project_id.slice(SUBMITTED_PROJECT_PREFIX.length)]
    if (file !== undefined && !card.files.includes(file)) card.files.push(file)
  }
  const fileCards: FileCard[] = []
  for (const batch of batches) {
    const orphans: ImportRow[] = []
    for (const card of byUtility.values()) {
      if (batch.rows.some(r => r.project?.utility === card.utility)) card.flagged ??= []
    }
    for (const row of batch.rows) {
      if (row.project) continue
      const card = row.utility ? byUtility.get(row.utility) : undefined
      if (card) (card.flagged ??= []).push(row)
      else orphans.push(row)
    }
    if (orphans.length) fileCards.push({ kind: 'file', id: batch.id, filename: batch.filename, flagged: orphans })
  }
  return [...byUtility.values(), ...fileCards]
}
