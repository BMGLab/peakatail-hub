import type { GeneSummary } from '@lib/contract/types'
import type { CoordinateScale } from './CoordinateScale'

interface GeneModelLayerProps {
  scale: CoordinateScale
  gene: GeneSummary
  height?: number
}

/**
 * Exons/introns/3'UTR + strand arrow -- always-on layer per design doc §1.
 * ROUGH PLACEHOLDER: real per-exon coordinates come from the GTF-derived
 * gene model (see PeakATail ema/annotate/gtftobed.py); until that's wired
 * through the contract/io packages we render one evenly-segmented block per
 * gene as a visual anchor so the layer stack + strand arrow direction can be
 * exercised end to end.
 */
export function GeneModelLayer({ scale, gene, height = 40 }: GeneModelLayerProps) {
  // Callers (GeneView) only mount this layer once `gene.start`/`end` are
  // confirmed non-null (span exists) -- see the `hasSpan` guard there.
  // Falling back to 0 here would silently draw a zero-width/garbage model
  // instead of the "coordinates unavailable" state GeneView already shows.
  if (gene.start === null || gene.end === null) return null
  const x1 = scale.toPixel(gene.start)
  const x2 = scale.toPixel(gene.end)
  const midY = height / 2
  const segments = 4
  const segWidth = (x2 - x1) / segments

  return (
    <svg width={scale.pixelWidth} height={height} className="geneview-layer geneview-layer--gene-model">
      <line x1={x1} y1={midY} x2={x2} y2={midY} stroke="var(--text-dim)" strokeWidth={1.5} />
      {Array.from({ length: segments }, (_, i) => (
        <rect
          key={i}
          x={x1 + i * segWidth}
          y={midY - 6}
          width={Math.max(1, segWidth - 2)}
          height={12}
          fill={i === segments - 1 ? 'var(--warn)' : 'var(--accent)'}
          opacity={0.85}
          rx={2}
        >
          <title>{i === segments - 1 ? "placeholder 3'UTR segment" : `placeholder exon ${i + 1}`}</title>
        </rect>
      ))}
      <text x={x1} y={midY + 24} fontSize={11} fill="var(--text-h)" fontWeight={600}>
        {gene.gene_name} ({gene.strand === '+' ? '→' : '←'})
      </text>
    </svg>
  )
}
