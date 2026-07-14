import type { CoordinateScale } from './CoordinateScale'

interface CoverageLayerProps {
  scale: CoordinateScale
  height?: number
}

/**
 * Coverage lane: reserved, filled per-cluster curve is roadmap B (true bigWig
 * coverage). Hidden by default in v1 (design §1.5) -- this component exists
 * so the layer stack + LayerPanel toggle wiring is real now, but it only ever
 * renders a "not available" placeholder until roadmap B lands.
 */
export function CoverageLayer({ scale, height = 32 }: CoverageLayerProps) {
  return (
    <div className="geneview-layer geneview-layer--coverage" style={{ width: scale.pixelWidth, height }}>
      <span className="geneview-layer__stub-note">Coverage lane (true bigWig coverage) -- roadmap B, not yet available.</span>
    </div>
  )
}
