import { describe, expect, it } from 'vitest'
import pkg from '../package.json'

// Guards the scaffold ticket: every library later tickets rely on is declared up front.
const REQUIRED_RUNTIME = ['maplibre-gl', 'react-map-gl']
const REQUIRED_DEV = [
  'tailwindcss',
  '@tailwindcss/vite',
  'vitest',
  '@testing-library/react',
  '@testing-library/jest-dom',
  'jsdom',
]

describe('package.json dependencies', () => {
  it.each(REQUIRED_RUNTIME)('declares runtime dependency %s', (name) => {
    expect(pkg.dependencies).toHaveProperty(name)
  })

  it.each(REQUIRED_DEV)('declares dev dependency %s', (name) => {
    expect(pkg.devDependencies).toHaveProperty(name)
  })

  it('pins react-map-gl to v8+ so react-map-gl/maplibre is available', () => {
    const major = Number(pkg.dependencies['react-map-gl'].replace(/^[^\d]*/, '').split('.')[0])
    expect(major).toBeGreaterThanOrEqual(8)
  })
})

describe('installed packages resolve', () => {
  it.each(['maplibre-gl', 'react-map-gl/maplibre', 'tailwindcss'])('resolves %s', (name) => {
    expect(import.meta.resolve(name)).toMatch(/node_modules/)
  })
})
