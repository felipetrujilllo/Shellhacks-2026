import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Root, { isMapRoute } from './Root'

// The real App fetches data and mounts MapLibre; routing only needs to know which page is showing.
vi.mock('./App.tsx', () => ({ default: () => <main aria-label="map workspace" /> }))

const setHash = (hash: string) =>
  act(() => {
    window.location.hash = hash
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  })

const onLanding = () => screen.queryByRole('heading', { level: 1, name: /plan together/i })
const onMap = () => screen.queryByRole('main', { name: 'map workspace' })

afterEach(() => {
  window.history.replaceState(null, '', '/')
})

describe('isMapRoute', () => {
  it('matches #/map and paths under it, nothing else', () => {
    for (const hash of ['#/map', '#/map/', '#/map/pair/3', '#/map?x=1']) expect(isMapRoute(hash), hash).toBe(true)
    for (const hash of ['', '#', '#/', '#product', '#data', '#about', '#top', '#/mapx', '#map']) expect(isMapRoute(hash), hash).toBe(false)
  })
})

describe('Root routing', () => {
  it('shows the landing page at the site root, not the map', () => {
    render(<Root />)
    expect(onLanding()).not.toBeNull()
    expect(onMap()).toBeNull()
  })

  it('opens the map directly on a #/map deep link', () => {
    window.history.replaceState(null, '', '/#/map')
    render(<Root />)
    expect(onMap()).not.toBeNull()
    expect(onLanding()).toBeNull()
  })

  it('"Try the map" leads to the map workspace', () => {
    render(<Root />)
    const link = screen.getByRole('link', { name: /try the map/i })
    // jsdom does not navigate on anchor clicks, so follow the link's href the way the browser would.
    fireEvent.click(link)
    setHash(link.getAttribute('href')!)
    expect(onMap()).not.toBeNull()
    expect(onLanding()).toBeNull()
  })

  it('goes back to the landing page when the hash leaves #/map (browser back)', () => {
    window.history.replaceState(null, '', '/#/map')
    render(<Root />)
    setHash('')
    expect(onLanding()).not.toBeNull()
    expect(onMap()).toBeNull()
  })

  it('stays on the landing page for its own section anchors', () => {
    render(<Root />)
    for (const anchor of ['#product', '#data', '#about', '#top']) {
      setHash(anchor)
      expect(onLanding(), anchor).not.toBeNull()
    }
  })
})
