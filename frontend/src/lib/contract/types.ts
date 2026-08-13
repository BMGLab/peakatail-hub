// TODO: replace with codegen from packages/contract JSON Schema once available.
//
// These are HAND-WRITTEN interim types mirroring the field names the Python
// `peakatail-contract` package is using (see docs/2026-07-12-peakatail-hub-
// frontend-design.md §4 + the entity block in the frontend scaffold task).
// Field names are kept IDENTICAL to the spec so the eventual codegen swap is
// a type-only diff, not a data-shape migration. Do NOT rename fields here
// without coordinating with the contract package agent.

/** A row from the PAS ledger: every PAS's provenance through the pipeline. */
export interface PasLedgerRow {
  orig_pas_key: string
  chrom: string
  start: number
  end: number
  strand: '+' | '-'
  unified_pas_id: string
  pas_uid: string
  snap_distance_bp: number | null
  gene_id: string | null
  /** Human-readable symbol (e.g. "SAMD11"), 2026-08-14 -- from annotatedpas.bed's own gene_symbol column. */
  gene_symbol: string | null
  gene_distance_bp: number | null
  tier: string | null
  last_stage: string
  dropped_at: string
  drop_reason: string | null
}

/** A row from the cell ledger: every cell's provenance through the pipeline. */
export interface CellLedgerRow {
  barcode: string
  cell_uid: string
  dataset_id: string
  total_reads: number
  /**
   * PAS-per-cell count. NOT gene count.
   * @see docs §7e — obs['n_genes'] is PAS-per-cell, never label this "genes".
   */
  n_pas: number
  dropped_at: string
  drop_reason: string | null
  cluster: string | null
}

/** A row in the long-format switch/diff findings table (one per PAS x strategy x arm). */
export interface FindingRow {
  finding_uid: string
  pas_uid: string
  gene_id: string
  /** Human-readable symbol (e.g. "SAMD11"), 2026-08-14 -- hub-side enrichment
   * joined from pas_ledger at query time (backend schemas.py FindingRowView),
   * not part of the raw findings_long grain. null when unavailable. */
  gene_symbol: string | null
  canonical_cluster: string
  celltype: string | null
  strategy: 'fisher' | 'nb_pairwise' | 'nb_multi'
  arm: string
  direction: 'shorten' | 'lengthen' | 'flat' | 'undetermined'
  utr_class: string | null
  qvalue: number
  pvalue: number
  delta_proportion: number
  log2fc: number
  n_cells: number
  n_reads: number
}

/** A row in the long-format length table (one per PAS/transcript x strategy x cell). */
export interface LengthRow {
  pas_uid: string | null
  gene_id: string
  transcript_id: string | null
  strategy: 'classic' | 'proportion' | 'shannon'
  cell_uid: string
  canonical_cluster: string
  value: number
  /**
   * Engine correction (2026-07-14, ema/switch_test/long_output.py): now
   * populated for ALL THREE strategies (a deterministic one-vs-rest
   * structural call), not just `proportion` as originally documented --
   * `shannon` has no polarity axis so it's always `'undetermined'`, never
   * `null`. Still nullable in the type for tolerance with older engine
   * outputs that predate this field. See `PasLedgerRow`-adjacent `Direction`
   * usage elsewhere for the same 4-value enum (never a bare boolean).
   */
  direction: 'shorten' | 'lengthen' | 'flat' | 'undetermined' | null
  /**
   * Informational provenance for `direction`'s methodology (e.g.
   * `'structural'` -- the one-vs-rest geometric call above -- vs. a future
   * `'differential'` pairwise mode). Per spec §7e's caveat-flag philosophy,
   * surface this wherever direction is shown rather than letting different
   * methodologies look interchangeable. Optional/additive; not yet
   * surfaced in any view -- tracked as a follow-up, not silently dropped.
   */
  direction_basis: string | null
  rank: number | null
}

// ---------------------------------------------------------------------------
// Supporting entities referenced by the app shell / views / API client below.
// These are NOT in the spec's literal entity block but are required to type
// the endpoints in docs §3 and the DetailPanel's polymorphic selection. Kept
// separate and clearly interim so contract/backend agents can reconcile field
// names against their own manifest/Run models later.
// ---------------------------------------------------------------------------

/**
 * Field names/types here MUST match `backend/src/peakatail_hub/schemas.py`'s
 * `RunSummary` pydantic model exactly (GET /runs). This is NOT the run's
 * `dataset_id`/`label` (a run may span >1 dataset -- see `n_datasets` /
 * `stratum_to_label`) -- there is no single flat label; callers needing a
 * display string derive one (see TopBar.tsx) rather than assuming a field
 * that was never real (a prior interim version of this type had
 * `dataset_id`/`label`/`created_at`/`n_samples` fields that do not exist on
 * the backend response -- they were always `undefined` at runtime, which
 * broke the Scope selector: `/datasets/undefined/umap` 404s).
 */
export interface RunSummary {
  run_id: string
  root: string
  contract_version: string
  resolved_config: Record<string, unknown>
  stratum_to_label: Record<string, string>
  n_pas: number | null
  n_cells: number | null
  n_genes: number | null
  n_datasets: number | null
  n_findings: number | null
  n_length_rows: number | null
  indexed_at: string | null
  /**
   * Which registered SOURCES directory (dashboard multi-directory manager,
   * GET/POST /sources) this run was last (re)discovered under. All three
   * are `null` for a run indexed before the sources feature existed, or via
   * the bare `hub index <dir>` CLI outside any registered source -- a
   * legitimate "unattributed" state, not missing data.
   */
  source_id: string | null
  source_path: string | null
  source_label: string | null
  /** Distinct non-null celltype values across this run's findings -- shown on the dashboard's run card. */
  n_celltypes: number | null
  /** Whether this run has any atlas-snap provenance at all (index/indexer.py
   * `_atlas_snap_available`) -- `false` on `reannotate` runs (no snap step
   * of their own, a real "not applicable"), `null` only for a run indexed
   * before this flag existed. */
  atlas_snap_available: boolean | null
}

// ---------------------------------------------------------------------------
// B3_switch results (2026-08-14) -- "cell types -> stages -> genes" is the
// PRIMARY navigation the professor's headline finding (3'UTR shortening
// across disease stages, per cell type) needs, ahead of flat gene browsing.
// Mirrors backend schemas.py SwitchResults/SwitchCelltypeResult/SwitchTrend
// exactly (GET /runs/{run_id}/switch, GET /runs/{run_id}/switch/{celltype}/trend-genes).
// ---------------------------------------------------------------------------

export interface SwitchTrend {
  n_stages: number | null
  slope: number | null
  spearman: number | null
  direction: string | null
  value_col: string | null
  mean_by_stage: Record<string, number>
}

export interface SwitchLengthAvailability {
  file_size_bytes: number | null
}

/** One cell type's B3_switch results within a run: `diff` = finding counts
 * per strategy (already fully queryable via `/findings?celltype=...`),
 * `length` = availability only (the classic/proportion/shannon files are
 * per-cell x per-gene and can be 100GB+ for one run -- never fully
 * ingested, see the backend's switch_availability table), `trend` = the
 * fully-ingested length-across-stages headline. */
/** nb_multi omnibus counts for one celltype -- a DIFFERENT result grain than
 * `diff.fisher` (an omnibus LRT across all stages, no canonical_cluster/
 * direction), 2026-08-14. `n` = total PAS tested, `n_significant` = qvalue < 0.05. */
export interface SwitchNbMultiSummary {
  n: number
  n_significant: number
}

export interface SwitchCelltypeResult {
  celltype: string
  diff: Record<string, number>
  nb_multi: SwitchNbMultiSummary | null
  length: Record<string, SwitchLengthAvailability>
  trend: SwitchTrend | null
}

/** One row of `GET /runs/{id}/switch/{celltype}/nb-multi` -- the per-PAS
 * drill-down behind `SwitchCelltypeResult.nb_multi`'s counts. */
export interface SwitchNbMultiRow {
  pas_id: string
  gene_id: string | null
  pvalue: number | null
  qvalue: number | null
  test_stat: number | null
  df: number | null
  dispersion: number | null
  n_cells: number | null
}

export interface ClusterMatchAvailability {
  file_path: string | null
  file_size_bytes: number | null
}

export interface SwitchResults {
  run_id: string
  celltypes: SwitchCelltypeResult[]
  cluster_match: ClusterMatchAvailability | null
}

export interface SwitchTrendGeneRow {
  gene_id: string
  n_stages: number | null
  slope: number | null
  spearman: number | null
  direction: string | null
}

/** Matches backend schemas.py `SourceSummary` (GET/POST /sources). One
 * registered runs-root directory the dashboard's SOURCES panel manages. */
export interface Source {
  source_id: string
  path: string
  label: string | null
  added_at: string
  last_scanned_at: string | null
  /** 'ok' = scanned, no failures. 'empty' = scanned, zero run_manifest.json found.
   * 'error' = at least one run under this path failed indexing (see last_scan_error).
   * null = registered but not yet scanned (should not normally happen -- add scans inline). */
  last_scan_status: 'ok' | 'empty' | 'error' | null
  last_scan_error: string | null
  run_count: number
}

/** Matches backend schemas.py `SourceScanReport` -- the indexer outcome of one add/rescan pass. */
export interface SourceScanReport {
  indexed: string[]
  skipped_unchanged: string[]
  failed: Record<string, string>
}

/** Matches backend schemas.py `SourceScanResponse` -- POST /sources and POST /sources/{id}/rescan's response shape. */
export interface SourceScanResult {
  source: Source
  scan: SourceScanReport
}

/** Matches backend schemas.py `QcStageStat` (`/runs/{id}/qc`'s per-stage drop counts). */
export interface QcStageStat {
  stage: string
  dropped: number
}

/**
 * Matches backend schemas.py `QcFunnel` exactly -- NOT the earlier interim
 * shape (`stages: StageCount[]` + `config_diff`), which never existed on
 * the real response. Config-diff is a roadmap item (spec §7d: gated on B0 +
 * E2), there is no `config_diff` field yet.
 */
export interface RunQc {
  run_id: string
  n_pas_total: number
  n_pas_survived: number
  n_cells_total: number
  n_cells_survived: number
  pas_drop_by_stage: QcStageStat[]
  cell_drop_by_stage: QcStageStat[]
  per_sample_stats_available: boolean
  gate_note: string
}

// ---------------------------------------------------------------------------
// Browse: GET /genes, /pas, /cells -- searchable, paginated entity lists
// backing the gene/PAS/cell browsers. Same page-envelope shape as
// `/findings` (`items`/`next_cursor`/`total`, backend schemas.py
// `GenesPage`/`PasPage`/`CellsPage`).
// ---------------------------------------------------------------------------

/** One row of `GET /genes` (backend schemas.py `GeneListRow`) -- a lighter
 * aggregate than `GeneSummary` (no `run_id`/`n_length_rows`), one row per
 * gene with at least one surviving PAS. */
export interface GeneListRow {
  gene_id: string
  /** Human-readable symbol (e.g. "SAMD11"), 2026-08-14. */
  gene_symbol: string | null
  chrom: string | null
  start: number | null
  end: number | null
  strand: '+' | '-' | null
  n_pas: number
  n_findings: number
}

export interface GenesPage {
  items: GeneListRow[]
  next_cursor: string | null
  total: number
}

/** Full ledger rows, survived + dropped alike -- a provenance browser, not
 * a render feed (unlike `GeneviewPas`, which is windowed/survived-only). */
export interface PasPage {
  items: PasLedgerRow[]
  next_cursor: string | null
  total: number
}

export interface CellsPage {
  items: CellLedgerRow[]
  next_cursor: string | null
  total: number
}

/**
 * Backend schemas.py `GeneSummary` nests coordinates under `span:
 * GeneSpan | null` (null when the gene has zero surviving PAS -- e.g. every
 * assigned PAS was dropped). `chrom`/`start`/`end`/`strand` here are
 * therefore nullable -- client.ts flattens `span` onto this shape; consumers
 * MUST null-check before rendering coordinates (GeneView does, via
 * `MissingArtifactNotice`) rather than assume a span always exists.
 * `gene_name` is now backend-sourced (GTF `gene_name` attribute via
 * `peakatail_hub.gtf`, see genes.py) -- `client.ts` falls back to `gene_id`
 * only when the backend's `gene_name` comes back empty (no GTF configured
 * for the run / gene not found in it), never unconditionally overwrites it.
 */
export interface GeneSummary {
  gene_id: string
  gene_name: string
  chrom: string | null
  start: number | null
  end: number | null
  strand: '+' | '-' | null
  n_pas: number
}

/**
 * One row of `/genes/{id}/geneview-data`'s `pas` array (backend schemas.py
 * `GeneviewPas`) -- windowed coordinates/tier/distances ONLY. Deliberately
 * NOT full `PasDetail`: per spec §7a `/genes/{id}/counts` (the only path
 * that opens clusters.h5ad) is a separate, heavier endpoint, so
 * geneview-data was never meant to carry per-cluster counts. `PASStemLayer`
 * needs a per-PAS count to size stems; `per_cluster_counts` here defaults
 * to `{}` (flat stems) until a follow-up wires the two endpoints together --
 * tracked as a known gap, not silently faked as real counts.
 */
export interface GeneviewPas {
  pas_uid: string
  chrom: string
  start: number
  end: number
  strand: '+' | '-'
  unified_pas_id: string
  gene_distance_bp: number | null
  snap_distance_bp: number | null
  tier: string | null
  per_cluster_counts: Record<string, number>
}

/**
 * `/pas/{id}` returns a plain `PasLedgerRow`; `/pas/{id}/provenance` wraps
 * it in `{pas, findings, length_rows, trail}` (schemas.py `PasProvenance`).
 * This flattened `PasDetail` is what `client.ts` normalizes BOTH into (see
 * `getPas`/`getPasProvenance`) for the DetailPanel/AuditView -- not a shape
 * either endpoint returns directly on the wire.
 */
export interface PasDetail extends PasLedgerRow {
  gene_name: string | null
  per_cluster_counts: Record<string, number>
  /**
   * Reads backing per_cluster_counts are NOT UMI-deduplicated.
   * @see docs §7e — flag wherever counts are shown.
   */
  umi_deduplicated: false
}

export interface CellDetail extends CellLedgerRow {
  celltype: string | null
}

/**
 * One transcript's exon structure for the isoform track (backend schemas.py
 * `GeneviewIsoform`, sourced from a GTF via `peakatail_hub.gtf`). `exons` are
 * `[start, end)` BED-style pairs in ascending genomic order (independent of
 * strand — strand only controls the arrow direction drawn on the intron
 * backbone, never the storage order of the exon list).
 */
export interface GeneviewIsoform {
  transcript_id: string
  exons: [number, number][]
}

/** One PAS's usage within one cluster (backend schemas.py `GeneviewClusterValue`).
 * `proportion` is `null` when the gene had zero reads in this cluster at all
 * (never coerced to 0 — a true zero-usage PAS and "gene not expressed here"
 * are different facts, matching the matplotlib reference's NaN-vs-0 split). */
export interface GeneviewClusterValue {
  pas_uid: string
  reads_per_cell: number
  proportion: number | null
}

/**
 * Per-cluster PAS-usage track (backend schemas.py `GeneviewClusterTrack`) --
 * the data behind each "cluster N (n=…)" mini bar chart in the geneview,
 * mirroring PeakATail's own `gene_track_matplotlib.py` renderer. `values` is
 * POSITIONALLY aligned with `GeneviewLayerData.pas` (same order, same
 * length) so layers can zip them by index without a pas_uid lookup.
 */
export interface GeneviewClusterTrack {
  cluster: string
  n_cells: number
  values: GeneviewClusterValue[]
}

export interface GeneviewLayerData {
  gene: GeneSummary
  window: { chrom: string | null; start: number | null; end: number | null }
  pas: GeneviewPas[]
  diff: FindingRow[]
  length: LengthRow[]
  coverage: null // roadmap B — coverage lane hidden in v1
  /** Data-availability flags from backend schemas.py GeneviewData.gates (spec §5: fail loud, not blank). */
  gates: string[]
  /** Isoform/exon structure for the always-on gene-model track; empty when no GTF was configured for this run. */
  isoforms: GeneviewIsoform[]
  /** Per-cluster PAS-usage proportion tracks (the figure's viridis bar rows); empty when clusters.h5ad was unreadable. */
  clusterTracks: GeneviewClusterTrack[]
}

// ---------------------------------------------------------------------------
// Real ema geneview (2026-08-14) -- replaces the hand-rolled
// GeneviewLayerData/GeneviewCanvas track rendering above (still kept around
// for DetailPanel's PAS-selection typing; NOT used by GeneView anymore) with
// the actual `ema switch geneview` output: an interactive plotly figure and
// a static matplotlib figure, both generated on demand by a host-side
// worker and served as real files (backend schemas.py GeneviewRender /
// GeneviewPasDistanceRow, api/geneview.py). GeneView embeds the figure
// directly (iframe for plotly, img for matplotlib) rather than re-drawing
// anything client-side.
// ---------------------------------------------------------------------------

/** One row of the PAS-distance table ema draws beneath the gene panel
 * (`--pas-distance-table`, on by default from the hub) and this type mirrors
 * for a real, readable table alongside the embedded figure. */
export interface GeneviewPasDistanceRow {
  rank: number
  pas_id: string
  chrom: string
  strand: '+' | '-'
  start: number
  end: number
  width_bp: number
  summit_pos: number
  gap_to_next_bp: number | null
  summit_dist_to_next_bp: number | null
}

/** `GET /genes/{id}/geneview/meta` -- metadata + the PAS-distance table for
 * the currently-cached/just-generated real geneview figure. Also the signal
 * GeneView uses to know a cache-miss finished generating (and warmed the
 * cache) before pointing the plotly iframe / matplotlib img at the figure
 * endpoints, so those load instantly instead of racing a ~10-25s cold
 * render. */
export interface GeneviewRenderMeta {
  gene_id: string
  gene_name: string
  run_id: string
  dataset_id: string
  cluster_key: string
  chrom: string | null
  start: number | null
  end: number | null
  strand: '+' | '-' | null
  n_pas: number | null
  n_clusters_rendered: number | null
  n_isoforms: number | null
  cached: boolean
  duration_sec: number
  pas_distances: GeneviewPasDistanceRow[]
}

export interface UmapPoint {
  cell_uid: string
  x: number
  y: number
  leiden: string
  celltype: string | null
  stage: string | null
  sample: string | null
}

/**
 * Matches backend schemas.py `StubResponse` -- both `/concordance` and
 * `/benchmarks` return exactly this shape (a single object, not an array of
 * per-pair/per-metric rows) because no contract schema exists yet for
 * either artifact type; `available` is always `false` today. The earlier
 * `ConcordanceSummary`/`BenchmarkSummary` per-row shapes never matched a
 * real response.
 */
export interface StubResponse {
  run_id: string
  available: boolean
  note: string
}

/**
 * Backend schemas.py `SearchResults` (`GET /search?q=`) returns three
 * separately-typed arrays -- `{q, genes: [{gene_id}], pas: PasLedgerRow[],
 * cells: CellLedgerRow[]}` -- not a unified `SearchResult[]`. `SearchResult`
 * below is a frontend-only normalized shape the API client folds the three
 * arrays into for TopBar's dropdown, kept for that UI convenience -- it is
 * NOT what `fetchJson('/search', ...)` returns directly (see client.ts).
 */
export interface BackendSearchResults {
  q: string
  genes: { gene_id: string }[]
  pas: PasLedgerRow[]
  cells: CellLedgerRow[]
}

export interface SearchResult {
  kind: 'gene' | 'pas' | 'cell'
  id: string
  label: string
  sublabel: string | null
}

/**
 * A `GeneviewPas` enriched at click-time with everything else the geneview
 * canvas already had in hand for that PAS (design brief: "click → emit a
 * selection event with full PAS metadata (pas_uid, coords, gene, per-cluster
 * proportion, per-strategy diff q/Δ + length direction)"). Extends
 * `GeneviewPas` rather than replacing it, so every existing consumer that
 * only knows about `GeneviewPas` (DetailPanel's `isFullPasDetail` narrowing,
 * etc.) keeps working unchanged; the extra fields are additive and optional.
 */
export interface GeneviewPasSelection extends GeneviewPas {
  /** Within-gene usage proportion for this PAS, keyed by cluster label (from `GeneviewClusterTrack`). */
  cluster_proportions?: Record<string, number | null>
  /** Per-strategy switch-diff summary for this PAS, from whatever `findings` were loaded in the current geneview window. */
  diff_summary?: { strategy: FindingRow['strategy']; qvalue: number; delta_proportion: number; direction: FindingRow['direction'] }[]
  /** Per-strategy switch-length direction for this PAS's gene (see `LengthRow.direction` docstring re: per-PAS vs per-gene grain). */
  length_summary?: { strategy: LengthRow['strategy']; direction: LengthRow['direction'] }[]
}

/** Union type for the shared DetailPanel's polymorphic selection.
 * `pas` accepts `GeneviewPas`/`GeneviewPasSelection` too -- clicking a stem
 * or bar in the geneview canvas only has the windowed geneview-data shape on
 * hand, not a full PasDetail/provenance fetch; DetailPanel renders the
 * fields it has and falls back gracefully (`—`) for the ones only a full
 * PasDetail carries. */
export type SelectedEntity =
  | { kind: 'gene'; data: GeneSummary }
  | { kind: 'pas'; data: PasDetail | GeneviewPas | GeneviewPasSelection }
  | { kind: 'cell'; data: CellDetail }

/** A pinned entity in the pin tray (subset of SelectedEntity, tagged for display). */
export interface PinnedEntity {
  kind: SelectedEntity['kind']
  id: string
  label: string
  pinnedAt: number
}

/** Contract version this frontend build was written against; used for the
 * fail-loud mismatch banner once the backend starts reporting its own version. */
export const CONTRACT_VERSION = '0.0.0-interim'
