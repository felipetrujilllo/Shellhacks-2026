import { BASEMAPS, type BasemapId } from './basemaps'

const SATELLITE: BasemapId = 'satellite'

interface BasemapToggleProps {
  /**
   * The basemaps on offer (basemapOptions() in basemaps.ts: they depend on the theme). The first
   * is the theme's own vector map, which turning satellite off goes back to.
   */
  options: readonly BasemapId[]
  value: BasemapId
  onChange: (id: BasemapId) => void
}

/**
 * The satellite on/off toggle (#59). There is no Dark/Light button: the top bar's theme toggle
 * already swaps the vector map between Dark Matter and Positron.
 */
export default function BasemapToggle({ options, value, onChange }: BasemapToggleProps) {
  const satelliteOn = value === SATELLITE
  return (
    <div role="group" aria-label="Basemap" className="map-control map-segmented border border-white/15 bg-slate-950/90">
      <button
        type="button"
        aria-pressed={satelliteOn}
        onClick={() => onChange(satelliteOn ? options[0] : SATELLITE)}
        className={`flex min-h-10 items-center gap-2 px-3 text-xs font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 ${satelliteOn ? 'bg-slate-700 text-white' : 'text-slate-400 hover:bg-white/10 hover:text-white'}`}
      >
        <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="m12 3 9 5-9 5-9-5 9-5Z" />
          <path d="m3 12 9 5 9-5M3 16l9 5 9-5" />
        </svg>
        {BASEMAPS[SATELLITE].label}
      </button>
    </div>
  )
}
