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

export interface RunSummary {
  run_id: string
  dataset_id: string
  label: string
  contract_version: string
  created_at: string
  n_samples: number
  n_cells: number
  n_pas: number
}

export interface StageCount {
  stage: string
  n_pas: number
  n_cells: number
}

export interface RunQc {
  run_id: string
  stages: StageCount[]
  config_diff: Record<string, { resolved: unknown; default: unknown }> | null
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

export interface ConcordanceSummary {
  pair: string
  ari: number
  ami: number
}

export interface BenchmarkSummary {
  name: string
  metric: string
  value: number
  note: string | null
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
