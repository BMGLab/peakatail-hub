import type { GeneviewPas } from '@lib/contract/types'
import type { CoordinateScale } from './CoordinateScale'
import { MIN_PAS_WIDTH_PX } from './layout'

interface PASBandsLayerProps {
  scale: CoordinateScale
  pas: GeneviewPas[]
  /** Top/bottom y (in the same local coordinate frame as the plot-area <g>
   * this renders inside) the band should span -- from the top of the
   * isoform track through the bottom of the last visible cluster/overlay
   * row, so one continuous stripe reads across the whole stack (design
   * brief: "Vertical PAS BANDS spanning ALL panels"). */
  top: number
  bottom: number
  onHover?: ((pas: GeneviewPas | null, clientX: number, clientY: number) => void) | undefined
  onSelect?: ((pas: GeneviewPas) => void) | undefined
}

/**
 * Faint vertical stripe per PAS spanning every track, labelled with the
 * pas_uid at the top -- mirrors `_annotate_pas_positions()` in PeakATail's
 * `ema/viz/_gene_track_helpers.py` (same salmon wash, sourced from the
 * design system's `--pas-band-fill`/`--pas-label` tokens rather than a
 * fresh hardcoded color so it always matches the packaged figure). Rendered
 * first (behind track content) by the caller's paint order. Width is
 * clamped to `MIN_PAS_WIDTH_PX` so a narrow/singleton-bp PAS stays visible
 * at whole-gene zoom (same reasoning as the matplotlib reference's
 * `min_visible_w`).
 */
export function PASBandsLayer({ scale, pas, top, bottom, onHover, onSelect }: PASBandsLayerProps) {
  return (
    <g className="pas-bands">
      {pas.map((p) => {
        const x1raw = scale.toPixel(p.start)
        const x2raw = scale.toPixel(p.end)
        const w = Math.max(x2raw - x1raw, MIN_PAS_WIDTH_PX)
        const x1 = w > x2raw - x1raw ? x1raw - (w - (x2raw - x1raw)) / 2 : x1raw
        const centre = x1 + w / 2
        return (
          <g key={p.pas_uid}>
            <rect
              x={x1}
              y={top}
              width={w}
              height={Math.max(bottom - top, 0)}
              style={{ fill: 'var(--pas-band-fill)' }}
              onMouseEnter={(e) => onHover?.(p, e.clientX, e.clientY)}
              onMouseMove={(e) => onHover?.(p, e.clientX, e.clientY)}
              onMouseLeave={() => onHover?.(null, 0, 0)}
              onClick={() => onSelect?.(p)}
              className="pas-bands__rect"
            />
            <text x={centre} y={top - 4} fontSize={9} style={{ fill: 'var(--pas-label)' }} textAnchor="middle">
              {p.pas_uid.split(':')[1] ?? p.pas_uid}
            </text>
          </g>
        )
      })}
    </g>
  )
}
