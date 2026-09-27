import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Project } from './types'
import { UNREADABLE_UPLOADS, UPLOAD_FILES_STORAGE_KEY, UPLOADS_STORAGE_KEY, loadUploadFiles, loadUploads, saveUploadFiles, saveUploads } from './uploadCache'

function memoryStorage(initial: Record<string, string> = {}): Storage {
  const data = new Map(Object.entries(initial))
  return {
    get length() { return data.size },
    clear: () => data.clear(),
    getItem: (key: string) => data.get(key) ?? null,
    key: (i: number) => [...data.keys()][i] ?? null,
    removeItem: (key: string) => { data.delete(key) },
    setItem: (key: string, value: string) => { data.set(key, String(value)) },
  }
}

const refuse = () => { throw new DOMException('The operation is insecure.', 'SecurityError') }
const blocked = { get length() { return refuse() }, clear: refuse, getItem: refuse, key: refuse, removeItem: refuse, setItem: refuse }

const upload = { project_id: 'b1-1', utility: 'Savannah Water', project_name: 'Water main' } as Project

afterEach(() => { vi.unstubAllGlobals() })

describe('uploadCache', () => {
  it('round-trips the uploads under relay.uploads.v1', () => {
    const storage = memoryStorage()
    vi.stubGlobal('localStorage', storage)
    expect(loadUploads()).toEqual({ uploads: [], available: true, problem: null })
    expect(saveUploads([upload])).toBe(true)
    expect(JSON.parse(storage.getItem('relay.uploads.v1')!)).toEqual([upload])
    expect(loadUploads()).toEqual({ uploads: [upload], available: true, problem: null })
  })

  it('removes the key when the list is emptied', () => {
    const storage = memoryStorage({ [UPLOADS_STORAGE_KEY]: JSON.stringify([upload]) })
    vi.stubGlobal('localStorage', storage)
    expect(saveUploads([])).toBe(true)
    expect(storage.getItem(UPLOADS_STORAGE_KEY)).toBeNull()
  })

  it.each(['{not json', '{"project_id": "x"}', '[{"utility": "no id"}]', '[null]'])(
    'reports unreadable data (%s) instead of throwing', raw => {
      vi.stubGlobal('localStorage', memoryStorage({ [UPLOADS_STORAGE_KEY]: raw }))
      expect(loadUploads()).toEqual({ uploads: [], available: true, problem: UNREADABLE_UPLOADS })
    })

  it('never throws when the browser refuses storage', () => {
    vi.stubGlobal('localStorage', blocked)
    expect(loadUploads()).toEqual({ uploads: [], available: false, problem: null })
    expect(saveUploads([upload])).toBe(false)
    expect(saveUploads([])).toBe(false)
  })

  it('reports a full storage as not saved', () => {
    const storage = memoryStorage()
    storage.setItem = () => { throw new DOMException('Quota exceeded', 'QuotaExceededError') }
    vi.stubGlobal('localStorage', storage)
    expect(saveUploads([upload])).toBe(false)
  })
})

describe('uploadCache file names (#57)', () => {
  const other = { project_id: 'b2-1', utility: 'Tidewater Grid Co.', project_name: 'River crossing' } as Project

  it('round-trips each upload\'s file name under relay.uploads.files.v1, apart from the uploads', () => {
    const storage = memoryStorage()
    vi.stubGlobal('localStorage', storage)
    expect(loadUploadFiles()).toEqual({})
    expect(saveUploadFiles([upload, other], { 'b1-1': 'savannah.csv', 'b2-1': 'tidewater.csv' }))
      .toEqual({ 'b1-1': 'savannah.csv', 'b2-1': 'tidewater.csv' })
    expect(UPLOAD_FILES_STORAGE_KEY).toBe('relay.uploads.files.v1')
    expect(JSON.parse(storage.getItem('relay.uploads.files.v1')!)).toEqual({ 'b1-1': 'savannah.csv', 'b2-1': 'tidewater.csv' })
    expect(storage.getItem(UPLOADS_STORAGE_KEY)).toBeNull() // the uploads themselves are saved separately, unchanged
    expect(loadUploadFiles()).toEqual({ 'b1-1': 'savannah.csv', 'b2-1': 'tidewater.csv' })
  })

  it('keeps only the names of the uploads still kept, and removes the key when none are left', () => {
    const storage = memoryStorage()
    vi.stubGlobal('localStorage', storage)
    const files = { 'b1-1': 'savannah.csv', 'b2-1': 'tidewater.csv' }
    expect(saveUploadFiles([other], files)).toEqual({ 'b2-1': 'tidewater.csv' })
    expect(JSON.parse(storage.getItem(UPLOAD_FILES_STORAGE_KEY)!)).toEqual({ 'b2-1': 'tidewater.csv' })
    expect(saveUploadFiles([], files)).toEqual({})
    expect(storage.getItem(UPLOAD_FILES_STORAGE_KEY)).toBeNull()
  })

  it('stores nothing for uploads with no known file name (saved before #57)', () => {
    const storage = memoryStorage()
    vi.stubGlobal('localStorage', storage)
    expect(saveUploadFiles([upload], {})).toEqual({})
    expect(storage.getItem(UPLOAD_FILES_STORAGE_KEY)).toBeNull()
  })

  it.each(['{not json', '["a.csv"]', 'null', '"a.csv"'])('reads unreadable file names (%s) as none', raw => {
    vi.stubGlobal('localStorage', memoryStorage({ [UPLOAD_FILES_STORAGE_KEY]: raw }))
    expect(loadUploadFiles()).toEqual({})
  })

  it('drops entries that are not file names', () => {
    vi.stubGlobal('localStorage', memoryStorage({ [UPLOAD_FILES_STORAGE_KEY]: JSON.stringify({ 'b1-1': 'savannah.csv', 'b2-1': 7, 'b3-1': null }) }))
    expect(loadUploadFiles()).toEqual({ 'b1-1': 'savannah.csv' })
  })

  it('never throws when the browser refuses storage: no names saved, and this tab keeps them', () => {
    vi.stubGlobal('localStorage', blocked)
    expect(loadUploadFiles()).toEqual({})
    expect(saveUploadFiles([upload], { 'b1-1': 'savannah.csv' })).toEqual({ 'b1-1': 'savannah.csv' })
    expect(saveUploadFiles([], {})).toEqual({})
  })
})
