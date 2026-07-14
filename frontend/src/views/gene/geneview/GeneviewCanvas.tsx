import { useRef } from 'react'
import type { GeneviewLayerData, PasDetail } from '@lib/contract/types'
import { createCoordinateScale } from './CoordinateScale'
import { Ruler } from './Ruler'
import { GeneModelLayer } from './GeneModelLayer'
import { PASStemLayer } from './PASStemLayer'
import { DiffOverlayLayer } from './DiffOverlayLayer'
import { LengthOverlayLayer } from './LengthOverlayLayer'
import { CoverageLayer } from './CoverageLayer'
import type { GeneviewLayerState } from './LayerPanel'
import type { GenomicWindow } from './CoordinateScale'
import { ExportButton } from '@export/ExportButton'
import './GeneviewCanvas.css'

interface GeneviewCanvasProps {
  data: GeneviewLayerData
  window: GenomicWindow
  layers: GeneviewLayerState
  width?: number
  onZoomIn: (centerBp?: number) => void
  onZoomOut: (centerBp?: number) => void
  onPan: (deltaBp: number) => void
  onResetToGeneSpan: () => void
  onSelectPas?: ((pas: PasDetail) => void) | undefined
}

/**
 * Composes the independent toggleable layers over a shared genomic x-axis
 * (design doc §1 "Interactive geneview (centerpiece)"). This is the
 * MINIMAL-BUT-REAL scaffold: it renders against mock/windowed data now; the
 * full interactive zoom/box-select renderer is a later wave's job -- the
 * component boundaries below (CoordinateScale/Ruler/*Layer/LayerPanel) are
 * the contract that wave builds against.
 */
export function GeneviewCanvas({ data, window, layers, width = 900, onZoomIn, onZoomOut, onPan, onResetToGeneSpan, onSelectPas }: GeneviewCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const scale = createCoordinateScale(window, width)

  function handleWheel(e: React.WheelEvent) {
    e.preventDefault()
    const rect = e.currentTarget.getBoundingClientRect()
    const centerBp = scale.toGenomic(e.clientX - rect.left)
    if (e.deltaY < 0) onZoomIn(centerBp)
    else onZoomOut(centerBp)
  }

  return (
    <div className="geneview-canvas">
      <div className="geneview-canvas__toolbar">
        <button type="button" onClick={() => onZoomIn()}>
          Zoom in
        </button>
        <button type="button" onClick={() => onZoomOut()}>
          Zoom out
        </button>
        <button type="button" onClick={() => onPan(-Math.round((window.end - window.start) * 0.2))}>
          ← Pan
        </button>
        <button type="button" onClick={() => onPan(Math.round((window.end - window.start) * 0.2))}>
          Pan →
        </button>
        <button type="button" onClick={onResetToGeneSpan}>
          Reset to gene span
        </button>
        <ExportButton targetRef={containerRef} filename={`geneview-${data.gene.gene_id}`} />
      </div>

      <div className="geneview-canvas__stack" ref={containerRef} onWheel={handleWheel}>
        {/* NOTE: each layer below renders its own <svg> for now (independent
            toggle/refetch per design §1); ExportButton exports the first one
            it finds. A later wave should merge these into a single <svg> with
            <g> per layer so "export current view" captures the full stack. */}
        <Ruler scale={scale} />
        <GeneModelLayer scale={scale} gene={data.gene} />
        {layers.pasStems && <PASStemLayer scale={scale} pas={data.pas} onSelect={onSelectPas} />}
        {Array.from(layers.diffStrategies).map((s) => (
          <DiffOverlayLayer key={s} scale={scale} findings={data.diff} strategy={s} qMax={layers.qMax} significantOnly={layers.significantOnly} />
        ))}
        {Array.from(layers.lengthStrategies).map((s) => (
          <LengthOverlayLayer key={s} scale={scale} lengths={data.length} strategy={s} />
        ))}
        {layers.coverage && <CoverageLayer scale={scale} />}
      </div>
    </div>
  )
}
