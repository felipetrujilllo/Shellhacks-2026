import { BASEMAPS, type BasemapId } from './basemaps'

interface BasemapToggleProps {
  /** The basemaps to offer, in order (basemapOptions() in basemaps.ts: they depend on the theme). */
  options: readonly BasemapId[]
  value: BasemapId
  onChange: (id: BasemapId) => void
}

export default function BasemapToggle({ options, value, onChange }: BasemapToggleProps) {
  return (
    <div role="group" aria-label="Basemap" className="map-control map-segmented border border-white/15 bg-slate-950/90">
      {options.map((id) => (
        <button
          key={id}
          type="button"
          aria-pressed={value === id}
          onClick={() => onChange(id)}
          className={`flex min-h-10 items-center gap-2 px-3 text-xs font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 ${value === id ? 'bg-slate-700 text-white' : 'text-slate-400 hover:bg-white/10 hover:text-white'}`}
        >
          <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            {id === 'dark' ? <path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z" />
              : id === 'light' ? <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>
              : <><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5M3 16l9 5 9-5" /></>}
          </svg>
          {BASEMAPS[id].label}
        </button>
      ))}
    </div>
  )
}
