import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiUrl, fetchHealth, fetchOverlap, fetchOverlaps, fetchProjects } from './api'
import { apiExample, expectOverlap, expectProject } from './test/apiExamples'

function jsonResponse(body: unknown, status = 200, statusText = 'OK'): Response {
  return new Response(JSON.stringify(body), {
    status,
    statusText,
    headers: { 'Content-Type': 'application/json' },
  })
}

const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  vi.stubEnv('VITE_API_URL', 'http://api.test:8000')
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const requestedUrl = () => fetchMock.mock.calls[0][0]

describe('apiUrl', () => {
  it('joins VITE_API_URL and the path', () => {
    expect(apiUrl('/projects')).toBe('http://api.test:8000/projects')
  })

  it('handles trailing slashes on the base and a missing leading slash on the path', () => {
    vi.stubEnv('VITE_API_URL', 'https://gridwatch.example/api/')
    expect(apiUrl('/overlaps')).toBe('https://gridwatch.example/api/overlaps')
    expect(apiUrl('overlaps')).toBe('https://gridwatch.example/api/overlaps')
  })

  it('throws when VITE_API_URL is missing', () => {
    vi.stubEnv('VITE_API_URL', '')
    expect(() => apiUrl('/projects')).toThrow('VITE_API_URL is not set')
  })

  it('does not call fetch when VITE_API_URL is missing', async () => {
    vi.stubEnv('VITE_API_URL', '')
    await expect(fetchProjects()).rejects.toThrow('VITE_API_URL is not set')
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('fetchers', () => {
  it('fetchHealth GETs /health and returns the body', async () => {
    fetchMock.mockResolvedValue(jsonResponse(apiExample('health')))
    await expect(fetchHealth()).resolves.toEqual({ status: 'ok' })
    expect(requestedUrl()).toBe('http://api.test:8000/health')
  })

  it('fetchProjects GETs /projects and returns contract-shaped projects', async () => {
    fetchMock.mockResolvedValue(jsonResponse(apiExample('projects')))
    const projects = await fetchProjects()
    expect(requestedUrl()).toBe('http://api.test:8000/projects')
    expect(projects.map((p) => p.project_id)).toEqual(['DESC_3', 'GPC_2'])
    projects.forEach(expectProject)
  })

  it('fetchOverlaps GETs /overlaps and keeps rank order', async () => {
    fetchMock.mockResolvedValue(jsonResponse(apiExample('overlaps')))
    const overlaps = await fetchOverlaps()
    expect(requestedUrl()).toBe('http://api.test:8000/overlaps')
    expect(overlaps.map((o) => o.rank)).toEqual([1, 2])
    overlaps.forEach(expectOverlap)
  })

  it('fetchOverlap GETs /overlaps/{overlap_id}', async () => {
    fetchMock.mockResolvedValue(jsonResponse(apiExample('overlap')))
    const overlap = await fetchOverlap('OVL_2')
    expect(requestedUrl()).toBe('http://api.test:8000/overlaps/OVL_2')
    expect(overlap.overlap_id).toBe('OVL_2')
  })

  it('fetchOverlap URL-encodes the overlap_id', async () => {
    fetchMock.mockResolvedValue(jsonResponse(apiExample('overlap')))
    await fetchOverlap('a/b ?#')
    expect(requestedUrl()).toBe('http://api.test:8000/overlaps/a%2Fb%20%3F%23')
  })
})

describe('non-2xx responses', () => {
  it('throws an error carrying the status for a 404', async () => {
    fetchMock.mockResolvedValue(jsonResponse(apiExample('not_found'), 404, 'Not Found'))
    await expect(fetchOverlap('OVL_99')).rejects.toThrow(
      'GET http://api.test:8000/overlaps/OVL_99 failed with status 404 Not Found',
    )
  })

  it('throws an error carrying the status for a 500', async () => {
    fetchMock.mockResolvedValue(new Response('boom', { status: 500 }))
    await expect(fetchProjects()).rejects.toThrow('failed with status 500')
  })
})
