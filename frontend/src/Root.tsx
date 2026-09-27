import { useEffect, useState } from 'react'
import App from './App.tsx'
import LandingPage, { MAP_HREF } from './components/LandingPage'

/** True when the URL hash points at the map workspace (#/map, or anything under it). */
export function isMapRoute(hash: string): boolean {
  return hash === MAP_HREF || hash.startsWith(`${MAP_HREF}/`) || hash.startsWith(`${MAP_HREF}?`)
}

/** Picks the page from the URL hash: the map workspace at #/map, the landing page everywhere else
    (including the landing page's own in-page anchors like #product). Hash-based so the static
    deploy needs no server-side routing, and the browser back button returns to the landing page. */
export default function Root() {
  const [hash, setHash] = useState(() => window.location.hash)
  const onMap = isMapRoute(hash)

  useEffect(() => {
    const onHashChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  // Entering the map from a scrolled landing page: start the workspace at the top.
  useEffect(() => {
    if (onMap) window.scrollTo(0, 0)
  }, [onMap])

  return onMap ? <App /> : <LandingPage />
}
