import type { LengthRow } from '@lib/contract/types'
import type { CoordinateScale } from './CoordinateScale'
import { parsePasUid } from './CoordinateScale'

interface LengthOverlayLayerProps {
  scale: CoordinateScale
  lengths: LengthRow[]
  strategy: LengthRow['strategy']
  directionFilter?: LengthRow['direction']
  rowHeight?: number
}

const DIRECTION_MARK: Record<NonNullable<LengthRow['direction']>, string> = {
  shorten: '▾',
  lengthen: '▴',
  flat: '·',
  undetermined: '?',
}

/**
 * `switch length` overlay: one sub-row per strategy (classic / proportion /
 * shannon); shorten/lengthen/flat/undetermined direction (design §1.4).
 * `direction` is populated for all three strategies (engine 2026-07-14
 * correction) -- what's STILL proportion-only is `pas_uid`/`rank` (a grain
 * difference: proportion is the only strategy with a per-PAS row; classic/
 * shannon are per-cell/per-gene aggregates), which is why classic/shannon
 * render as a summary badge instead of per-PAS ticks below. That's a design
 * choice about row grain, not a gated/missing-data state.
 */
/** Bare SVG children (no own `<svg>`) -- caller (GeneviewSvg) positions this
 * row inside the composed document so toggled overlays export too. */
export function LengthOverlayLayer({ scale, lengths, strategy, directionFilter, rowHeight = 24 }: LengthOverlayLayerProps) {
  const rows = lengths.filter((l) => l.strategy === strategy && (!directionFilter || l.direction === directionFilter))
  const perPas = rows.filter((r) => r.pas_uid !== null)
  const aggregateOnly = perPas.length === 0 && rows.length > 0

  if (aggregateOnly) {
    return (
      <g className="geneview-layer geneview-layer--length-overlay" data-strategy={strategy}>
        <text x={4} y={rowHeight / 2 + 4} fontSize={9} style={{ fill: 'var(--track-tick)' }}>
          length: {strategy} (aggregate only, {rows.length} cells -- classic/shannon are per-cell/per-gene, not per-PAS)
        </text>
      </g>
    )
  }

  return (
    <g className="geneview-layer geneview-layer--length-overlay" data-strategy={strategy}>
      <text x={4} y={rowHeight - 8} fontSize={9} style={{ fill: 'var(--track-tick)' }}>
        length: {strategy}
      </text>
      {perPas.map((l, i) => {
        const parsed = parsePasUid(l.pas_uid!)
        if (!parsed) return null
        const x = scale.toPixel(parsed.pos)
        return (
          <text key={`${l.pas_uid}-${i}`} x={x} y={rowHeight / 2 + 4} fontSize={12} textAnchor="middle" style={{ fill: 'var(--track-ink)' }}>
            {l.direction ? DIRECTION_MARK[l.direction] : '?'}
            <title>
              {l.pas_uid} · value={l.value.toFixed(3)} · {l.direction ?? 'unknown'}
            </title>
          </text>
        )
      })}
    </g>
  )
}
