import { useCallback, useEffect, useRef, useState } from 'react'
import type { GeneSummary } from '@lib/contract/types'
import { panWindow, zoomWindow, type GenomicWindow } from './CoordinateScale'

export interface UseGeneviewWindowResult {
  window: GenomicWindow
  zoomIn: (centerBp?: number) => void
  zoomOut: (centerBp?: number) => void
  pan: (deltaBp: number) => void
  resetToGeneSpan: () => void
  setWindow: (w: GenomicWindow) => void
}

/**
 * Owns the current visible [chrom,start,end] window for the geneview
 * renderer. Real windowed range-fetching (only features in view at the
 * current LOD, per design §1) plugs in downstream via
 * `useGeneviewData(geneId, { start: window.start, end: window.end })` --
 * this hook only owns the window math/state, not the fetch.
 */
const PLACEHOLDER_WINDOW: GenomicWindow = { chrom: '', start: 0, end: 1 }

/** `gene.chrom`/`start`/`end` are nullable (backend schemas.py GeneSummary's
 * `span` is null when the gene has zero surviving PAS) -- `GenomicWindow`
 * itself stays non-nullable so CoordinateScale/every layer doesn't have to
 * null-check; this is the one place that resolves "no real span yet" to
 * the placeholder window.
 *
 * Pads 5% of the span on each side (min 1bp) -- mirrors PeakATail's own
 * `gene_track_matplotlib.py` (`pad = int(gene_span * 0.05) + 1`). Without
 * this, a PAS sitting exactly at `gene.start`/`gene.end` (common: the
 * gene's own span IS derived from its outermost surviving PAS, see
 * `queries.gene_pas_span`) renders flush against the plot's left/right
 * edge -- its band label gets clipped and its bar's percent label collides
 * with the y-axis tick label at x=0, an unreadable overlap on the
 * fixture's tightest-zoom default view. */
function spanOf(gene: GeneSummary | null | undefined): GenomicWindow {
  if (gene && gene.chrom !== null && gene.start !== null && gene.end !== null) {
    const span = Math.max(gene.end - gene.start, 1)
    const pad = Math.round(span * 0.05) + 1
    return { chrom: gene.chrom, start: Math.max(0, gene.start - pad), end: gene.end + pad }
  }
  return PLACEHOLDER_WINDOW
}

export function useGeneviewWindow(gene: GeneSummary | null | undefined): UseGeneviewWindowResult {
  const geneSpan: GenomicWindow = spanOf(gene)

  const [window, setWindowState] = useState<GenomicWindow>(geneSpan)
  const hasInitialized = useRef(false)

  // Sync the window to the gene's span the first time gene data arrives
  // (it loads asynchronously via useGene/useGeneviewData).
  useEffect(() => {
    if (gene && !hasInitialized.current) {
      hasInitialized.current = true
      setWindowState(geneSpan)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gene])

  const resetToGeneSpan = useCallback(() => {
    setWindowState(spanOf(gene))
  }, [gene])

  // Gentler per-step factors (0.8 in / 1.25 out, exact reciprocals) so a
  // scroll notch or button press nudges the view rather than jumping a third
  // of the span at a time -- the previous 0.7/1.4 felt jerky and made it easy
  // to overshoot past the feature you were zooming toward.
  const zoomIn = useCallback(
    (centerBp?: number) => setWindowState((w) => zoomWindow(w, 0.8, centerBp ?? (w.start + w.end) / 2)),
    [],
  )
  const zoomOut = useCallback(
    (centerBp?: number) => setWindowState((w) => zoomWindow(w, 1.25, centerBp ?? (w.start + w.end) / 2)),
    [],
  )
  const pan = useCallback((deltaBp: number) => setWindowState((w) => panWindow(w, deltaBp)), [])

  return { window, zoomIn, zoomOut, pan, resetToGeneSpan, setWindow: setWindowState }
}
