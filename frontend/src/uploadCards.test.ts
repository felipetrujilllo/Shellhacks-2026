import { describe, expect, it } from 'vitest'
import type { ImportBatch, ImportRow } from './importProjects'
import type { Project } from './types'
import { uploadCards } from './uploadCards'

/** An upload as the server serves it (SUB-<client id>). */
const served = (clientId: string, utility: string) => ({ project_id: `SUB-${clientId}`, utility, project_name: clientId }) as Project
const ok = (row: number, clientId: string, utility: string): ImportRow =>
  ({ row, name: clientId, utility, issues: [], project: { project_id: clientId, utility } as Project })
const flagged = (row: number, utility: string, issue = 'lat_center is invalid'): ImportRow =>
  ({ row, name: `Row ${row}`, utility, issues: [issue], project: null })
const batch = (id: string, filename: string, rows: ImportRow[]): ImportBatch => ({ id, filename, rows })

describe('uploadCards', () => {
  it('makes one card for a file with one company: its file, mapped count and flagged rows', () => {
    const rows = [ok(2, 'b1-1', 'Tallapoosa'), ok(3, 'b1-2', 'Tallapoosa'), flagged(4, 'Tallapoosa')]
    expect(uploadCards([served('b1-1', 'Tallapoosa'), served('b1-2', 'Tallapoosa')], { 'b1-1': 'al.csv', 'b1-2': 'al.csv' }, [batch('b1', 'al.csv', rows)]))
      .toEqual([{ kind: 'company', utility: 'Tallapoosa', mapped: 2, files: ['al.csv'], flagged: [rows[2]] }])
  })

  it('makes one card per company for a file with two, each naming the file', () => {
    const rows = [ok(2, 'b1-1', 'A'), ok(3, 'b1-2', 'B')]
    const cards = uploadCards([served('b1-1', 'A'), served('b1-2', 'B')], { 'b1-1': 'two.csv', 'b1-2': 'two.csv' }, [batch('b1', 'two.csv', rows)])
    expect(cards).toEqual([
      { kind: 'company', utility: 'A', mapped: 1, files: ['two.csv'], flagged: [] },
      { kind: 'company', utility: 'B', mapped: 1, files: ['two.csv'], flagged: [] },
    ])
  })

  it('lists both files when one company\'s projects came from two', () => {
    const cards = uploadCards([served('b1-1', 'A'), served('b2-1', 'A'), served('b2-2', 'A')],
      { 'b1-1': 'first.csv', 'b2-1': 'second.csv', 'b2-2': 'second.csv' }, [])
    expect(cards).toEqual([{ kind: 'company', utility: 'A', mapped: 3, files: ['first.csv', 'second.csv'], flagged: null }])
  })

  it('gives flagged rows with no company, or whose company has nothing mapped, a card headed by the file', () => {
    const rows = [ok(2, 'b1-1', 'A'), flagged(3, '', 'Utility is missing'), flagged(4, 'Ghost Co')]
    expect(uploadCards([served('b1-1', 'A')], { 'b1-1': 'mixed.csv' }, [batch('b1', 'mixed.csv', rows)])).toEqual([
      { kind: 'company', utility: 'A', mapped: 1, files: ['mixed.csv'], flagged: [] },
      { kind: 'file', id: 'b1', filename: 'mixed.csv', flagged: [rows[1], rows[2]] },
    ])
  })

  it('gives a file where every row was flagged a card headed by the file', () => {
    const rows = [flagged(2, 'A'), flagged(3, '', 'Utility is missing')]
    expect(uploadCards([], {}, [batch('b1', 'bad.csv', rows)])).toEqual([{ kind: 'file', id: 'b1', filename: 'bad.csv', flagged: rows }])
  })

  it('after a refresh (no batches) keeps the saved file names but knows no flagged rows', () => {
    expect(uploadCards([served('b1-1', 'A')], { 'b1-1': 'al.csv' }, []))
      .toEqual([{ kind: 'company', utility: 'A', mapped: 1, files: ['al.csv'], flagged: null }])
  })

  it('leaves the file list empty for uploads saved without a file name', () => {
    expect(uploadCards([served('old-1', 'A'), served('old-2', 'A')], {}, []))
      .toEqual([{ kind: 'company', utility: 'A', mapped: 2, files: [], flagged: null }])
  })

  it('makes no cards when nothing was uploaded', () => {
    expect(uploadCards([], {}, [])).toEqual([])
  })
})
