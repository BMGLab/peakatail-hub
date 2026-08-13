"""DuckDB DDL for the hub's read store.

One row per (run_id, entity) in each table -- multi-run is supported from
day one (the `runs` table + `run_id` column on every other table) even
though v1 typically indexes a single runs_root with a handful of runs.

Design notes:
- `runs.manifest_checksum` is the idempotency gate (see index/indexer.py):
  sha256 of the raw manifest JSON bytes. Unchanged manifest -> unchanged
  checksum -> `hub index` treats the run as already-indexed and skips it
  entirely (no deletes, no inserts -- a true no-op, not just a cheap
  upsert), which is what the idempotency test in tests/test_indexer.py
  asserts.
- Every other table's primary read pattern is `WHERE run_id = ?`; range/
  facet/pagination queries additionally filter on the columns spec §3 lists
  per endpoint.
- `umap_points` is the one denormalized table sourced from clusters.h5ad
  (via Run.open_clusters_h5ad(), the indexer's single h5ad touch point --
  see index/indexer.py) rather than from a TSV/parquet ledger artifact.
"""

from __future__ import annotations

import duckdb

DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id                VARCHAR PRIMARY KEY,
    root                  VARCHAR,
    contract_version      VARCHAR,
    manifest_checksum     VARCHAR,
    -- Idempotency fix (2026-07-14): manifest_checksum alone is NOT enough --
    -- a run whose ledgers/parquet/h5ad changed but whose run_manifest.json
    -- bytes happened not to (e.g. a fixture regenerated in place, or an
    -- engine writer that emits the manifest before/separately from the
    -- artifacts it references) was silently treated as unchanged and
    -- skipped, leaving stale data in the store indefinitely. See
    -- index/indexer.py::_artifacts_fingerprint -- a run is only skipped
    -- when BOTH manifest_checksum AND artifacts_fingerprint match.
    artifacts_fingerprint VARCHAR,
    resolved_config       VARCHAR,  -- JSON-encoded dict
    stratum_to_label      VARCHAR,  -- JSON-encoded dict
    n_pas                 INTEGER,
    n_cells               INTEGER,
    n_genes               INTEGER,
    n_datasets            INTEGER,
    n_findings            INTEGER,
    n_length_rows         INTEGER,
    -- Which registered `sources` row last (re)indexed this run_id, NULL for
    -- runs indexed before the sources feature existed or via the bare
    -- `hub index <dir>` CLI outside of any registered source. See
    -- index/indexer.py::index_source -- a run already indexed elsewhere
    -- (manifest+artifacts unchanged, so index_run() skips the heavy
    -- re-index) still gets this column re-pointed at whichever source most
    -- recently discovered it, via queries.touch_run_source.
    source_id             VARCHAR,
    indexed_at            TIMESTAMP
);

-- Multi-directory SOURCES manager (dashboard feature): one row per
-- registered runs-root directory. A DuckDB table rather than a sidecar JSON
-- file -- it's already the hub's one persistence mechanism, gets the same
-- transactional/idempotent guarantees as everything else here, and needs no
-- new file-locking story alongside the existing single-writer DuckDB file.
CREATE TABLE IF NOT EXISTS sources (
    source_id         VARCHAR PRIMARY KEY,
    path              VARCHAR UNIQUE,  -- resolved absolute path; add is idempotent per-path
    label             VARCHAR,
    added_at          TIMESTAMP,
    last_scanned_at   TIMESTAMP,
    last_scan_status  VARCHAR,  -- 'ok' | 'empty' | 'error' | NULL (never scanned)
    last_scan_error   VARCHAR
);

CREATE TABLE IF NOT EXISTS pas_ledger (
    run_id            VARCHAR,
    pas_uid           VARCHAR,
    orig_pas_key      VARCHAR,
    chrom             VARCHAR,
    start             BIGINT,
    "end"             BIGINT,
    strand            VARCHAR,
    unified_pas_id    VARCHAR,
    snap_distance_bp  BIGINT,
    gene_id           VARCHAR,
    gene_distance_bp  BIGINT,
    tier              VARCHAR,
    last_stage        VARCHAR,
    dropped_at        VARCHAR,
    drop_reason       VARCHAR
);

CREATE TABLE IF NOT EXISTS cell_ledger (
    run_id       VARCHAR,
    cell_uid     VARCHAR,
    barcode      VARCHAR,
    dataset_id   VARCHAR,
    total_reads  BIGINT,
    n_pas        BIGINT,
    dropped_at   VARCHAR,
    drop_reason  VARCHAR,
    cluster      VARCHAR
);

CREATE TABLE IF NOT EXISTS findings_long (
    run_id               VARCHAR,
    finding_uid          VARCHAR,
    pas_uid              VARCHAR,
    gene_id              VARCHAR,
    canonical_cluster    VARCHAR,
    comparison_cluster   VARCHAR,
    celltype             VARCHAR,
    strategy             VARCHAR,
    arm                  VARCHAR,
    direction            VARCHAR,
    utr_class            VARCHAR,
    qvalue               DOUBLE,
    pvalue               DOUBLE,
    delta_proportion     DOUBLE,
    log2fc               DOUBLE,
    odds_ratio           DOUBLE,
    n_cells              BIGINT,
    n_reads              BIGINT,
    n_cells_subject      BIGINT,
    n_cells_comparison   BIGINT,
    n_reads_subject      BIGINT,
    n_reads_comparison   BIGINT
);

CREATE TABLE IF NOT EXISTS length_long (
    run_id             VARCHAR,
    strategy           VARCHAR,
    gene_id            VARCHAR,
    transcript_id      VARCHAR,
    cell_uid           VARCHAR,
    canonical_cluster  VARCHAR,
    value              DOUBLE,
    pas_uid            VARCHAR,
    rank               INTEGER,
    direction          VARCHAR
);

CREATE TABLE IF NOT EXISTS umap_points (
    run_id             VARCHAR,
    dataset_id         VARCHAR,
    cell_uid           VARCHAR,
    x                  DOUBLE,
    y                  DOUBLE,
    leiden             VARCHAR,
    canonical_cluster  VARCHAR,
    celltype           VARCHAR,  -- gated: NULL until A1/A2/B2 land, see spec §7c
    stage              VARCHAR,  -- gated: NULL until B7 lands
    sample             VARCHAR   -- gated: NULL until B7 lands
);

-- B3_switch results (2026-08-13 multi-dataset fix, task brief item 4: "a
-- run has MULTIPLE results" -- per-dataset clusterings (umap_points above)
-- and switch-analysis results, surfaced truthfully rather than assumed to
-- be a single findings_long.parquet). Switch-diff results are folded
-- directly into `findings_long` (see index/indexer.py::_switch_diff_findings_df
-- -- the real switch_diff_long.parquet is already FindingRow-shaped); these
-- three tables cover what findings_long can't: the length-trend-across-
-- stages headline (trend_summary/trend_gene, fully ingested -- small, a few
-- thousand rows/celltype) and a cheap stat-only inventory of the
-- classic/proportion/shannon length results (availability -- NOT
-- fully ingested, those are per-cell x per-gene files seen up to ~100GB+
-- for a single cohort run).
CREATE TABLE IF NOT EXISTS switch_trend_summary (
    run_id         VARCHAR,
    celltype       VARCHAR,
    n_stages       INTEGER,
    slope          DOUBLE,
    spearman       DOUBLE,
    direction      VARCHAR,
    value_col      VARCHAR,
    mean_by_stage  VARCHAR  -- JSON-encoded {stage: mean_value}
);

CREATE TABLE IF NOT EXISTS switch_trend_gene (
    run_id     VARCHAR,
    celltype   VARCHAR,
    gene_id    VARCHAR,
    n_stages   INTEGER,
    slope      DOUBLE,
    spearman   DOUBLE,
    direction  VARCHAR
);

CREATE TABLE IF NOT EXISTS switch_availability (
    run_id           VARCHAR,
    celltype         VARCHAR,  -- NULL for run-level results (e.g. cluster match)
    kind             VARCHAR,  -- 'length' | 'match' (diff is queryable from findings_long directly)
    subkind          VARCHAR,  -- 'classic' | 'proportion' | 'shannon' for kind='length'; NULL otherwise
    file_path        VARCHAR,  -- run-relative path to the primary artifact
    file_size_bytes  BIGINT
);

CREATE INDEX IF NOT EXISTS idx_switch_trend_summary_run ON switch_trend_summary(run_id);
CREATE INDEX IF NOT EXISTS idx_switch_trend_gene_run ON switch_trend_gene(run_id, celltype);
CREATE INDEX IF NOT EXISTS idx_switch_availability_run ON switch_availability(run_id);

CREATE INDEX IF NOT EXISTS idx_pas_ledger_run ON pas_ledger(run_id);
CREATE INDEX IF NOT EXISTS idx_pas_ledger_gene ON pas_ledger(run_id, gene_id);
CREATE INDEX IF NOT EXISTS idx_cell_ledger_run ON cell_ledger(run_id);
CREATE INDEX IF NOT EXISTS idx_findings_run ON findings_long(run_id);
CREATE INDEX IF NOT EXISTS idx_findings_gene ON findings_long(run_id, gene_id);
CREATE INDEX IF NOT EXISTS idx_length_run ON length_long(run_id);
CREATE INDEX IF NOT EXISTS idx_length_gene ON length_long(run_id, gene_id);
CREATE INDEX IF NOT EXISTS idx_umap_run ON umap_points(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_source ON runs(source_id);
"""

# Migration for DuckDB files created before the sources feature existed:
# `CREATE TABLE IF NOT EXISTS runs (...)` above is a no-op once the table
# already exists, so a pre-existing `runs` table never gains the new
# `source_id` column from the DDL string alone. `ADD COLUMN IF NOT EXISTS`
# is itself idempotent, so re-running this on an already-migrated DB (or a
# brand new one where the CREATE TABLE just added the column) is a safe
# no-op either way.
_MIGRATIONS = """
ALTER TABLE runs ADD COLUMN IF NOT EXISTS source_id VARCHAR;
"""


def apply_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(DDL)
    con.execute(_MIGRATIONS)
