import { VIRIDIS_GRADIENT_STOPS } from './viridis'

interface ColorbarProps {
  x: number
  top: number
  height: number
  width?: number
  gradientId: string
}

/**
 * Vertical viridis colorbar, "Within-gene proportion" 0..1 -- the reference
 * figure's right-side legend (`fig.colorbar(...)` in
 * `gene_track_matplotlib.py`). Part of the SAME composed SVG as the tracks
 * (not a separate HTML element) so "export current view" captures it too.
 */
export function Colorbar({ x, top, height, width = 16, gradientId }: ColorbarProps) {
  const barH = Math.min(height * 0.6, 220)
  const barTop = top + (height - barH) / 2

  return (
    <g className="geneview-colorbar">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="1" x2="0" y2="0">
          {VIRIDIS_GRADIENT_STOPS.map((s) => (
            <stop key={s.offset} offset={s.offset} stopColor={s.color} />
          ))}
        </linearGradient>
      </defs>
      <rect
        x={x}
        y={barTop}
        width={width}
        height={barH}
        fill={`url(#${gradientId})`}
        style={{ stroke: 'var(--track-baseline)' }}
        strokeWidth={0.5}
      />
      <text x={x + width + 4} y={barTop + 4} fontSize={9} style={{ fill: 'var(--track-ink)' }}>
        1.0
      </text>
      <text x={x + width + 4} y={barTop + barH / 2 + 3} fontSize={9} style={{ fill: 'var(--track-ink)' }}>
        0.5
      </text>
      <text x={x + width + 4} y={barTop + barH} fontSize={9} style={{ fill: 'var(--track-ink)' }}>
        0
      </text>
      <text
        x={x + width + 16}
        y={barTop + barH / 2}
        fontSize={9}
        style={{ fill: 'var(--track-ink)' }}
        textAnchor="middle"
        transform={`rotate(90, ${x + width + 16}, ${barTop + barH / 2})`}
      >
        Within-gene proportion
      </text>
    </g>
  )
}
