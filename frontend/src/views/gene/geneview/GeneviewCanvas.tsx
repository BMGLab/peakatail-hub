import { useCallback, useEffect, useRef, useState } from 'react'
import type { FindingRow, GeneviewClusterTrack, GeneviewLayerData, GeneviewPas, GeneviewPasSelection, LengthRow } from '@lib/contract/types'
import { createCoordinateScale, panWindow, windowFromRange, type GenomicWindow } from './CoordinateScale'
import { Ruler } from './Ruler'
import { IsoformTrack } from './IsoformTrack'
import { PASBandsLayer } from './PASBandsLayer'
import { ClusterProportionTrack } from './ClusterProportionTrack'
import { Colorbar } from './Colorbar'
import { PASStemLayer } from './PASStemLayer'
import { DiffOverlayLayer } from './DiffOverlayLayer'
import { LengthOverlayLayer } from './LengthOverlayLayer'
import { GeneviewTooltip } from './GeneviewTooltip'
import type { GeneviewLayerState } from './LayerPanel'
import {
  CLUSTER_ROW_HEIGHT,
  COLORBAR_GAP,
  COLORBAR_WIDTH,
  LEFT_MARGIN,
  OVERLAY_ROW_HEIGHT,
  PAS_LABEL_HEIGHT,
  RULER_HEIGHT,
  TITLE_HEIGHT,
  TRACK_GAP,
  isoformTrackHeight,
} from './layout'
import { ExportButton } from '@export/ExportButton'
import './GeneviewCanvas.css'

// `window` (the component prop below) shadows the DOM global -- alias the
// real thing once at module scope so the drag-effect's document-level
// listeners stay unambiguous without renaming the prop everywhere else in
// this file (the prop name matches every sibling hook/component's own
// `window: GenomicWindow` convention, see useGeneviewWindow.ts).
const windowGlobal = globalThis.window

interface GeneviewCanvasProps {
  data: GeneviewLayerData
  window: GenomicWindow
  layers: GeneviewLayerState
  width?: number
  onZoomIn: (centerBp?: number) => void
  onZoomOut: (centerBp?: number) => void
  onPan: (deltaBp: number) => void
  onResetToGeneSpan: () => void
  onSetWindow: (w: GenomicWindow) => void
  onSelectPas?: ((pas: GeneviewPasSelection) => void) | undefined
}

function formatSpan(bp: number): string {
  if (bp >= 1_000_000) return `${(bp / 1_000_000).toFixed(2)} Mb`
  if (bp >= 1_000) return `${(bp / 1_000).toFixed(1)} kb`
  return `${bp.toLocaleString()} bp`
}

/** "Gene <SYMBOL> (<ENSG>) — chr:start-end (strand, span) — N PAS" -- the
 * exact title format of PeakATail's own gene-track figure (`gene_track_
 * matplotlib.py`'s `fig.suptitle`), so the hub's geneview reads as the same
 * artifact rendered interactively rather than a different tool. */
function buildTitle(data: GeneviewLayerData): string {
  const g = data.gene
  const label = g.gene_name && g.gene_name !== g.gene_id ? `${g.gene_name} (${g.gene_id})` : g.gene_id
  if (g.chrom === null || g.start === null || g.end === null || g.strand === null) {
    return `Gene ${label} — coordinates unavailable — ${data.pas.length} PAS`
  }
  const span = formatSpan(g.end - g.start)
  return `Gene ${label} — ${g.chrom}:${g.start.toLocaleString()}-${g.end.toLocaleString()} (${g.strand === '-' ? '−' : '+'} strand, ${span}) — ${data.pas.length} PAS`
}

/** Positionally zip a cluster track's `values` to `pas` by `pas_uid` (the
 * contract guarantees same order/length, but this is defensive against a
 * partial/stale window rather than assuming index-alignment blindly). */
function proportionsForPas(clusterTracks: GeneviewClusterTrack[], pasUid: string): Record<string, number | null> {
  const out: Record<string, number | null> = {}
  for (const t of clusterTracks) {
    const v = t.values.find((vv) => vv.pas_uid === pasUid)
    out[t.cluster] = v ? v.proportion : null
  }
  return out
}

function buildSelection(pas: GeneviewPas, data: GeneviewLayerData): GeneviewPasSelection {
  const diffForPas = data.diff.filter((f) => f.pas_uid === pas.pas_uid)
  const lengthForPas = data.length.filter((l) => l.pas_uid === pas.pas_uid || l.gene_id === data.gene.gene_id)
  // One entry per strategy actually present for this PAS's gene -- de-duped
  // (length rows are per-cell, many rows share a strategy/direction).
  const lengthByStrategy = new Map<string, (typeof lengthForPas)[number]>()
  for (const l of lengthForPas) if (!lengthByStrategy.has(l.strategy)) lengthByStrategy.set(l.strategy, l)

  return {
    ...pas,
    cluster_proportions: proportionsForPas(data.clusterTracks, pas.pas_uid),
    diff_summary: diffForPas.map((f) => ({
      strategy: f.strategy,
      qvalue: f.qvalue,
      delta_proportion: f.delta_proportion,
      direction: f.direction,
    })),
    length_summary: Array.from(lengthByStrategy.values()).map((l) => ({ strategy: l.strategy, direction: l.direction })),
  }
}

type DragMode = 'pan' | 'box' | null

interface TooltipState {
  x: number
  y: number
  pas: GeneviewPas
  cluster?: GeneviewClusterTrack | undefined
}

/**
 * Composes the geneview's independent toggleable layers into ONE svg
 * document sharing a genomic x-axis (design doc §1 "Interactive geneview
 * (centerpiece)") -- isoform track, PAS bands, per-cluster viridis
 * proportion tracks, and a viridis colorbar, laid out to match PeakATail's
 * own `gene_track_matplotlib.py` figure. A single composed `<svg>` (rather
 * than one per layer, the earlier scaffold's approach) so "export current
 * view" captures the whole stack, and so drag-to-pan / shift-drag-to-zoom
 * math only has one coordinate space to reason about.
 */
export function GeneviewCanvas({
  data,
  window,
  layers,
  width: widthProp,
  onZoomIn,
  onZoomOut,
  onPan,
  onResetToGeneSpan,
  onSetWindow,
  onSelectPas,
}: GeneviewCanvasProps) {
  // `containerRef` is both the ExportButton's target (it walks the subtree
  // for the first <svg>) AND the ResizeObserver target below -- both care
  // about the same `.geneview-canvas__stack` node, no need for two refs.
  const containerRef = useRef<HTMLDivElement>(null)
  const surfaceRef = useRef<SVGRectElement>(null)

  // Plot pixel-width tracks the actual panel width (via ResizeObserver on
  // the scrollable stack wrapper) rather than a fixed constant -- a fixed
  // 900px default silently produced a composed svg wider than the
  // three-column app shell's center panel, so the distal PAS of even this
  // tiny 2-PAS fixture gene scrolled out of view with no visible affordance
  // that anything was clipped. Falls back to `widthProp` (or 900) before
  // the first layout measurement / in environments without a real layout
  // engine (jsdom tests, see GeneView.wireshape.test.tsx).
  const [measuredWidth, setMeasuredWidth] = useState<number | null>(null)
  useEffect(() => {
    const el = containerRef.current
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    const ro = new ResizeObserver((entries) => {
      const cw = entries[0]?.contentRect.width
      if (cw && cw > 0) {
        const plot = cw - 16 /* stack padding */ - LEFT_MARGIN - COLORBAR_GAP - COLORBAR_WIDTH
        setMeasuredWidth(Math.max(360, Math.round(plot)))
      }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const width = measuredWidth ?? widthProp ?? 900

  const scale = createCoordinateScale(window, width)

  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
  const [drag, setDrag] = useState<{ mode: DragMode; startClientX: number; startWindow: GenomicWindow; currentClientX: number } | null>(
    null,
  )

  // --- layout: compute row list up front so bands/colorbar know the exact
  // vertical span of the track stack (design brief: bands span ALL panels).
  const isoH = isoformTrackHeight(data.isoforms.length)
  const trackTop = TITLE_HEIGHT + RULER_HEIGHT + PAS_LABEL_HEIGHT
  let cursor = trackTop + isoH + TRACK_GAP
  const clusterRows = data.clusterTracks.map((track) => {
    const y = cursor
    cursor += CLUSTER_ROW_HEIGHT + TRACK_GAP
    return { track, y }
  })
  const overlayRows: { kind: 'diff' | 'length' | 'stems' | 'coverage'; key: string; y: number }[] = []
  if (layers.pasStems) {
    overlayRows.push({ kind: 'stems', key: 'stems', y: cursor })
    cursor += OVERLAY_ROW_HEIGHT * 2 + TRACK_GAP
  }
  for (const s of layers.diffStrategies) {
    overlayRows.push({ kind: 'diff', key: `diff-${s}`, y: cursor })
    cursor += OVERLAY_ROW_HEIGHT + TRACK_GAP
  }
  for (const s of layers.lengthStrategies) {
    overlayRows.push({ kind: 'length', key: `length-${s}`, y: cursor })
    cursor += OVERLAY_ROW_HEIGHT + TRACK_GAP
  }
  if (layers.coverage) {
    overlayRows.push({ kind: 'coverage', key: 'coverage', y: cursor })
    cursor += OVERLAY_ROW_HEIGHT + TRACK_GAP
  }
  const trackBottom = cursor - TRACK_GAP
  const svgHeight = trackBottom + 8
  const svgWidth = LEFT_MARGIN + width + COLORBAR_GAP + COLORBAR_WIDTH

  // Shared y-axis cap across every cluster track (matplotlib reference's
  // `y_cap`), so bar heights are comparable row to row.
  const allProps = data.clusterTracks.flatMap((t) => t.values.map((v) => v.proportion).filter((p): p is number => p !== null))
  const yMax = Math.max(0.05, ...(allProps.length ? [Math.max(...allProps) * 1.15] : [0.5]))

  // --- interaction: wheel-zoom at cursor ---
  function handleWheel(e: React.WheelEvent) {
    e.preventDefault()
    const rect = surfaceRef.current?.getBoundingClientRect()
    const localX = rect ? e.clientX - rect.left : width / 2
    const centerBp = scale.toGenomic(localX)
    if (e.deltaY < 0) onZoomIn(centerBp)
    else onZoomOut(centerBp)
  }

  // --- interaction: drag-to-pan (plain drag) / drag-to-zoom (shift+drag) ---
  // Starts ONLY from the background "drag surface" rect (bottom-most in
  // paint order) -- a mousedown that lands directly on a PAS bar/band fires
  // that element's own onClick instead, since it's the actual event target.
  function handleSurfaceMouseDown(e: React.MouseEvent) {
    if (e.button !== 0) return
    setDrag({ mode: e.shiftKey ? 'box' : 'pan', startClientX: e.clientX, startWindow: window, currentClientX: e.clientX })
  }

  useEffect(() => {
    if (!drag) return undefined
    function onMove(e: MouseEvent) {
      setDrag((d) => (d ? { ...d, currentClientX: e.clientX } : d))
      if (drag!.mode === 'pan') {
        const deltaPx = e.clientX - drag!.startClientX
        const deltaBp = deltaPx * scale.bpPerPixel
        onSetWindow(panWindow(drag!.startWindow, -deltaBp))
      }
    }
    function onUp(e: MouseEvent) {
      if (drag!.mode === 'box') {
        const rect = surfaceRef.current?.getBoundingClientRect()
        const x0 = rect ? drag!.startClientX - rect.left : 0
        const x1 = rect ? e.clientX - rect.left : 0
        if (Math.abs(x1 - x0) > 4) {
          const bpA = scale.toGenomic(x0)
          const bpB = scale.toGenomic(x1)
          onSetWindow(windowFromRange(drag!.startWindow, bpA, bpB))
        }
      }
      setDrag(null)
    }
    windowGlobal.addEventListener('mousemove', onMove)
    windowGlobal.addEventListener('mouseup', onUp)
    return () => {
      windowGlobal.removeEventListener('mousemove', onMove)
      windowGlobal.removeEventListener('mouseup', onUp)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drag])

  const handleHoverPas = useCallback((pas: GeneviewPas | null, clientX: number, clientY: number, cluster?: GeneviewClusterTrack) => {
    setTooltip(pas ? { x: clientX, y: clientY, pas, cluster } : null)
  }, [])

  const handleSelectPas = useCallback(
    (pas: GeneviewPas) => {
      onSelectPas?.(buildSelection(pas, data))
    },
    [data, onSelectPas],
  )

  const gradientId = `geneview-viridis-${data.gene.gene_id}`

  // Box-zoom preview rect (screen px, local to the drag surface).
  let boxPreview: { x: number; w: number } | null = null
  if (drag?.mode === 'box') {
    const rect = surfaceRef.current?.getBoundingClientRect()
    const x0 = rect ? drag.startClientX - rect.left : 0
    const x1 = rect ? drag.currentClientX - rect.left : 0
    boxPreview = { x: Math.min(x0, x1), w: Math.abs(x1 - x0) }
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
        <span className="geneview-canvas__locus mono">
          {window.chrom}:{Math.round(window.start).toLocaleString()}-{Math.round(window.end).toLocaleString()}
          {' · '}
          {formatSpan(window.end - window.start)}
        </span>
        <span className="geneview-canvas__hint">drag to pan · shift-drag to zoom to region · scroll to zoom</span>
        <ExportButton targetRef={containerRef} filename={`geneview-${data.gene.gene_id}`} />
      </div>

      <div className="geneview-canvas__stack" ref={containerRef}>
        <svg
          width={svgWidth}
          height={svgHeight}
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="geneview-svg"
          onWheel={handleWheel}
        >
          <rect x={0} y={0} width={svgWidth} height={svgHeight} className="geneview-svg__bg" />
          <text x={LEFT_MARGIN} y={20} className="geneview-svg__title">
            {buildTitle(data)}
          </text>

          {/* drag surface: bottom-most, spans the whole track region so a
              click/drag on empty space pans/box-zooms; PAS bars/bands paint
              on top and intercept clicks aimed directly at them. */}
          <g transform={`translate(${LEFT_MARGIN}, ${TITLE_HEIGHT})`}>
            <rect
              ref={surfaceRef}
              x={0}
              y={0}
              width={width}
              height={svgHeight - TITLE_HEIGHT}
              className="geneview-svg__drag-surface"
              onMouseDown={handleSurfaceMouseDown}
            />
          </g>

          <g transform={`translate(${LEFT_MARGIN}, ${TITLE_HEIGHT})`}>
            <Ruler scale={scale} height={RULER_HEIGHT} />
          </g>

          {/* PAS bands span from the top of the isoform track through the
              bottom of the last rendered row (design brief: "spanning ALL
              panels"). */}
          <g transform={`translate(${LEFT_MARGIN}, 0)`}>
            <PASBandsLayer
              scale={scale}
              pas={data.pas}
              top={trackTop}
              bottom={trackBottom}
              onHover={(p, cx, cy) => handleHoverPas(p, cx, cy)}
              onSelect={handleSelectPas}
            />
          </g>

          <g transform={`translate(${LEFT_MARGIN}, ${trackTop})`}>
            <IsoformTrack scale={scale} isoforms={data.isoforms} strand={data.gene.strand} height={isoH} />
          </g>
          <text x={8} y={trackTop + isoH / 2} className="geneview-svg__row-label" dominantBaseline="middle">
            Isoforms
          </text>

          {clusterRows.map(({ track, y }) => (
            <g key={track.cluster}>
              <g transform={`translate(${LEFT_MARGIN}, ${y})`}>
                <ClusterProportionTrack
                  scale={scale}
                  track={track}
                  pas={data.pas}
                  height={CLUSTER_ROW_HEIGHT}
                  yMax={yMax}
                  onHover={(p, t, cx, cy) => handleHoverPas(p, cx, cy, t)}
                  onLeave={() => setTooltip(null)}
                  onSelect={handleSelectPas}
                />
              </g>
              <text x={8} y={y + CLUSTER_ROW_HEIGHT / 2 - 4} className="geneview-svg__row-label" dominantBaseline="middle">
                cluster {track.cluster}
              </text>
              <text x={8} y={y + CLUSTER_ROW_HEIGHT / 2 + 9} className="geneview-svg__row-label geneview-svg__row-label--dim" dominantBaseline="middle">
                (n={track.n_cells})
              </text>
            </g>
          ))}

          {overlayRows.map((row) => {
            if (row.kind === 'stems') {
              return (
                <g key={row.key} transform={`translate(${LEFT_MARGIN}, ${row.y})`}>
                  <PASStemLayer scale={scale} pas={data.pas} height={OVERLAY_ROW_HEIGHT * 2} onSelect={handleSelectPas} />
                </g>
              )
            }
            if (row.kind === 'diff') {
              const strategy = row.key.replace('diff-', '') as FindingRow['strategy']
              return (
                <g key={row.key} transform={`translate(${LEFT_MARGIN}, ${row.y})`}>
                  <DiffOverlayLayer
                    scale={scale}
                    findings={data.diff}
                    strategy={strategy}
                    qMax={layers.qMax}
                    significantOnly={layers.significantOnly}
                    rowHeight={OVERLAY_ROW_HEIGHT}
                  />
                </g>
              )
            }
            if (row.kind === 'length') {
              const strategy = row.key.replace('length-', '') as LengthRow['strategy']
              return (
                <g key={row.key} transform={`translate(${LEFT_MARGIN}, ${row.y})`}>
                  <LengthOverlayLayer scale={scale} lengths={data.length} strategy={strategy} rowHeight={OVERLAY_ROW_HEIGHT} />
                </g>
              )
            }
            return (
              <g key={row.key} transform={`translate(${LEFT_MARGIN}, ${row.y})`}>
                <text x={4} y={OVERLAY_ROW_HEIGHT / 2 + 4} fontSize={9} className="geneview-svg__row-label">
                  coverage lane (true bigWig coverage) -- roadmap B, not yet available
                </text>
              </g>
            )
          })}

          <Colorbar x={LEFT_MARGIN + width + COLORBAR_GAP} top={trackTop} height={trackBottom - trackTop} gradientId={gradientId} />

          {boxPreview && (
            <rect
              x={LEFT_MARGIN + boxPreview.x}
              y={TITLE_HEIGHT}
              width={boxPreview.w}
              height={svgHeight - TITLE_HEIGHT}
              className="geneview-svg__box-preview"
            />
          )}
        </svg>
      </div>

      {tooltip && (
        <GeneviewTooltip x={tooltip.x} y={tooltip.y}>
          <div className="geneview-tooltip__title mono">{tooltip.pas.pas_uid}</div>
          <div>
            {tooltip.pas.chrom}:{tooltip.pas.start.toLocaleString()}-{tooltip.pas.end.toLocaleString()} ({tooltip.pas.strand})
          </div>
          <div>tier: {tooltip.pas.tier ?? '—'}</div>
          {tooltip.cluster && (
            <div>
              cluster {tooltip.cluster.cluster} (n={tooltip.cluster.n_cells}):{' '}
              {(() => {
                const v = tooltip.cluster.values.find((vv) => vv.pas_uid === tooltip.pas.pas_uid)
                return v?.proportion !== null && v?.proportion !== undefined ? `${(v.proportion * 100).toFixed(1)}%` : 'no reads'
              })()}
            </div>
          )}
          <div className="geneview-tooltip__hint">click for full detail</div>
        </GeneviewTooltip>
      )}
    </div>
  )
}
