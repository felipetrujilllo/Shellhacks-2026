// Sun/moon button in the top bar that switches between the light and dark themes (#45).
import type { Theme } from '../theme'

interface ThemeToggleProps {
  theme: Theme
  onToggle: () => void
}

/**
 * A toggle button named "Light theme": pressed in the light theme, not pressed in the dark one
 * (a fixed name plus aria-pressed, as the WAI-ARIA toggle button pattern asks, so a screen reader
 * says "Light theme, toggle button, pressed"). The icon and tooltip show what a click does.
 */
export default function ThemeToggle({ theme, onToggle }: ThemeToggleProps) {
  const light = theme === 'light'
  return (
    <button type="button" className="theme-toggle" aria-label="Light theme" aria-pressed={light}
      title={light ? 'Switch to dark theme' : 'Switch to light theme'} onClick={onToggle}>
      <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        {light
          ? <path data-icon="moon" d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z" />
          : <g data-icon="sun"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></g>}
      </svg>
    </button>
  )
}
