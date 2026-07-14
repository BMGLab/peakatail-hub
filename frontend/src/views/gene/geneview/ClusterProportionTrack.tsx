import type { GeneviewClusterTrack, GeneviewPas } from '@lib/contract/types'
import type { CoordinateScale } from './CoordinateScale'
import { viridis, NO_DATA_COLOR } from './viridis'
import { MIN_PAS_WIDTH_PX } from './layout'

interface ClusterProportionTrackProps {
  scale: CoordinateScale
  track: GeneviewClusterTrack
  pas: GeneviewPas[]
  height: number
  /** Shared y-axis cap across every rendered cluster track (so bar heights
   * are comparable row-to-row, matching the matplotlib reference's shared
   * y_cap) -- always >= the largest proportion actually present. */
  yMax: number
  onHover?: ((pas: GeneviewPas, track: GeneviewClusterTrack, clientX: number, clientY: number) => void) | undefined
  onLeave?: (() => void) | undefined
  onSelect?: ((pas: GeneviewPas, track: GeneviewClusterTrack) => void) | undefined
}

/**
 * One "cluster N (n=…)" mini bar chart: within-gene PAS-usage proportion at
 * each PAS position, bars coloured by proportion via viridis, % labels above
 * bars -- this is the core data view PeakATail's own gene-track figure is
 * built around (see `gene_track_matplotlib.py`'s per-cluster rows). Bare SVG
 * children; caller positions this inside the composed document.
 */
export function ClusterProportionTrack({
  scale,
  track,
  pas,
  height,
  yMax,
  onHover,
  onLeave,
  onSelect,
}: ClusterProportionTrackProps) {
  const baselineY = height - 14
  const plotH = baselineY - 6

  return (
    <g className="cluster-proportion-track">
      <line x1={0} y1={baselineY} x2={scale.pixelWidth} y2={baselineY} style={{ stroke: 'var(--track-baseline)' }} strokeWidth={0.8} />
      {/* y-axis ticks: 0 and yMax, matching the matplotlib reference's 0/0.5-ish scale */}
      <text x={-6} y={baselineY} fontSize={8} style={{ fill: 'var(--track-tick)' }} textAnchor="end" dominantBaseline="middle">
        0
      </text>
      <text x={-6} y={baselineY - plotH} fontSize={8} style={{ fill: 'var(--track-tick)' }} textAnchor="end" dominantBaseline="middle">
        {yMax.toFixed(2)}
      </text>
      <line x1={0} y1={baselineY - plotH} x2={0} y2={baselineY} style={{ stroke: 'var(--track-grid)' }} strokeWidth={0.6} />

      {track.values.map((v) => {
        const p = pas.find((pp) => pp.pas_uid === v.pas_uid)
        if (!p) return null
        const x1raw = scale.toPixel(p.start)
        const x2raw = scale.toPixel(p.end)
        const w = Math.max(x2raw - x1raw, MIN_PAS_WIDTH_PX)
        const x1 = x1raw - Math.max(0, w - (x2raw - x1raw)) / 2
        const prop = v.proportion
        const barH = prop !== null && Number.isFinite(prop) ? (Math.min(prop, yMax) / yMax) * plotH : 0
        const colour = prop !== null && Number.isFinite(prop) ? viridis(Math.min(1, Math.max(0, prop))) : NO_DATA_COLOR

        return (
          <g key={v.pas_uid}>
            <rect
              x={x1}
              y={baselineY - barH}
              width={w}
              height={barH}
              fill={colour}
              onMouseEnter={(e) => onHover?.(p, track, e.clientX, e.clientY)}
              onMouseMove={(e) => onHover?.(p, track, e.clientX, e.clientY)}
              onMouseLeave={() => onLeave?.()}
              onClick={() => onSelect?.(p, track)}
              className="cluster-proportion-track__bar"
            />
            {prop !== null && Number.isFinite(prop) && barH > 0 && (
              <text
                x={x1 + w / 2}
                y={baselineY - barH - 3}
                fontSize={8}
                style={{ fill: 'var(--track-ink)' }}
                textAnchor="middle"
              >
                {(prop * 100).toFixed(0)}%
              </text>
            )}
          </g>
        )
      })}
    </g>
  )
}
