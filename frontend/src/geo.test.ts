import { describe, expect, it } from 'vitest'
import { overlapsToGeoJSON, projectsToGeoJSON } from './geo'
import { apiExample, expectOverlap, expectProject } from './test/apiExamples'
import type { Overlap, Project } from './types'

function project(overrides: Partial<Project>): Project {
  return {
    project_id: 'P_1',
    utility: 'Georgia Power',
    state: 'GA',
    project_name: 'Test line',
    name_a: 'A Sub',
    lat_a: 32.1,
    lon_a: -81.1,
    name_b: 'B Sub',
    lat_b: 32.3,
    lon_b: -81.5,
    lat_center: 32.2,
    lon_center: -81.3,
    in_service_date: '2026-01-01',
    est_cost_usd: null,
    location_confidence: 'confirmed',
    ...overrides,
  }
}

describe('projectsToGeoJSON', () => {
  it('turns a project with both endpoints into a LineString from a to b, as [lon, lat]', () => {
    const fc = projectsToGeoJSON([project({})])
    expect(fc.type).toBe('FeatureCollection')
    expect(fc.features).toHaveLength(1)
    expect(fc.features[0].geometry).toEqual({
      type: 'LineString',
      coordinates: [
        [-81.1, 32.1],
        [-81.5, 32.3],
      ],
    })
  })

  it('turns a project with only endpoint a into a Point at the center, as [lon, lat]', () => {
    const fc = projectsToGeoJSON([project({ lat_b: null, lon_b: null })])
    expect(fc.features[0].geometry).toEqual({ type: 'Point', coordinates: [-81.3, 32.2] })
  })

  it('turns a project with only endpoint b into a Point at the center', () => {
    const fc = projectsToGeoJSON([project({ lat_a: null, lon_a: null })])
    expect(fc.features[0].geometry).toEqual({ type: 'Point', coordinates: [-81.3, 32.2] })
  })

  it('treats an endpoint with only one of lat/lon as unknown', () => {
    const fc = projectsToGeoJSON([project({ lon_b: null })])
    expect(fc.features[0].geometry).toEqual({ type: 'Point', coordinates: [-81.3, 32.2] })
  })

  it('falls back to a center Point when neither endpoint is known', () => {
    const fc = projectsToGeoJSON([project({ lat_a: null, lon_a: null, lat_b: null, lon_b: null })])
    expect(fc.features[0].geometry).toEqual({ type: 'Point', coordinates: [-81.3, 32.2] })
  })

  it('keeps a coordinate of 0 (not treated as missing)', () => {
    const fc = projectsToGeoJSON([project({ lat_a: 0, lon_a: 0 })])
    expect(fc.features[0].geometry).toEqual({
      type: 'LineString',
      coordinates: [
        [0, 0],
        [-81.5, 32.3],
      ],
    })
  })

  it('gives every feature its project_id and utility', () => {
    const fc = projectsToGeoJSON([
      project({ project_id: 'DESC_1', utility: 'Dominion Energy South Carolina' }),
      project({ project_id: 'GPC_1', utility: 'Georgia Power', lat_b: null, lon_b: null }),
    ])
    expect(fc.features.map((f) => f.properties)).toEqual([
      { project_id: 'DESC_1', utility: 'Dominion Energy South Carolina' },
      { project_id: 'GPC_1', utility: 'Georgia Power' },
    ])
  })

  it('returns an empty FeatureCollection for no projects', () => {
    expect(projectsToGeoJSON([])).toEqual({ type: 'FeatureCollection', features: [] })
  })
})

describe('overlapsToGeoJSON', () => {
  it('turns each overlap into a LineString between the two project centers with overlap_id and rank', () => {
    const overlap: Overlap = {
      overlap_id: 'OVL_7',
      rank: 3,
      score: 0.5,
      distance_mi: 10,
      time_gap_days: 30,
      project_a: project({ project_id: 'A', lat_center: 32.0, lon_center: -81.0 }),
      project_b: project({ project_id: 'B', lat_center: 33.0, lon_center: -82.0 }),
    }
    const fc = overlapsToGeoJSON([overlap])
    expect(fc).toEqual({
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          geometry: {
            type: 'LineString',
            coordinates: [
              [-81.0, 32.0],
              [-82.0, 33.0],
            ],
          },
          properties: { overlap_id: 'OVL_7', rank: 3 },
        },
      ],
    })
  })
})

describe('docs/api.md examples', () => {
  it('the projects example matches the Project type and builds the expected features', () => {
    const projects = apiExample('projects') as unknown[]
    projects.forEach(expectProject)
    const fc = projectsToGeoJSON(projects as Project[])
    // DESC_3 has both endpoints; GPC_2 is missing endpoint b.
    expect(fc.features).toEqual([
      {
        type: 'Feature',
        geometry: {
          type: 'LineString',
          coordinates: [
            [-81.1246, 32.35912],
            [-81.032495, 32.333758],
          ],
        },
        properties: { project_id: 'DESC_3', utility: 'Dominion Energy South Carolina' },
      },
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [-81.175112, 32.352116] },
        properties: { project_id: 'GPC_2', utility: 'Georgia Power' },
      },
    ])
  })

  it('the overlaps example matches the Overlap type and builds center-to-center lines in rank order', () => {
    const overlaps = apiExample('overlaps') as unknown[]
    overlaps.forEach(expectOverlap)
    const fc = overlapsToGeoJSON(overlaps as Overlap[])
    expect(fc.features.map((f) => f.properties)).toEqual([
      { overlap_id: 'OVL_2', rank: 1 },
      { overlap_id: 'OVL_3', rank: 2 },
    ])
    expect(fc.features[1].geometry.coordinates).toEqual([
      [-81.0785475, 32.346439],
      [-81.1957885, 32.3004085],
    ])
  })

  it('the single overlap example matches the Overlap type', () => {
    expectOverlap(apiExample('overlap'))
  })
})
