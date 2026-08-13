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
    -- Whether this run has ANY atlas-snap provenance (<run>/unified/
    -- atlas_status.tsv exists) -- absent entirely on `reannotate` runs (no
    -- snap step of their own). Lets the PAS browser render an honest
    -- "N/A (no atlas-snap step)" for the whole snap_distance_bp column
    -- instead of a bare per-row dash indistinguishable from broken data.
    -- See index/indexer.py::_atlas_snap_available / _snap_distance_lookup.
    atlas_snap_available  BOOLEAN,
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
    -- Human-readable gene symbol (e.g. "SAMD11"), 2026-08-14 -- sourced from
    -- annotatedpas.bed's own gene_symbol column at index time (see
    -- index/indexer.py::_pas_annot_df); NULL on the real provenance ledger
    -- (fixture runs) or any PAS the annotation step didn't assign a gene to.
    gene_symbol       VARCHAR,
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

-- `slope`/`spearman` (2026-08-14, appended last -- see the strategy-column
-- comment on switch_trend_summary/switch_trend_gene above for why append-
-- only ordering matters for `_insert_df`'s positional INSERT): populated
-- ONLY for the length-strategy pseudo-findings (classic/proportion/shannon,
-- folded in from switch_trend_gene -- see
-- index/indexer.py::_switch_length_findings_df), NULL for real per-PAS
-- diff findings (fisher/nb_multi), which have no slope/spearman concept.
-- `qvalue`/`pvalue`/`n_reads`/`delta_proportion` are, symmetrically, always
-- NULL for length rows (no PAS-level test exists to report them from) --
-- see FindingRowView's docstring in schemas.py for the full "findings_long
-- is now two grains" picture.
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
    n_reads_comparison   BIGINT,
    slope                DOUBLE,
    spearman             DOUBLE
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
-- `strategy` (2026-08-14, appended last -- see _MIGRATIONS below, ALTER TABLE
-- ADD COLUMN always appends, and `_insert_df`'s `INSERT INTO t SELECT *
-- FROM df` is POSITIONAL so a fresh-DB CREATE and an existing-DB ALTER must
-- agree on column order): which B3_switch/length subkind this trend was
-- computed from -- 'classic' (pdui, the only one the pipeline itself always
-- ran `ema switch trend` for), or 'proportion'/'shannon' (computed
-- out-of-band against the same run's length/<ct>/{proportion,shannon}
-- TSVs -- see index/indexer.py::_switch_trend_dfs for the two directory
-- layouts this reads: classic's legacy flat `trend/<ct>/length_trend.json`
-- vs proportion/shannon's `trend/<ct>/<strategy>/length_trend.json`).
-- NULL on rows written before this column existed; treat as 'classic' at
-- query time (COALESCE) rather than backfilling, since the flat layout IS
-- classic's real layout.
CREATE TABLE IF NOT EXISTS switch_trend_summary (
    run_id         VARCHAR,
    celltype       VARCHAR,
    n_stages       INTEGER,
    slope          DOUBLE,
    spearman       DOUBLE,
    direction      VARCHAR,
    value_col      VARCHAR,
    mean_by_stage  VARCHAR,  -- JSON-encoded {stage: mean_value}
    strategy       VARCHAR
);

CREATE TABLE IF NOT EXISTS switch_trend_gene (
    run_id     VARCHAR,
    celltype   VARCHAR,
    gene_id    VARCHAR,
    n_stages   INTEGER,
    slope      DOUBLE,
    spearman   DOUBLE,
    direction  VARCHAR,
    strategy   VARCHAR
);

CREATE TABLE IF NOT EXISTS switch_availability (
    run_id           VARCHAR,
    celltype         VARCHAR,  -- NULL for run-level results (e.g. cluster match)
    kind             VARCHAR,  -- 'length' | 'match' (diff is queryable from findings_long directly)
    subkind          VARCHAR,  -- 'classic' | 'proportion' | 'shannon' for kind='length'; NULL otherwise
    file_path        VARCHAR,  -- run-relative path to the primary artifact
    file_size_bytes  BIGINT
);

-- switch-diff nb_multi omnibus results (2026-08-14): a DIFFERENT row grain
-- than fisher's switch_diff_long.parquet (folded into findings_long, see
-- index/indexer.py::_switch_diff_findings_df) -- nb_multi_omnibus.tsv is one
-- row per PAS x celltype (an omnibus likelihood-ratio test across ALL
-- stages at once, not a pairwise contrast: no canonical_cluster/
-- comparison_cluster/direction/arm columns exist for it), so it cannot be
-- folded into findings_long without fabricating fields that don't exist.
-- Small (~700KB/~8k rows for a 24-celltype cohort run) -- fully ingested,
-- unlike B3_switch/length. gene_id is joined in at index time from
-- pas_ledger (same run-level unified pas_id space, see
-- index/indexer.py::_switch_nb_multi_df) so results are still gene-
-- browsable even though the raw TSV only has pas_id.
CREATE TABLE IF NOT EXISTS switch_nb_multi (
    run_id       VARCHAR,
    celltype     VARCHAR,
    pas_id       VARCHAR,
    gene_id      VARCHAR,   -- joined from pas_ledger; NULL if not resolvable
    pvalue       DOUBLE,
    qvalue       DOUBLE,
    test_stat    DOUBLE,
    df           INTEGER,
    dispersion   DOUBLE,
    n_cells      BIGINT
);

CREATE INDEX IF NOT EXISTS idx_switch_trend_summary_run ON switch_trend_summary(run_id);
CREATE INDEX IF NOT EXISTS idx_switch_trend_gene_run ON switch_trend_gene(run_id, celltype);
CREATE INDEX IF NOT EXISTS idx_switch_availability_run ON switch_availability(run_id);
CREATE INDEX IF NOT EXISTS idx_switch_nb_multi_run ON switch_nb_multi(run_id, celltype);
CREATE INDEX IF NOT EXISTS idx_switch_nb_multi_gene ON switch_nb_multi(run_id, gene_id);

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
ALTER TABLE runs ADD COLUMN IF NOT EXISTS atlas_snap_available BOOLEAN;
ALTER TABLE pas_ledger ADD COLUMN IF NOT EXISTS gene_symbol VARCHAR;
ALTER TABLE switch_trend_summary ADD COLUMN IF NOT EXISTS strategy VARCHAR;
ALTER TABLE switch_trend_gene ADD COLUMN IF NOT EXISTS strategy VARCHAR;
ALTER TABLE findings_long ADD COLUMN IF NOT EXISTS slope DOUBLE;
ALTER TABLE findings_long ADD COLUMN IF NOT EXISTS spearman DOUBLE;
"""

# `idx_switch_trend_gene_strategy` MUST be created here, not in the main DDL
# block above (2026-08-14 bug found deploying to a pre-existing live DB):
# `CREATE TABLE IF NOT EXISTS switch_trend_gene (...)` is a no-op on a table
# that already exists from before the `strategy` column was added -- so if
# the CREATE INDEX referencing `strategy` were part of that same DDL string,
# it would run BEFORE `_MIGRATIONS`' `ALTER TABLE ... ADD COLUMN strategy`
# ever executes, and DuckDB would raise "does not have a column named
# strategy" (this exact error crashed the live backend's startup on first
# deploy attempt). Only ever hit on an EXISTING db being migrated -- a fresh
# db's CREATE TABLE already includes the column, so a from-scratch/fixture
# test never exercises this ordering bug. Living in `_MIGRATIONS` guarantees
# the column-adding ALTER has already run in this same `apply_schema` call.
_POST_MIGRATION_DDL = """
CREATE INDEX IF NOT EXISTS idx_switch_trend_gene_strategy ON switch_trend_gene(run_id, celltype, strategy);
"""


def apply_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(DDL)
    con.execute(_MIGRATIONS)
    con.execute(_POST_MIGRATION_DDL)
