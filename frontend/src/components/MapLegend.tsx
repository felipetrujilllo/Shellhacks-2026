// Map legend. Reads the same constants as the layer styles in mapStyle.ts.
import { UTILITY_COLORS } from '../colors'
import { themeColor } from '../theme'
import { LOW_CONFIDENCE_OPACITY, OVERLAP_COLOR, SELECTED_OVERLAP_COLOR } from './mapStyle'

// Neutral: the real layer uses each utility's color. Fallback must match theme.css.
const LOW_CONFIDENCE_SWATCH = themeColor('--color-legend-low-confidence', '#cbd5e1')

export default function MapLegend() {
  return (
    <details className="map-control relative border border-white/15 bg-slate-950/90 text-xs text-slate-200">
      <summary className="min-h-11 cursor-pointer px-3 py-3.5 font-semibold focus-visible:outline-2 focus-visible:outline-sky-400">Legend</summary>
      <div className="map-panel map-legend-panel border border-white/15 bg-slate-950/95">
        {Object.entries(UTILITY_COLORS).map(([utility, color]) => (
          <div key={utility} className="flex items-center gap-2">
            <span className="inline-block h-1 w-5 rounded-full" style={{ backgroundColor: color }} />
            {utility}
          </div>
        ))}
        <div className="flex items-center gap-2">
          <span aria-hidden="true" className="inline-flex w-5 items-center gap-1" style={{ opacity: LOW_CONFIDENCE_OPACITY }}>
            <span className="inline-block w-2 border-t-2 border-dotted" style={{ borderColor: LOW_CONFIDENCE_SWATCH }} />
            <span className="inline-block size-2 rounded-full border-2" style={{ borderColor: LOW_CONFIDENCE_SWATCH }} />
          </span>
          Low-confidence location (unconfirmed)
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block w-5 border-t-2 border-dashed" style={{ borderColor: OVERLAP_COLOR }} />
          Coordination opportunity
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block h-1 w-5 rounded-full" style={{ backgroundColor: SELECTED_OVERLAP_COLOR }} />
          Selected opportunity
        </div>
      </div>
    </details>
  )
}
