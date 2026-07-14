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
 * the placeholder window. */
function spanOf(gene: GeneSummary | null | undefined): GenomicWindow {
  if (gene && gene.chrom !== null && gene.start !== null && gene.end !== null) {
    return { chrom: gene.chrom, start: gene.start, end: gene.end }
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

  const zoomIn = useCallback(
    (centerBp?: number) => setWindowState((w) => zoomWindow(w, 0.7, centerBp ?? (w.start + w.end) / 2)),
    [],
  )
  const zoomOut = useCallback(
    (centerBp?: number) => setWindowState((w) => zoomWindow(w, 1.4, centerBp ?? (w.start + w.end) / 2)),
    [],
  )
  const pan = useCallback((deltaBp: number) => setWindowState((w) => panWindow(w, deltaBp)), [])

  return { window, zoomIn, zoomOut, pan, resetToGeneSpan, setWindow: setWindowState }
}
