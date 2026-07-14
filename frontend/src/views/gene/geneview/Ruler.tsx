import type { CoordinateScale } from './CoordinateScale'

/** Pick ONE display unit for the WHOLE ruler from the total window span --
 * same thresholds as PeakATail's own `gene_track_matplotlib.py` (<5kb -> bp,
 * 5kb-1Mb -> kb, >=1Mb -> Mb). Deliberately NOT chosen per-tick from each
 * tick's own absolute value (the previous approach): on a sub-kb window
 * every tick's absolute coordinate is itself >=1000 (e.g. chr1:999-1500), so
 * per-tick formatting put every tick in kb regardless of the window's own
 * span -- fine on its own, but combined with a fixed 1-decimal precision it
 * silently rounded a 50bp tick spacing down to indistinguishable duplicate
 * labels ("1.1kb", "1.1kb", "1.1kb", ...). Decimals are derived from the
 * actual tick spacing so adjacent ticks are always visibly distinct. */
function chooseUnit(span: number): { div: number; suffix: string } {
  if (span >= 1_000_000) return { div: 1_000_000, suffix: 'Mb' }
  if (span >= 5_000) return { div: 1_000, suffix: 'kb' }
  return { div: 1, suffix: 'bp' }
}

function decimalsFor(step: number, div: number): number {
  const valueStep = step / div
  if (valueStep >= 1) return 0
  return Math.max(0, Math.ceil(-Math.log10(valueStep)))
}

/** Pick a "nice" tick step (1/2/5 x 10^n) for the given genomic span. */
function niceStep(span: number, targetTicks = 8): number {
  const raw = span / targetTicks
  const mag = 10 ** Math.floor(Math.log10(raw))
  const norm = raw / mag
  const step = norm < 1.5 ? 1 : norm < 3.5 ? 2 : norm < 7.5 ? 5 : 10
  return step * mag
}

interface RulerProps {
  scale: CoordinateScale
  height?: number
}

/**
 * Ruler + coordinate ticks -- always-on layer per design doc §1. Bare SVG
 * children (no own `<svg>`/positioning) -- the caller (GeneviewSvg) places
 * this inside the single composed document so "export current view"
 * captures it along with every track.
 */
export function Ruler({ scale, height = 28 }: RulerProps) {
  const { window: win } = scale
  const step = niceStep(win.end - win.start)
  const firstTick = Math.ceil(win.start / step) * step
  const ticks: number[] = []
  for (let t = firstTick; t <= win.end; t += step) ticks.push(t)
  const unit = chooseUnit(win.end - win.start)
  const decimals = decimalsFor(step, unit.div)

  return (
    <g className="geneview-layer geneview-layer--ruler">
      <rect x={0} y={0} width={scale.pixelWidth} height={height} style={{ fill: 'var(--track-ruler-bg)' }} />
      <line x1={0} y1={height - 1} x2={scale.pixelWidth} y2={height - 1} style={{ stroke: 'var(--track-baseline)' }} />
      {ticks.map((t) => {
        const x = scale.toPixel(t)
        return (
          <g key={t}>
            <line x1={x} y1={height - 8} x2={x} y2={height} style={{ stroke: 'var(--track-tick)' }} />
            <text x={x} y={height - 12} textAnchor="middle" fontSize={9} style={{ fill: 'var(--track-tick)' }}>
              {(t / unit.div).toFixed(decimals)}
              {unit.suffix}
            </text>
          </g>
        )
      })}
      <text x={4} y={10} fontSize={10} style={{ fill: 'var(--track-ink)' }}>
        {win.chrom}:{win.start.toLocaleString()}-{win.end.toLocaleString()}
      </text>
    </g>
  )
}
