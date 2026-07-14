import type { GeneviewIsoform } from '@lib/contract/types'
import type { CoordinateScale } from './CoordinateScale'
import { ISOFORM_ROW_HEIGHT } from './layout'

interface IsoformTrackProps {
  scale: CoordinateScale
  isoforms: GeneviewIsoform[]
  strand: '+' | '-' | null
  height: number
}

// Colors come from the design system's track-canvas tokens (tokens.css §3)
// so this always matches the packaged CLIC2/DPYD reference figure exactly,
// in both light and dark chrome (the track canvas itself never re-skins).
const EXON_COLOUR = 'var(--track-model-exon)'
const INTRON_COLOUR = 'var(--track-model-intron)'
const EXON_HEIGHT_FRAC = 0.6

/**
 * Exon boxes + thin intron backbone + strand-direction arrows, one row per
 * transcript -- mirrors PeakATail's own `_draw_gene_structure()`
 * (ema/viz/_gene_track_helpers.py) so the hub's isoform track reads exactly
 * like the reference CLIC2/DPYD figures. Renders bare SVG children (no
 * wrapping <svg>/<g transform>) -- the caller (GeneviewSvg) positions this
 * inside the composed document so export captures it along with every other
 * track.
 */
export function IsoformTrack({ scale, isoforms, strand, height }: IsoformTrackProps) {
  if (isoforms.length === 0) {
    return (
      <text x={4} y={height / 2} fontSize={10} fill="var(--track-tick)" dominantBaseline="middle">
        no isoform structure available for this run (GTF not configured)
      </text>
    )
  }

  const rowH = Math.min(ISOFORM_ROW_HEIGHT, height / isoforms.length)

  return (
    <g className="isoform-track">
      <line x1={0} y1={height} x2={scale.pixelWidth} y2={height} stroke="var(--track-grid)" />
      {isoforms.map((iso, rowIdx) => {
        const yCentre = rowIdx * rowH + rowH / 2
        if (iso.exons.length === 0) return null
        const backboneStart = Math.min(...iso.exons.map((e) => e[0]))
        const backboneEnd = Math.max(...iso.exons.map((e) => e[1]))
        const x1 = scale.toPixel(backboneStart)
        const x2 = scale.toPixel(backboneEnd)
        const arrowStep = Math.max((x2 - x1) / 8, 6)
        const arrowDir = strand === '-' ? -1 : 1
        const arrowXs: number[] = []
        for (let x = x1 + arrowStep / 2; x < x2; x += arrowStep) arrowXs.push(x)

        return (
          <g key={iso.transcript_id} className="isoform-track__row">
            <line x1={x1} y1={yCentre} x2={x2} y2={yCentre} stroke={INTRON_COLOUR} strokeWidth={0.8} />
            {arrowXs.map((x, i) => (
              <path
                key={i}
                d={
                  arrowDir > 0
                    ? `M ${x - 3} ${yCentre - 3} L ${x + 3} ${yCentre} L ${x - 3} ${yCentre + 3}`
                    : `M ${x + 3} ${yCentre - 3} L ${x - 3} ${yCentre} L ${x + 3} ${yCentre + 3}`
                }
                fill="none"
                stroke={INTRON_COLOUR}
                strokeWidth={0.8}
              />
            ))}
            {iso.exons.map(([exonStart, exonEnd], i) => {
              const ex1 = scale.toPixel(exonStart)
              const ex2 = scale.toPixel(exonEnd)
              const minVisible = scale.pixelWidth * 0.004
              const w = Math.max(ex2 - ex1, minVisible)
              return (
                <rect
                  key={i}
                  x={ex1}
                  y={yCentre - (rowH * EXON_HEIGHT_FRAC) / 2}
                  width={w}
                  height={rowH * EXON_HEIGHT_FRAC}
                  fill={EXON_COLOUR}
                  rx={1.5}
                >
                  <title>
                    {iso.transcript_id} exon {exonStart.toLocaleString()}-{exonEnd.toLocaleString()}
                  </title>
                </rect>
              )
            })}
            <text x={4} y={yCentre} fontSize={9} fill="var(--track-label)" dominantBaseline="middle">
              {iso.transcript_id}
            </text>
          </g>
        )
      })}
    </g>
  )
}
