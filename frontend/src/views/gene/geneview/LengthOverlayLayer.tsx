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
}

/**
 * `switch length` overlay: one sub-row per strategy (classic / proportion /
 * shannon); shorten/lengthen/flat direction (design §1.4). Per docs §7c, only
 * `proportion` is per-PAS (has a non-null pas_uid) -- classic/shannon are
 * per-cell/per-gene aggregates and are rendered as a summary badge instead of
 * per-PAS ticks until the engine change (E5) lands.
 */
export function LengthOverlayLayer({ scale, lengths, strategy, directionFilter, rowHeight = 24 }: LengthOverlayLayerProps) {
  const rows = lengths.filter((l) => l.strategy === strategy && (!directionFilter || l.direction === directionFilter))
  const perPas = rows.filter((r) => r.pas_uid !== null)
  const aggregateOnly = perPas.length === 0 && rows.length > 0

  if (aggregateOnly) {
    return (
      <div className="geneview-layer geneview-layer--length-overlay" data-strategy={strategy} style={{ height: rowHeight }}>
        <span className="badge badge--neutral" title="classic/shannon length values are per-cell/per-gene, not per-PAS -- gated pending E5">
          length: {strategy} (aggregate only, {rows.length} cells)
        </span>
      </div>
    )
  }

  return (
    <svg width={scale.pixelWidth} height={rowHeight} className="geneview-layer geneview-layer--length-overlay" data-strategy={strategy}>
      <text x={4} y={rowHeight - 8} fontSize={9} fill="var(--text-dim)">
        length: {strategy}
      </text>
      {perPas.map((l, i) => {
        const parsed = parsePasUid(l.pas_uid!)
        if (!parsed) return null
        const x = scale.toPixel(parsed.pos)
        return (
          <text key={`${l.pas_uid}-${i}`} x={x} y={rowHeight / 2 + 4} fontSize={12} textAnchor="middle" fill="var(--text)">
            {l.direction ? DIRECTION_MARK[l.direction] : '?'}
            <title>
              {l.pas_uid} · value={l.value.toFixed(3)} · {l.direction ?? 'unknown'}
            </title>
          </text>
        )
      })}
    </svg>
  )
}
