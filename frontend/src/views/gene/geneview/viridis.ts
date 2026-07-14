// Minimal viridis sequential colormap -- no d3-scale-chromatic dependency
// (this repo deliberately avoids the `d3` umbrella package, see the note in
// CoordinateScale.ts; the same reasoning applies here: this is a ~20-line
// lookup + lerp, not worth a new dependency).
//
// Stops and positions are copied EXACTLY from the design system's
// `--viridis-NN` tokens (src/app/theme/tokens.css, `--viridis-ramp`) rather
// than a fresh matplotlib sample, so a bar painted by this function and a
// swatch painted by `var(--viridis-NN)` elsewhere in the app are pixel-
// identical. Positions are NOT evenly spaced (00/15/30/45/60/70/82/92/100) --
// interpolation below uses each stop's real `t`, not its index.
const VIRIDIS_STOPS: { t: number; rgb: [number, number, number] }[] = [
  { t: 0.0, rgb: [0x44, 0x01, 0x54] }, // --viridis-00
  { t: 0.15, rgb: [0x47, 0x2d, 0x7b] }, // --viridis-15
  { t: 0.3, rgb: [0x3b, 0x52, 0x8b] }, // --viridis-30
  { t: 0.45, rgb: [0x2c, 0x72, 0x8e] }, // --viridis-45
  { t: 0.6, rgb: [0x21, 0x91, 0x8c] }, // --viridis-60
  { t: 0.7, rgb: [0x28, 0xae, 0x80] }, // --viridis-70
  { t: 0.82, rgb: [0x5e, 0xc9, 0x62] }, // --viridis-82
  { t: 0.92, rgb: [0xad, 0xdc, 0x30] }, // --viridis-92
  { t: 1.0, rgb: [0xfd, 0xe7, 0x25] }, // --viridis-100
]

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

/** viridis(t) for t in [0,1] (clamped) -> `rgb(r,g,b)` CSS color string. */
export function viridis(t: number): string {
  const x = Math.min(1, Math.max(0, t))
  let i0 = 0
  while (i0 < VIRIDIS_STOPS.length - 2 && VIRIDIS_STOPS[i0 + 1]!.t <= x) i0++
  const s0 = VIRIDIS_STOPS[i0]!
  const s1 = VIRIDIS_STOPS[i0 + 1]!
  const span = s1.t - s0.t || 1
  const frac = (x - s0.t) / span
  const r = Math.round(lerp(s0.rgb[0], s1.rgb[0], frac))
  const g = Math.round(lerp(s0.rgb[1], s1.rgb[1], frac))
  const b = Math.round(lerp(s0.rgb[2], s1.rgb[2], frac))
  return `rgb(${r}, ${g}, ${b})`
}

/** SVG <linearGradient> stop list for the colorbar (0 -> 1, top -> bottom
 * when the gradient is rendered with a vertical y1/y2) -- same stops/
 * positions as `--viridis-ramp` in tokens.css. */
export const VIRIDIS_GRADIENT_STOPS: { offset: string; color: string }[] = VIRIDIS_STOPS.map((s) => ({
  offset: `${s.t * 100}%`,
  color: `rgb(${s.rgb[0]}, ${s.rgb[1]}, ${s.rgb[2]})`,
}))

/** Grey used for "no data" (NaN proportion) bars/cells -- matches the
 * matplotlib reference's `#aaaaaa` NaN fallback in gene_track_matplotlib.py. */
export const NO_DATA_COLOR = '#aaaaaa'
