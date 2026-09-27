// Decorative sunset scene behind the landing page hero: transmission towers over a river and a treeline.
// Silhouettes, ground and wires are colored in landing.css with the theme tokens; only the sky, sun and
// river gradient stops below are literal colors, since a sunset has no place in the app palette:
//   #0d1b36 night navy (top-left sky), #3b2a55 dusky purple, #a4486a dusk rose, #e9784a sunset orange,
//   #ffb45c amber horizon, #ffd98a / #fff1c4 pale sun glow and disk, #f39a5a river reflection.

type Tower = { x: number; base: number; scale: number }

// Nearest (largest) first, receding to the right toward the sun. Tower art is a 100x200 unit drawing.
const TOWERS: Tower[] = [
  { x: 520, base: 708, scale: 3 },
  { x: 820, base: 695, scale: 2.1 },
  { x: 1040, base: 678, scale: 1.5 },
  { x: 1200, base: 664, scale: 1.08 },
  { x: 1320, base: 654, scale: 0.78 },
  { x: 1410, base: 647, scale: 0.56 },
  { x: 1478, base: 642, scale: 0.4 },
]

// Where the wires hang, in tower units: the ground wire on the peak, then the four insulator ends.
const ATTACH = [
  [50, 2],
  [6, 58],
  [94, 58],
  [14, 92],
  [86, 92],
]

const place = ({ x, base, scale }: Tower, [ux, uy]: number[]) => [x - 50 * scale + ux * scale, base - 200 * scale + uy * scale]

/** One sagging quadratic curve per attachment point between each pair of neighboring towers. */
function wirePaths(): string {
  const out: string[] = []
  for (let i = 0; i < TOWERS.length - 1; i++) {
    const [a, b] = [TOWERS[i], TOWERS[i + 1]]
    const sag = 26 * (a.scale + b.scale)
    for (const point of ATTACH) {
      const [x1, y1] = place(a, point)
      const [x2, y2] = place(b, point)
      out.push(`M${x1.toFixed(1)} ${y1.toFixed(1)}Q${((x1 + x2) / 2).toFixed(1)} ${(Math.max(y1, y2) + sag).toFixed(1)} ${x2.toFixed(1)} ${y2.toFixed(1)}`)
    }
  }
  return out.join('')
}

/** A bumpy treeline edge from x=0 to x=1600 around `top`, closed down to `bottom`. Deterministic, no randomness. */
function treeline(top: number, bottom: number, height: number, step: number, seed: number): string {
  let d = `M0 ${bottom}L0 ${top}`
  for (let x = step; x <= 1600 + step; x += step) {
    const bump = Math.abs(Math.sin(x * 0.013 + seed) + 0.6 * Math.sin(x * 0.041 + seed * 2)) * height
    d += `Q${x - step / 2} ${(top - bump).toFixed(0)} ${x} ${(top - bump * 0.35).toFixed(0)}`
  }
  return `${d}L${1600 + step} ${bottom}Z`
}

const WIRES = wirePaths()

// The energy pulses: a short gold dash runs along two of the wires, span by span toward the sun, so it
// reads as power being relayed tower to tower. One path per span (pathLength 100 so the dash math in
// landing.css is the same for every span); each span starts when the previous one ends. Motion lives in
// landing.css and is switched off for prefers-reduced-motion.
export const PULSE_LINES = [1, 4] // indexes into ATTACH: the upper-left and lower-right conductors
export const PULSE_SPAN_SECONDS = 0.6
export const PULSE_LINE_OFFSET_SECONDS = 2
function pulseSegments(): { d: string; delay: number }[] {
  const out: { d: string; delay: number }[] = []
  PULSE_LINES.forEach((line, lineIndex) => {
    for (let i = 0; i < TOWERS.length - 1; i++) {
      const [a, b] = [TOWERS[i], TOWERS[i + 1]]
      const sag = 26 * (a.scale + b.scale)
      const [x1, y1] = place(a, ATTACH[line])
      const [x2, y2] = place(b, ATTACH[line])
      out.push({
        d: `M${x1.toFixed(1)} ${y1.toFixed(1)}Q${((x1 + x2) / 2).toFixed(1)} ${(Math.max(y1, y2) + sag).toFixed(1)} ${x2.toFixed(1)} ${y2.toFixed(1)}`,
        delay: lineIndex * PULSE_LINE_OFFSET_SECONDS + i * PULSE_SPAN_SECONDS,
      })
    }
  })
  return out
}
const PULSES = pulseSegments()
const FAR_TREES = treeline(640, 700, 34, 28, 1)
const NEAR_BANK = treeline(812, 900, 60, 46, 4)

export default function LandingHero() {
  return (
    <svg className="landing-hero-art" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="landing-sky" x1="0" y1="0" x2="0.85" y2="1">
          <stop offset="0" stopColor="#0d1b36" />
          <stop offset="0.42" stopColor="#3b2a55" />
          <stop offset="0.68" stopColor="#a4486a" />
          <stop offset="0.86" stopColor="#e9784a" />
          <stop offset="1" stopColor="#ffb45c" />
        </linearGradient>
        <radialGradient id="landing-sun" cx="1250" cy="640" r="460" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#ffd98a" stopOpacity="0.95" />
          <stop offset="0.35" stopColor="#e9784a" stopOpacity="0.45" />
          <stop offset="1" stopColor="#e9784a" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="landing-river" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f39a5a" stopOpacity="0.85" />
          <stop offset="1" stopColor="#3b2a55" stopOpacity="0.9" />
        </linearGradient>
        <g id="landing-tower">
          <path d="M18 200L40 100L44 20L50 2L56 20L60 100L82 200M44 42L6 50L44 54M56 42L94 50L56 54M41 76L14 84L41 88M59 76L86 84L59 88M6 50v8M94 50v8M14 84v8M86 84v8" />
          <path className="landing-hero-lattice" d="M44 20L58 60M56 20L42 60M42 60L60 100M58 60L40 100M40 100L68.8 140M60 100L31.2 140M31.2 140L76.5 175M68.8 140L23.5 175M23.5 175L82 200M76.5 175L18 200M42 60H58M40 100H60M31.2 140H68.8M23.5 175H76.5" />
        </g>
      </defs>
      <rect width="1600" height="900" fill="url(#landing-sky)" />
      <rect width="1600" height="900" fill="url(#landing-sun)" />
      <circle cx="1250" cy="628" r="34" fill="#fff1c4" />
      <path className="landing-hero-far" d={FAR_TREES} />
      <rect className="landing-hero-ground" y="690" width="1600" height="40" />
      <path d="M0 722C400 706 900 740 1600 716V830H0Z" fill="url(#landing-river)" />
      <ellipse cx="1250" cy="760" rx="120" ry="7" fill="#fff1c4" opacity="0.5" />
      <ellipse cx="1250" cy="782" rx="70" ry="4" fill="#fff1c4" opacity="0.35" />
      <g className="landing-hero-tower">
        {TOWERS.map(({ x, base, scale }) => (
          <use key={x} href="#landing-tower" transform={`translate(${x - 50 * scale} ${base - 200 * scale}) scale(${scale})`} />
        ))}
      </g>
      <path className="landing-hero-wire" d={WIRES} />
      <g className="landing-hero-pulses">
        {PULSES.map(({ d, delay }) => (
          <path key={d} className="landing-hero-pulse" d={d} pathLength={100} style={{ animationDelay: `${delay}s` }} />
        ))}
      </g>
      <path className="landing-hero-near" d={NEAR_BANK} />
    </svg>
  )
}
