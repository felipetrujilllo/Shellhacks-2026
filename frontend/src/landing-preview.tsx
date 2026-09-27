// Dev-only entry for landing-preview.html: renders the landing page on its own, outside the app.
// The palette loads first, like main.tsx, so every var(--…) token resolves.
import './theme.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import LandingPage from './components/LandingPage'
import { applyTheme, getInitialTheme } from './theme'

applyTheme(getInitialTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LandingPage />
  </StrictMode>,
)
