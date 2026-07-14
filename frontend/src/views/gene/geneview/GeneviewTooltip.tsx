import type { ReactNode } from 'react'

interface GeneviewTooltipProps {
  x: number
  y: number
  children: ReactNode
}

/**
 * Floating hover tooltip for PAS bars/bands (design brief: "Hover a PAS
 * bar/band → tooltip"). `position: fixed` at the raw `clientX`/`clientY` the
 * triggering mouse event reported -- deliberately NOT container-relative, so
 * callers never need to subtract a bounding-rect offset just to show a
 * tooltip. Not part of the composed `<svg>` (tooltips are transient UI
 * chrome, not part of what "export current view" should capture).
 */
export function GeneviewTooltip({ x, y, children }: GeneviewTooltipProps) {
  return (
    <div className="geneview-tooltip" style={{ left: x + 12, top: y + 12 }} role="tooltip">
      {children}
    </div>
  )
}
