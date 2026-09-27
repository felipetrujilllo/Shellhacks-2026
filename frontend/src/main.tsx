// The palette loads first: every stylesheet and the map's color constants (theme.ts) read its tokens.
import './theme.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { applyTheme, getInitialTheme } from './theme'

// Before the first render, so the page never shows the wrong theme first (#45).
applyTheme(getInitialTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
