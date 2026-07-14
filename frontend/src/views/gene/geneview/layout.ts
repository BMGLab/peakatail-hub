// Shared pixel-layout constants for the composed geneview SVG (see
// GeneviewCanvas.tsx). Kept in one place because the interactive wrapper
// (mouse -> genomic-position math for zoom/pan/box-select) and every track's
// renderer both need to agree on where the "plot area" (the genomic-scaled
// region) starts and ends within the overall SVG.
//
// Mirrors the `--track-*` design tokens in src/app/theme/tokens.css (the
// design-system's authoritative layout metrics for this exact view, tuned to
// match the packaged CLIC2/DPYD figures) -- kept as plain numeric constants
// here rather than read from CSS custom properties at render time because
// every value below feeds numeric SVG attribute math (x/y/width/height),
// which cannot consume `var(...)` directly. If tokens.css's `--track-*`
// values change, update the matching constant here in the same change.
//
// Layout, left to right:  [ LEFT_MARGIN (row labels, = --track-label-col) | plot area (`plotWidth`, genomic-scaled) | gap | COLORBAR_WIDTH ]
// Layout, top to bottom:  [ TITLE_HEIGHT | RULER_HEIGHT (= --track-ruler-h) | isoform track | PAS band labels sit just above the isoform track | cluster tracks (= --track-prop-row each)... | optional overlay rows... ]

export const LEFT_MARGIN = 136 // --track-label-col
export const COLORBAR_GAP = 18
export const COLORBAR_WIDTH = 70 // includes --track-colorbar-w (14px bar) + tick/label text
export const TITLE_HEIGHT = 30
export const RULER_HEIGHT = 26 // --track-ruler-h
/** Headroom above the isoform track reserved for PAS id labels (the small
 * red text sitting just above the exon boxes in the reference figure). */
export const PAS_LABEL_HEIGHT = 16
export const ISOFORM_ROW_HEIGHT = 22 // --track-model-row
export const MIN_ISOFORM_TRACK_HEIGHT = 40
export const CLUSTER_ROW_HEIGHT = 52 // --track-prop-row
export const OVERLAY_ROW_HEIGHT = 24
export const TRACK_GAP = 2 // --track-gap
/** Minimum visible pixel width for a PAS band/bar, so a narrow (or
 * singleton, ~1bp) PAS doesn't vanish at whole-gene zoom -- mirrors
 * `--pas-band-w` and the matplotlib reference's `min_visible_w` clamp
 * (ema/viz/gene_track_matplotlib.py). */
export const MIN_PAS_WIDTH_PX = 8

export function isoformTrackHeight(nIsoforms: number): number {
  return Math.max(MIN_ISOFORM_TRACK_HEIGHT, nIsoforms * ISOFORM_ROW_HEIGHT + 10)
}
