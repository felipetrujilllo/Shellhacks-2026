// The "minimum match" slider on the map (#54). Presentational: App owns the value (minMatch) and
// applies filterByMinMatch; this only shows it and reports the stop the user picks.
import type { CSSProperties } from 'react'
import { MATCH_STEPS, matchLabel } from '../matchFilter'

/** The range input works in whole percents (0, 5, …, 90) so the browser's own stepping lands on a stop. */
const PCT_STEP = 5
const MAX_PCT = (MATCH_STEPS.length - 1) * PCT_STEP

/** The MATCH_STEPS entry for a whole percent from the input (never a float like 0.7000000000000001). */
function stepFromPct(pct: number): number {
  const step = MATCH_STEPS[pct / PCT_STEP]
  if (step === undefined) throw new RangeError(`the slider gave ${pct}, not one of 0–${MAX_PCT} in ${PCT_STEP}s`)
  return step
}

interface MatchSliderProps {
  /** One of MATCH_STEPS (0 = "All"). */
  value: number
  onChange: (min: number) => void
}

export default function MatchSlider({ value, onChange }: MatchSliderProps) {
  const label = matchLabel(value) // also fails loud on a value that isn't a stop
  const pct = Math.round(value * 100)
  return (
    <div className="match-slider map-control" title="Minimum match: hide pairs below it">
      {/* The input's aria-valuetext already reads this out; hidden so it isn't announced twice. */}
      <output aria-hidden="true">{label}</output>
      <input
        type="range"
        aria-label="Minimum match"
        aria-valuetext={label}
        min={0}
        max={MAX_PCT}
        step={PCT_STEP}
        value={pct}
        // How far the gold "active" part of the track reaches (workspace.css).
        style={{ '--match-fill': `${(pct / MAX_PCT) * 100}%` } as CSSProperties}
        onChange={(e) => onChange(stepFromPct(Number(e.target.value)))}
      />
    </div>
  )
}
