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
  direction: 'shorten' | 'lengthen' | 'flat' | null
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

export interface GeneSummary {
  gene_id: string
  gene_name: string
  chrom: string
  start: number
  end: number
  strand: '+' | '-'
  n_pas: number
}

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

export interface GeneviewLayerData {
  gene: GeneSummary
  window: { chrom: string; start: number; end: number }
  pas: PasDetail[]
  diff: FindingRow[]
  length: LengthRow[]
  coverage: null // roadmap B — coverage lane hidden in v1
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

/** Union type for the shared DetailPanel's polymorphic selection. */
export type SelectedEntity =
  | { kind: 'gene'; data: GeneSummary }
  | { kind: 'pas'; data: PasDetail }
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
