import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Project } from './types'
import { UNREADABLE_UPLOADS, UPLOADS_STORAGE_KEY, loadUploads, saveUploads } from './uploadCache'

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
