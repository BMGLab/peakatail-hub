import type { GeneviewPas } from '@lib/contract/types'
import type { CoordinateScale } from './CoordinateScale'

interface PASStemLayerProps {
  scale: CoordinateScale
  pas: GeneviewPas[]
  /** Which clusters' counts to sum for stem height; empty = all clusters. */
  clusters?: string[] | undefined
  height?: number
  onSelect?: ((pas: GeneviewPas) => void) | undefined
}

/**
 * Each PAS a stick at its 3' end; height = read count in selected
 * cluster/celltype (design doc §1.2). Counts are NOT UMI-deduplicated --
 * caveat surfaced inline, not hidden. Bare SVG children -- caller
 * (GeneviewSvg) positions this row inside the composed document.
 */
export function PASStemLayer({ scale, pas, clusters, height = 60, onSelect }: PASStemLayerProps) {
  const heights = pas.map((p) => {
    const entries = Object.entries(p.per_cluster_counts)
    const relevant = clusters && clusters.length > 0 ? entries.filter(([c]) => clusters.includes(c)) : entries
    return relevant.reduce((sum, [, n]) => sum + n, 0)
  })
  const maxHeight = Math.max(1, ...heights)

  return (
    <g className="geneview-layer geneview-layer--pas-stems">
      {pas.map((p, i) => {
        const x = scale.toPixel(p.end)
        const h = (heights[i]! / maxHeight) * (height - 12)
        return (
          <g
            key={p.pas_uid}
            className="pas-stem"
            tabIndex={0}
            role="button"
            aria-label={`PAS ${p.pas_uid}`}
            onClick={() => onSelect?.(p)}
            style={{ cursor: onSelect ? 'pointer' : undefined }}
          >
            <line x1={x} y1={height - 2} x2={x} y2={height - 2 - h} style={{ stroke: 'var(--accent)' }} strokeWidth={2} />
            <circle cx={x} cy={height - 2 - h} r={3} style={{ fill: 'var(--accent)' }}>
              <title>
                {p.pas_uid} · tier={p.tier ?? '—'} · reads={heights[i]}
              </title>
            </circle>
          </g>
        )
      })}
      <text x={4} y={height - 2} fontSize={8} style={{ fill: 'var(--warn)' }}>
        ⚠ raw read stems (not UMI-deduplicated)
      </text>
    </g>
  )
}
