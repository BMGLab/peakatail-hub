// Plain linear-scale math for the genomic-coordinate <-> pixel mapping used by
// every geneview layer. DECISION: we deliberately did NOT take a `d3` (or
// `d3-scale`) dependency for this -- the only operation the renderer needs is
// a clamped linear scale plus its inverse, which is ~15 lines and easier to
// unit-test/tree-shake without pulling in d3's module graph. If later layers
// need d3's zoom-behavior/brush interaction helpers specifically, add
// `d3-zoom`/`d3-selection` as a targeted addition rather than the `d3` umbrella
// package -- documented here so the choice is visible to future contributors.

export interface GenomicWindow {
  chrom: string
  start: number
  end: number
}

export interface CoordinateScale {
  window: GenomicWindow
  pixelWidth: number
  /** Genomic position (bp, 0-based) -> pixel x within [0, pixelWidth]. */
  toPixel(genomicPos: number): number
  /** Pixel x -> genomic position (bp). Inverse of toPixel. */
  toGenomic(pixelX: number): number
  /** Convenience: bp span rendered per pixel (for LOD decisions upstream). */
  bpPerPixel: number
}

export function createCoordinateScale(window: GenomicWindow, pixelWidth: number): CoordinateScale {
  const span = Math.max(1, window.end - window.start)
  const bpPerPixel = span / Math.max(1, pixelWidth)

  return {
    window,
    pixelWidth,
    bpPerPixel,
    toPixel(genomicPos: number): number {
      const frac = (genomicPos - window.start) / span
      return frac * pixelWidth
    },
    toGenomic(pixelX: number): number {
      const frac = pixelX / Math.max(1, pixelWidth)
      return window.start + frac * span
    },
  }
}

/** Zoom the window by `factor` (>1 zooms out, <1 zooms in) around `centerBp`. */
export function zoomWindow(window: GenomicWindow, factor: number, centerBp: number): GenomicWindow {
  const span = window.end - window.start
  const newSpan = Math.max(20, span * factor)
  const centerFrac = (centerBp - window.start) / Math.max(1, span)
  const start = Math.max(0, Math.round(centerBp - centerFrac * newSpan))
  return { ...window, start, end: start + Math.round(newSpan) }
}

/** Pan the window by `deltaBp` (positive = rightward/downstream). */
export function panWindow(window: GenomicWindow, deltaBp: number): GenomicWindow {
  const start = Math.max(0, window.start + deltaBp)
  const span = window.end - window.start
  return { ...window, start, end: start + span }
}

/** Box-zoom: set the window to exactly the genomic range between two
 * positions (order-independent, min 20bp span so a near-zero-width drag
 * doesn't produce a degenerate/unusable window). Used by the drag-to-zoom
 * interaction (design brief "Zoom (scroll/box)"). */
export function windowFromRange(window: GenomicWindow, bpA: number, bpB: number): GenomicWindow {
  const lo = Math.max(0, Math.min(bpA, bpB))
  const hi = Math.max(bpA, bpB)
  const span = Math.max(20, hi - lo)
  return { ...window, start: Math.round(lo), end: Math.round(lo + span) }
}

/** Parse the interim `pas_uid` grammar (`chrom:pos:strand`) used by mock data
 * and the E1-minted IDs described in the design spec. Returns null if the
 * string doesn't match (defensive -- never crash the renderer on bad IDs). */
export function parsePasUid(pasUid: string): { chrom: string; pos: number; strand: '+' | '-' } | null {
  const parts = pasUid.split(':')
  if (parts.length !== 3) return null
  const [chrom, posStr, strand] = parts
  const pos = Number(posStr)
  if (!chrom || Number.isNaN(pos) || (strand !== '+' && strand !== '-')) return null
  return { chrom, pos, strand }
}
