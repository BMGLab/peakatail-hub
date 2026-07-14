import type { CoordinateScale } from './CoordinateScale'

function formatBp(bp: number): string {
  if (Math.abs(bp) >= 1_000_000) return `${(bp / 1_000_000).toFixed(2)}Mb`
  if (Math.abs(bp) >= 1_000) return `${(bp / 1_000).toFixed(1)}kb`
  return `${Math.round(bp)}bp`
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

/** Ruler + coordinate ticks -- always-on layer per design doc §1. */
export function Ruler({ scale, height = 28 }: RulerProps) {
  const { window: win } = scale
  const step = niceStep(win.end - win.start)
  const firstTick = Math.ceil(win.start / step) * step
  const ticks: number[] = []
  for (let t = firstTick; t <= win.end; t += step) ticks.push(t)

  return (
    <svg width={scale.pixelWidth} height={height} className="geneview-layer geneview-layer--ruler">
      <line x1={0} y1={height - 1} x2={scale.pixelWidth} y2={height - 1} stroke="var(--border)" />
      {ticks.map((t) => {
        const x = scale.toPixel(t)
        return (
          <g key={t}>
            <line x1={x} y1={height - 8} x2={x} y2={height} stroke="var(--border)" />
            <text x={x} y={height - 12} textAnchor="middle" fontSize={9} fill="var(--text-dim)">
              {formatBp(t)}
            </text>
          </g>
        )
      })}
      <text x={4} y={10} fontSize={10} fill="var(--text-dim)">
        {win.chrom}:{win.start.toLocaleString()}-{win.end.toLocaleString()}
      </text>
    </svg>
  )
}
