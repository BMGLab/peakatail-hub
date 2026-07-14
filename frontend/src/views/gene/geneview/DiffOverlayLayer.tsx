import type { FindingRow } from '@lib/contract/types'
import type { CoordinateScale } from './CoordinateScale'
import { parsePasUid } from './CoordinateScale'

interface DiffOverlayLayerProps {
  scale: CoordinateScale
  findings: FindingRow[]
  strategy: FindingRow['strategy']
  qMax?: number
  significantOnly?: boolean
  rowHeight?: number
}

const DIRECTION_COLOR: Record<FindingRow['direction'], string> = {
  shorten: 'var(--danger)',
  lengthen: 'var(--ok)',
  flat: 'var(--text-dim)',
  undetermined: 'var(--border)',
}

/**
 * `switch diff` overlay: one sub-row per strategy (fisher / nb_pairwise /
 * nb_multi); tick per called PAS encoding q + delta_proportion (design §1.3).
 * Coordinates are derived from `pas_uid` per docs §7d (never the diff TSV's
 * own coord columns, which are blank until engine change B4).
 */
export function DiffOverlayLayer({ scale, findings, strategy, qMax = 1, significantOnly = false, rowHeight = 24 }: DiffOverlayLayerProps) {
  const rows = findings.filter((f) => f.strategy === strategy && f.qvalue <= qMax && (!significantOnly || f.qvalue <= 0.05))

  return (
    <svg width={scale.pixelWidth} height={rowHeight} className="geneview-layer geneview-layer--diff-overlay" data-strategy={strategy}>
      <text x={4} y={rowHeight - 8} fontSize={9} fill="var(--text-dim)">
        diff: {strategy}
      </text>
      {rows.map((f) => {
        const parsed = parsePasUid(f.pas_uid)
        if (!parsed) return null
        const x = scale.toPixel(parsed.pos)
        const r = Math.max(2, Math.min(8, Math.abs(f.delta_proportion) * 12))
        return (
          <circle key={f.finding_uid} cx={x} cy={rowHeight / 2} r={r} fill={DIRECTION_COLOR[f.direction]} opacity={0.85}>
            <title>
              {f.pas_uid} · q={f.qvalue.toFixed(4)} · Δ={f.delta_proportion.toFixed(3)} · {f.direction}
            </title>
          </circle>
        )
      })}
    </svg>
  )
}
