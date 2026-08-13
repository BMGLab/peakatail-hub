"""`hub index <runs_root>` — walk a runs-root directory, validate each run,
and (re)write its rows into the DuckDB store.

Idempotency contract (task brief: "re-running `hub index` on an unchanged
run must be a fast no-op"): each indexed run's row in the `runs` table
stores `manifest_checksum` (sha256 of the raw `run_manifest.json` bytes)
AND `artifacts_fingerprint` (a hash of every registered artifact's
(path, size, mtime_ns), see `_artifacts_fingerprint`). A run is skipped
ONLY when BOTH match what's already stored.

Why both: manifest_checksum ALONE is not sufficient. Bug found 2026-07-14 --
a fixture was regenerated in place (pas_ledger.tsv/length_long.parquet
content changed, e.g. a corrected pas_uid formula) without the manifest's
own bytes changing, and `hub index` silently treated the run as unchanged
and skipped re-indexing it, leaving the DuckDB store stale indefinitely
with no error or warning. This is exactly the silent-stale-data failure
mode the hub exists to prevent (spec §5 "fail loud"). `artifacts_fingerprint`
closes that gap: any change to a referenced artifact file's size or mtime
(content changes essentially always change at least one of those) now
forces a re-index even when the manifest itself is untouched.

mtime+size (not a content hash) is deliberate: it's the "cheaper proxy"
the task brief allows, and hashing full artifact contents (parquet files,
and potentially large `clusters.h5ad`) on every `hub index` pass would
defeat the entire point of the fast-no-op check. The tradeoff -- a content
change that happens to preserve both size and mtime exactly would still be
missed -- is accepted as extremely unlikely in practice (the engine writes
each artifact fresh per run) and is the same tradeoff any mtime-based build
system (make, etc.) makes.

A run whose manifest OR any artifact fingerprint changed (including "never
indexed before") is fully re-processed: its previous rows (if any) are
deleted and freshly re-inserted inside one transaction, so a partial
failure never leaves stale + fresh rows mixed for the same run_id.
"""

from __future__ import annotations

import hashlib
import json
import os
import logging
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from peakatail_contract import ContractValidationError
from peakatail_hub.io_compat import Run, validate_run

logger = logging.getLogger("peakatail_hub.index")


@dataclass
class IndexReport:
    """Summary of one `hub index` pass, for the CLI to print and tests to assert on."""

    indexed: list[str] = field(default_factory=list)
    skipped_unchanged: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)  # run_dir -> error text


def _manifest_checksum(manifest_path: Path) -> str:
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def _resolve_artifact_path(run_dir: Path, root: str | None, rel_path: str) -> Path:
    """Best-effort resolution mirroring `peakatail_io.Run._resolve_artifact`
    (try relative to `run_dir` first, then relative to the manifest's own
    `root` field, then bare) -- deliberately independent of that function
    (no Run/pydantic construction needed here) so the fingerprint can be
    computed before deciding whether to even open a `Run` at all.
    """
    p = Path(rel_path)
    if p.is_absolute():
        return p
    candidate = run_dir / p
    if candidate.exists():
        return candidate
    if root:
        candidate = Path(root) / p
        if candidate.exists():
            return candidate
    return run_dir / p


def _artifacts_fingerprint(run_dir: Path, manifest_json: dict) -> str:
    """Hash of every registered artifact's (path, size, mtime_ns), sorted by
    path for determinism. A missing file is fingerprinted too (as a
    sentinel), so a previously-missing artifact appearing later also
    triggers a re-index. See module docstring for why this exists alongside
    `manifest_checksum`.
    """
    root = manifest_json.get("root")
    entries: list[tuple[str, int, int]] = []
    for artifact in manifest_json.get("artifacts", []):
        rel_path = artifact.get("path")
        if not rel_path:
            continue
        resolved = _resolve_artifact_path(run_dir, root, rel_path)
        try:
            st = resolved.stat()
            entries.append((rel_path, st.st_size, st.st_mtime_ns))
        except OSError:
            entries.append((rel_path, -1, -1))
    entries.sort(key=lambda e: e[0])
    digest = hashlib.sha256()
    for rel_path, size, mtime_ns in entries:
        digest.update(f"{rel_path}\0{size}\0{mtime_ns}\n".encode())
    return digest.hexdigest()


def find_run_dirs(runs_root: Path) -> list[Path]:
    """Every directory under `runs_root` containing a `run_manifest.json`,
    one dir per run (the manifest itself may be arbitrarily deep).
    """
    return sorted(p.parent for p in Path(runs_root).rglob("run_manifest.json"))


def _existing_fingerprints(con: duckdb.DuckDBPyConnection, run_id: str) -> tuple[str, str] | None:
    row = con.execute(
        "SELECT manifest_checksum, artifacts_fingerprint FROM runs WHERE run_id = ?", [run_id]
    ).fetchone()
    if row is None:
        return None
    # artifacts_fingerprint may be NULL on a row written before this column
    # existed (a pre-2026-07-14 DuckDB file) -- treat as "no prior
    # fingerprint recorded", which never matches, forcing a one-time
    # re-index rather than erroring or silently trusting stale data.
    return (row[0], row[1] or "")


def _delete_run(con: duckdb.DuckDBPyConnection, run_id: str) -> None:
    for table in (
        "runs", "pas_ledger", "cell_ledger", "findings_long", "length_long", "umap_points",
        "switch_trend_summary", "switch_trend_gene", "switch_availability", "switch_nb_multi",
    ):
        con.execute(f"DELETE FROM {table} WHERE run_id = ?", [run_id])  # noqa: S608 -- table name from fixed whitelist above


def _pas_ledger_df(run_id: str, run: Run) -> pd.DataFrame:
    rows = run.pas_ledger()
    return pd.DataFrame(
        [
            {
                "run_id": run_id,
                "pas_uid": r.pas_uid,
                "orig_pas_key": r.orig_pas_key,
                "chrom": r.chrom,
                "start": r.start,
                "end": r.end,
                "strand": r.strand,
                "unified_pas_id": r.unified_pas_id,
                "snap_distance_bp": r.snap_distance_bp,
                "gene_id": r.gene_id,
                # Real provenance/pas_ledger.tsv has no gene_symbol column --
                # r.gene_symbol is the PasLedgerRow pydantic default (None).
                "gene_symbol": r.gene_symbol,
                "gene_distance_bp": r.gene_distance_bp,
                "tier": r.tier.value if r.tier is not None else None,
                "last_stage": r.last_stage,
                "dropped_at": r.dropped_at,
                "drop_reason": r.drop_reason,
            }
            for r in rows
        ]
    )


def _pas_summit_pos(start: int, end: int, strand: str) -> int:
    """Strand-aware 3'-summit position from a BED interval -- see
    `peakatail_contract.ids.pas_summit_pos` (duplicated here, not imported,
    to keep this indexer's annotatedpas.bed loader a pure pandas/numpy
    vectorized pass rather than a per-row Python call into the contract
    package for 100k+ rows)."""
    return int(end) - 1 if strand == "+" else int(start)


def _pas_annot_df(run_id: str, run_dir: Path) -> pd.DataFrame:
    """Real-run PAS+gene source: `<run_dir>/annotatedpas.bed`.

    FINDING (2026-08-13, hub multi-dataset investigation): on every real
    engine run inspected (B1_cohort_full, grid/*, reannotate/*),
    `provenance/pas_ledger.tsv` is an EMPTY STUB -- present but with blank
    chrom/start/end/gene_id (engine provenance is wired incrementally, see
    `index_run`'s existing HUB_INDEX_LEDGERS note). `annotatedpas.bed`, by
    contrast, is the real final annotated-PAS artifact the engine always
    writes: tab-separated, no header, columns `chrom, start, end, pas_id,
    gene_id, gene_symbol, strand, <tier_rank>, tier_label` (verified against
    real output, e.g. `1  928219  928229  144  ENSG00000187634  SAMD11  +  0
    TIER_1`) -- 9 columns on every run inspected, but this reader tolerates
    8 (older/other runs may omit the trailing numeric tier-rank column) by
    treating the LAST column as the tier label unconditionally.

    Returns rows shaped exactly like `_pas_ledger_df`'s output (same column
    set, insertable into the same `pas_ledger` table) so every existing
    pas_ledger-backed endpoint (PAS browser, Genes browser, geneview
    coordinates, gene_pas_span, search) lights up with real data with zero
    downstream code changes. Caveats, documented rather than hidden:

    * `dropped_at` is always `''` (survived) -- annotatedpas.bed only lists
      PAS that made it through gene assignment; no drop-site provenance is
      available from this source (same gap `qc_funnel`'s gate_note already
      describes for the real ledger).
    * `unified_pas_id` is set to the bed's own `pas_id` (col 4), which is
      the RUN-level unified id (post pas_merge/atlas-snap). Per-dataset
      `clusters.h5ad` var_names are a DIFFERENT, dataset-LOCAL pas_id space
      (pre-unify) -- so `unified_pas_id` from this source will generally
      NOT resolve directly against a given dataset's h5ad var_names for a
      multi-dataset run. `genes.py`'s cluster-tracks/`gene_counts` joins
      already degrade gracefully (empty tracks, not a 500) when a var_name
      isn't present -- this is a known, documented gap, not a crash risk.
      Reconciling the two id spaces needs the engine's own
      `unified/pas_uid.tsv` / `unified/multi_sample_pas_mapping.tsv`
      sidecars and is out of this fix's scope.
    * `orig_pas_key` has no source in this file; falls back to the bed
      `pas_id`.
    * `gene_distance_bp`/`snap_distance_bp` are NOT in this file either, but
      ARE recovered from two other cheap, always-or-usually-present
      artifacts -- see `_gene_distance_lookup`/`_snap_distance_lookup`
      below for what each is sourced from and why (this used to leave both
      columns permanently blank in the PAS browser, read as "broken" rather
      than "genuinely not applicable" -- see `index_run`'s
      `atlas_snap_available` note for how `snap_distance_bp`'s absence is
      now distinguished from a genuine zero/no-match).

    Returns an empty DataFrame (never raises) if `annotatedpas.bed` doesn't
    exist for this run -- callers fall back to whatever `_pas_ledger_df`
    already produced (fixture runs, which have no annotatedpas.bed but do
    have a real provenance ledger).
    """
    path = run_dir / "annotatedpas.bed"
    if not path.exists():
        return pd.DataFrame()
    try:
        raw = pd.read_csv(
            path,
            sep="\t",
            header=None,
            dtype=str,
            keep_default_na=False,
            engine="c",
        )
    except Exception as exc:  # noqa: BLE001 -- a malformed bed must not abort indexing
        logger.warning("run_id=%s: annotatedpas.bed at %s unreadable, skipping (%s)", run_id, path, exc)
        return pd.DataFrame()
    if raw.shape[1] < 8:
        logger.warning(
            "run_id=%s: annotatedpas.bed at %s has %d columns (<8 expected: chrom,start,end,pas_id,gene_id,"
            "gene_symbol,strand,tier[,tier_label]), skipping",
            run_id, path, raw.shape[1],
        )
        return pd.DataFrame()

    chrom = raw[0].astype(str)
    start = raw[1].astype(np.int64)
    end = raw[2].astype(np.int64)
    pas_id = raw[3].astype(str)
    gene_id = raw[4].astype(str)
    gene_symbol = raw[5].astype(str)
    strand = raw[6].astype(str)
    # Last column is the tier label ("TIER_1"/.../"INTERGENIC") on every real
    # run inspected, whether the file has 8 or 9 columns.
    tier_label = raw[raw.shape[1] - 1].astype(str)

    pos = np.where(strand.to_numpy() == "+", end.to_numpy() - 1, start.to_numpy())
    pos_series = pd.Series(pos, index=raw.index)
    pas_uid = chrom.str.cat(pos_series.astype(str), sep=":").str.cat(strand, sep=":")

    n = len(raw)
    gene_distance = _gene_distance_lookup(run_dir, gene_id, pos_series)
    snap_distance = _snap_distance_lookup(run_dir, pas_id)

    return pd.DataFrame(
        {
            "run_id": [run_id] * n,
            "pas_uid": pas_uid,
            "orig_pas_key": pas_id,
            "chrom": chrom,
            "start": start,
            "end": end,
            "strand": strand,
            "unified_pas_id": pas_id,
            "snap_distance_bp": snap_distance,
            "gene_id": gene_id,
            # Empty-string convention (matches gene_id's own ''=INTERGENIC) --
            # normalized to real None downstream by pandas/DuckDB NULL
            # handling is NOT automatic for empty strings, so this stays ''
            # here (consistent with every other str column on this table)
            # and callers treat '' as "no symbol" the same way they already
            # treat gene_id=='' as "no gene".
            "gene_symbol": gene_symbol,
            "gene_distance_bp": gene_distance,
            "tier": tier_label,
            "last_stage": ["annotated"] * n,
            "dropped_at": [""] * n,
            "drop_reason": [None] * n,
        }
    )


def _gene_distance_lookup(run_dir: Path, gene_id: pd.Series, pas_pos: pd.Series) -> pd.Series:
    """Real source for `gene_distance_bp` ("distance (bp) from this PAS to
    gene_id's 3' end", PasLedgerRow's own docstring): `<run_dir>/gene_end.bed`
    (BED6-ish, no header, columns `chrom, start, end, gene_id, gene_symbol,
    strand` -- present on every run inspected, ~40k genes, cheap to read
    fully). Distance is `abs(pas_summit_pos - gene_3prime_end_pos)`, where
    `gene_3prime_end_pos` uses the SAME strand-aware convention as
    `_pas_summit_pos` (the gene's `end` column on `+`, `start` on `-`) -- PAS
    calling assigns a PAS to the nearest gene by exactly this distance, so a
    surviving PAS is typically very close to (often 0 from) its assigned
    gene's 3' end; a large value here is a real, meaningful signal (e.g. a
    3'UTR-extension PAS), not a data-quality flag.

    Returns an all-null `Int64` series (never raises) if `gene_end.bed`
    doesn't exist, is unreadable, or a given row's `gene_id` isn't in it
    (INTERGENIC-tier rows have `gene_id == ''` and are always null here).
    """
    n = len(gene_id)
    null_result = pd.array([None] * n, dtype="Int64")
    path = run_dir / "gene_end.bed"
    if not path.exists():
        return null_result
    try:
        genes = pd.read_csv(
            path, sep="\t", header=None, names=["chrom", "start", "end", "gene_id", "gene_symbol", "strand"],
            dtype={"chrom": str, "start": np.int64, "end": np.int64, "gene_id": str, "gene_symbol": str, "strand": str},
            usecols=[0, 1, 2, 3, 5], engine="c",
        )
    except Exception as exc:  # noqa: BLE001 -- a malformed gene_end.bed must not abort indexing
        logger.warning("run_id gene_distance_bp lookup: %s unreadable, leaving column null (%s)", path, exc)
        return null_result
    genes = genes.drop_duplicates(subset="gene_id", keep="first").set_index("gene_id")
    gene_end_pos = np.where(genes["strand"].to_numpy() == "+", genes["end"].to_numpy() - 1, genes["start"].to_numpy())
    gene_end_by_id = pd.Series(gene_end_pos, index=genes.index)

    matched_end = gene_id.map(gene_end_by_id)  # NaN where gene_id unknown/empty
    distance = (pas_pos.to_numpy(dtype=np.float64) - matched_end.to_numpy(dtype=np.float64))
    distance = np.abs(distance)
    return pd.array([None if pd.isna(d) else int(d) for d in distance], dtype="Int64")


def _snap_distance_lookup(run_dir: Path, pas_id: pd.Series) -> pd.Series:
    """Real source for `snap_distance_bp`: `<run_dir>/unified/atlas_status.tsv`
    (columns `unified_pas_id, atlas_match, atlas_distance_bp`), written only
    when the run used atlas-snap unification -- absent entirely on
    `reannotate` runs (branched from an already-unified state, no snap step
    of their own), which is a genuinely different, legitimate state from "PAS
    calling ran but nothing snapped" and is surfaced as such via
    `index_run`'s `atlas_snap_available` run-level flag (see there), not
    conflated with a per-row null here.

    `unified_pas_id` in this file is the SAME run-level unified id as
    annotatedpas.bed's `pas_id` column (verified: `atlas_match=True` row
    count here matches `n_snapped` in `figures/atlas_snap.meta.json`
    exactly on B1_cohort_full) -- joins directly on it, no id-space mismatch
    (unlike `unified_pas_id` vs per-dataset h5ad var_names, see this
    function's caller's docstring).

    Only `atlas_match == True` rows populate a real distance -- `atlas_status.tsv`
    also records a distance-to-nearest-atlas-candidate for UNMATCHED PAS
    (`atlas_match == False`, e.g. "168" bp away, still too far to snap), and
    that is NOT what `snap_distance_bp` means ("distance to the atlas PAS
    this was snapped to" -- PasLedgerRow's own docstring); those rows are
    null here, not the raw nearest-candidate distance.
    """
    n = len(pas_id)
    null_result = pd.array([None] * n, dtype="Int64")
    path = run_dir / "unified" / "atlas_status.tsv"
    if not path.exists():
        return null_result
    try:
        status = pd.read_csv(
            path, sep="\t", dtype={"unified_pas_id": str, "atlas_match": str, "atlas_distance_bp": str},
            usecols=["unified_pas_id", "atlas_match", "atlas_distance_bp"], engine="c",
        )
    except Exception as exc:  # noqa: BLE001 -- a malformed atlas_status.tsv must not abort indexing
        logger.warning("run_id snap_distance_bp lookup: %s unreadable, leaving column null (%s)", path, exc)
        return null_result
    matched = status[status["atlas_match"].str.lower() == "true"].drop_duplicates(subset="unified_pas_id", keep="first")
    distance_by_id = matched.set_index("unified_pas_id")["atlas_distance_bp"]
    joined = pas_id.map(distance_by_id)
    return pd.array([None if pd.isna(v) else int(float(v)) for v in joined], dtype="Int64")


def _atlas_snap_available(run_dir: Path) -> bool:
    """Whether this run has ANY atlas-snap provenance at all (see
    `_snap_distance_lookup`) -- surfaced as a run-level flag (`runs.
    atlas_snap_available`, RunSummary) so the PAS browser can render
    "N/A (no atlas-snap step for this run)" for the whole column on a
    `reannotate` run instead of a bare em-dash per row that reads as broken
    data."""
    return (run_dir / "unified" / "atlas_status.tsv").exists()


def _cell_ledger_df(run_id: str, run: Run) -> pd.DataFrame:
    rows = run.cell_ledger()
    return pd.DataFrame(
        [
            {
                "run_id": run_id,
                "cell_uid": r.cell_uid,
                "barcode": r.barcode,
                "dataset_id": r.dataset_id,
                "total_reads": r.total_reads,
                "n_pas": r.n_pas,
                "dropped_at": r.dropped_at,
                "drop_reason": r.drop_reason,
                "cluster": r.cluster,
            }
            for r in rows
        ]
    )


def _findings_df(run_id: str, run: Run) -> pd.DataFrame:
    rows = run.findings()
    return pd.DataFrame(
        [
            {
                "run_id": run_id,
                "finding_uid": r.finding_uid,
                "pas_uid": r.pas_uid,
                "gene_id": r.gene_id,
                "canonical_cluster": r.canonical_cluster,
                "comparison_cluster": r.comparison_cluster,
                "celltype": r.celltype,
                "strategy": r.strategy.value,
                "arm": r.arm,
                "direction": r.direction.value,
                "utr_class": r.utr_class,
                "qvalue": r.qvalue,
                "pvalue": r.pvalue,
                "delta_proportion": r.delta_proportion,
                "log2fc": r.log2fc,
                "odds_ratio": r.odds_ratio,
                "n_cells": r.n_cells,
                "n_reads": r.n_reads,
                "n_cells_subject": r.n_cells_subject,
                "n_cells_comparison": r.n_cells_comparison,
                "n_reads_subject": r.n_reads_subject,
                "n_reads_comparison": r.n_reads_comparison,
            }
            for r in rows
        ]
    )


#: Exact column set/order of the `findings_long` table (minus `run_id`,
#: added separately) -- shared by `_findings_df` (via pydantic) above and
#: `_switch_diff_findings_df` below (which reads the parquet directly, no
#: pydantic round-trip, so it must match this list by hand).
_FINDINGS_TABLE_COLUMNS = [
    "finding_uid", "pas_uid", "gene_id", "canonical_cluster", "comparison_cluster",
    "celltype", "strategy", "arm", "direction", "utr_class",
    "qvalue", "pvalue", "delta_proportion", "log2fc", "odds_ratio",
    "n_cells", "n_reads", "n_cells_subject", "n_cells_comparison",
    "n_reads_subject", "n_reads_comparison",
]

#: The FULL findings_long insert shape (2026-08-14) -- `_FINDINGS_TABLE_COLUMNS`
#: above stays exactly the 21-column real-per-PAS-diff-file shape (fisher's
#: switch_diff_long.parquet genuinely has all of and only those columns --
#: `_switch_diff_findings_df` validates against it and would wrongly skip
#: every celltype if `slope`/`spearman` were added there). This wider list
#: is what `index_run` reindexes the assembled `findings_df` against right
#: before `_insert_df`, since `_insert_df`'s `INSERT INTO t SELECT * FROM df`
#: is POSITIONAL -- every source frame (fisher, nb_multi, length) can supply
#: a different subset/order of columns; `.reindex(columns=...)` here is what
#: guarantees the final frame matches findings_long's real column order
#: regardless (missing columns become NaN, not a silent column-shift bug --
#: see schema.py's `idx_switch_trend_gene_strategy` post-mortem comment for
#: exactly the failure mode this reindex exists to prevent).
_FINDINGS_INSERT_COLUMNS = ["run_id", *_FINDINGS_TABLE_COLUMNS, "slope", "spearman"]


def _switch_diff_findings_df(run_id: str, run_dir: Path) -> pd.DataFrame:
    """Real-run switch-diff results source:
    `B3_switch/diff/<celltype>/<strategy>/differential/switch_diff_long.parquet`.

    FINDING (2026-08-13): a real cohort run's `findings_long.parquet` (the
    engine E5 artifact `_findings_df` reads) does not exist at the run root
    -- switch-diff results instead live per-celltype-per-strategy under
    `B3_switch/diff/`. Each `switch_diff_long.parquet` there is ALREADY
    shaped almost exactly like `FindingRow`/the `findings_long` table (same
    21 columns, verified against real output) plus one extra
    `direction_basis` column this table doesn't have (dropped here). Reading
    these directly and appending them to `findings_df` means the existing
    Findings browser / geneview overlay / audit trail all light up with real
    switch-diff data for zero further code changes -- this is the most
    direct way to surface "B3_switch results as first-class results of the
    run" for the diff dimension (task brief item 4).

    Two real-data gaps handled explicitly, not silently:
    * `celltype` is `None` in the parquet itself (the stratification is
      encoded only by which directory the file lives under) -- backfilled
      here from the `<celltype>` path segment.
    * `finding_uid` as minted by the engine does NOT include celltype (see
      `peakatail_contract.ids.finding_uid` -- only arm/strategy/
      resolved_label(=cluster)/var_name/pas_uid), so the SAME finding_uid
      can legitimately recur across different celltype directories (the
      same PAS x cluster-pair x strategy combination tested within more
      than one stratum). Left as-is (not deduplicated/renamed): downstream
      consumers that filter by `celltype` (the Findings browser, geneview's
      `clusters` filter) still see the right row; only a bare `GET
      /findings/{finding_uid}` single-row lookup could return an
      arbitrary-but-plausible one of several celltype-variants sharing an
      id -- documented here rather than hidden, not worth a synthetic
      re-keying scheme for a browse-first UI.

    Returns an empty DataFrame (never raises) when `B3_switch/diff` doesn't
    exist, is empty, or a given file fails to read (logged, skipped --
    one bad celltype/strategy must not blank the whole run's findings).
    """
    diff_root = run_dir / "B3_switch" / "diff"
    if not diff_root.is_dir():
        return pd.DataFrame()
    frames: list[pd.DataFrame] = []
    for parquet_path in sorted(diff_root.glob("*/*/differential/switch_diff_long.parquet")):
        celltype = parquet_path.parents[2].name  # .../diff/<celltype>/<strategy>/differential/file.parquet
        try:
            df = pd.read_parquet(parquet_path)
        except Exception as exc:  # noqa: BLE001 -- one bad file must not abort the whole run
            logger.warning("run_id=%s: switch diff parquet %s unreadable, skipping (%s)", run_id, parquet_path, exc)
            continue
        missing = [c for c in _FINDINGS_TABLE_COLUMNS if c not in df.columns]
        if missing:
            logger.warning(
                "run_id=%s: switch diff parquet %s missing expected columns %s, skipping",
                run_id, parquet_path, missing,
            )
            continue
        df = df[_FINDINGS_TABLE_COLUMNS].copy()
        df["celltype"] = df["celltype"].where(df["celltype"].notna() & (df["celltype"] != ""), celltype)
        df.insert(0, "run_id", run_id)
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


_NB_MULTI_COLUMNS = ["pas_id", "pvalue", "qvalue", "test_stat", "df", "dispersion", "n_cells"]


def _switch_nb_multi_df(run_id: str, run_dir: Path, pas_gene_lookup: pd.Series) -> pd.DataFrame:
    """Real-run nb_multi omnibus results source:
    `B3_switch/diff/<celltype>/nb_multi/differential/nb_multi_omnibus.tsv`.

    FINDING (2026-08-14): unlike fisher's switch_diff_long.parquet (already
    FindingRow-shaped, folded straight into findings_long -- see
    `_switch_diff_findings_df`), nb_multi's own output is a genuinely
    DIFFERENT grain: one row per PAS x celltype (an omnibus likelihood-ratio
    test across ALL stages at once), with NO canonical_cluster/
    comparison_cluster/direction/arm/gene_id columns -- those concepts don't
    apply to an omnibus test the way they do a pairwise contrast, so this
    cannot be force-fit into findings_long without fabricating fields. Kept
    in its own `switch_nb_multi` table instead (see schema.py's table
    docstring for why). Small (~700KB/~8k rows for a 24-celltype cohort run)
    -- fully ingested, unlike B3_switch/length.

    `gene_id` is joined in from `pas_gene_lookup` (a `pas_id -> gene_id`
    Series built by the caller from THIS SAME run's just-computed pas_ledger
    DataFrame -- same run-level unified pas_id space as annotatedpas.bed,
    see `_pas_annot_df`) so nb_multi hits stay gene-browsable even though
    the raw TSV only ever has `pas_id`.

    Returns an empty DataFrame (never raises) when `B3_switch/diff` doesn't
    exist; one bad celltype's file is logged and skipped, not fatal.
    """
    diff_root = run_dir / "B3_switch" / "diff"
    if not diff_root.is_dir():
        return pd.DataFrame()
    frames: list[pd.DataFrame] = []
    for tsv_path in sorted(diff_root.glob("*/nb_multi/differential/nb_multi_omnibus.tsv")):
        celltype = tsv_path.parents[2].name  # .../diff/<celltype>/nb_multi/differential/file.tsv
        try:
            df = pd.read_csv(tsv_path, sep="\t", dtype={"pas_id": str})
        except Exception as exc:  # noqa: BLE001 -- one bad file must not abort the whole run
            logger.warning("run_id=%s: nb_multi_omnibus.tsv %s unreadable, skipping (%s)", run_id, tsv_path, exc)
            continue
        missing = [c for c in _NB_MULTI_COLUMNS if c not in df.columns]
        if missing:
            logger.warning(
                "run_id=%s: nb_multi_omnibus.tsv %s missing expected columns %s, skipping",
                run_id, tsv_path, missing,
            )
            continue
        df = df[_NB_MULTI_COLUMNS].copy()
        df["gene_id"] = df["pas_id"].map(pas_gene_lookup)
        df.insert(0, "celltype", celltype)
        df.insert(0, "run_id", run_id)
        frames.append(df[["run_id", "celltype", "pas_id", "gene_id", *_NB_MULTI_COLUMNS[1:]]])
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _switch_nb_multi_findings_df(nb_multi_df: pd.DataFrame, pas_uid_lookup: pd.Series) -> pd.DataFrame:
    """Fold nb_multi's omnibus rows into findings_long-shaped rows too
    (2026-08-14) -- previously ONLY fisher was ever folded into
    findings_long (see `_switch_diff_findings_df`), which is exactly why
    the Findings tab's strategy facet only ever showed fisher even though
    nb_multi was fully computed and already browsable one level down, via
    `/runs/{id}/switch/{celltype}/nb-multi`. Takes the SAME `nb_multi_df`
    `_switch_nb_multi_df` already parsed (run_id/celltype/pas_id/gene_id/
    pvalue/qvalue/test_stat/df/dispersion/n_cells) -- no second file read.

    nb_multi has no cluster1/cluster2 pairwise split (one omnibus LRT per
    PAS x celltype across ALL stages at once), so several FindingRow fields
    have no natural value here, each handled explicitly rather than
    fabricated:
    * `canonical_cluster` uses the sentinel `'ALL_STAGES'` (never a made-up
      pairwise cluster label) -- `comparison_cluster` stays None, which the
      contract's own FindingRow docstring already anticipated ("None for
      nb_multi omnibus rows, which have no single partner").
    * `direction` is always `'undetermined'` -- an omnibus test has no
      shorten/lengthen polarity to report, and D8 requires a real enum
      value, never a blank.
    * `delta_proportion`/`n_reads` are None (2026-08-14 contract change --
      `peakatail_contract.FindingRow` widened both to Optional specifically
      for this: the omnibus test reports neither).

    `pas_uid` is resolved via `pas_uid_lookup` (a `pas_id -> pas_uid`
    Series, same run-level unified pas_id space and same caller-built-it
    pattern as `pas_gene_lookup` in `index_run`). A lookup miss leaves
    `pas_uid` None -- naturally excludes that row from PAS-scoped queries
    (geneview overlay, `/pas/{id}` detail, both filter `pas_uid IN (...)`)
    without a crash; it stays fully visible in the general Findings browse.

    Returns an empty DataFrame (never raises) when `nb_multi_df` is empty.
    """
    if nb_multi_df.empty:
        return pd.DataFrame()
    from peakatail_contract import ids

    df = nb_multi_df.copy()
    df["pas_uid"] = df["pas_id"].map(pas_uid_lookup)
    # `ids.finding_uid`'s separator guard rejects ':' in `arm` (it's part of
    # the joined ID string itself) -- 'switch_diff_nb_multi' (underscore) is
    # what's actually minted with; the STORED `arm` column below still uses
    # 'switch_diff:nb_multi' (colon), matching fisher's own
    # 'switch_diff:fisher' convention for display/facet consistency -- the
    # engine's own switch_diff_long.parquet was never round-tripped through
    # this validator, so its colon-containing arm values predate this guard.
    df["finding_uid"] = [
        ids.finding_uid(celltype, pas_id, "nb_multi", "switch_diff_nb_multi", resolved_pas_uid or "")
        for celltype, pas_id, resolved_pas_uid in zip(df["celltype"], df["pas_id"], df["pas_uid"], strict=True)
    ]
    n = len(df)
    return pd.DataFrame(
        {
            "run_id": df["run_id"],
            "finding_uid": df["finding_uid"],
            "pas_uid": df["pas_uid"],
            "gene_id": df["gene_id"],
            "canonical_cluster": ["ALL_STAGES"] * n,
            "comparison_cluster": [None] * n,
            "celltype": df["celltype"],
            "strategy": ["nb_multi"] * n,
            "arm": ["switch_diff:nb_multi"] * n,
            "direction": ["undetermined"] * n,
            "utr_class": [None] * n,
            "qvalue": df["qvalue"],
            "pvalue": df["pvalue"],
            "delta_proportion": [None] * n,
            "log2fc": [None] * n,
            "odds_ratio": [None] * n,
            "n_cells": df["n_cells"],
            "n_reads": [None] * n,
            "n_cells_subject": [None] * n,
            "n_cells_comparison": [None] * n,
            "n_reads_subject": [None] * n,
            "n_reads_comparison": [None] * n,
            "slope": [None] * n,
            "spearman": [None] * n,
        }
    )


_SUMMARY_COLUMNS = ["run_id", "celltype", "n_stages", "slope", "spearman", "direction", "value_col", "mean_by_stage", "strategy"]
_GENE_COLUMNS = ["run_id", "celltype", "gene_id", "n_stages", "slope", "spearman", "direction", "strategy"]


def _read_one_trend(
    run_id: str, celltype: str, strategy: str, trend_dir: Path
) -> tuple[dict | None, pd.DataFrame | None]:
    """One (celltype, strategy) trend result -- `length_trend.json` +
    `length_trend_by_gene.tsv` inside `trend_dir`. Returns `(summary_row |
    None, gene_df | None)`; either half may be missing independently (a
    summary with no per-gene table, or vice versa) without failing the
    other. Never raises -- a bad file is logged and treated as absent.
    """
    summary_row = None
    json_path = trend_dir / "length_trend.json"
    if json_path.exists():
        try:
            summary = json.loads(json_path.read_text())
        except Exception as exc:  # noqa: BLE001
            logger.warning("run_id=%s: %s unreadable, skipping (%s)", run_id, json_path, exc)
            summary = None
        if summary is not None:
            summary_row = {
                "run_id": run_id,
                "celltype": celltype,
                "n_stages": summary.get("n_stages"),
                "slope": summary.get("slope"),
                "spearman": summary.get("spearman"),
                "direction": summary.get("direction"),
                "value_col": summary.get("value_col"),
                "mean_by_stage": json.dumps(summary.get("mean_by_stage") or {}),
                "strategy": strategy,
            }
    gene_df = None
    gene_path = trend_dir / "length_trend_by_gene.tsv"
    if gene_path.exists():
        try:
            gdf = pd.read_csv(gene_path, sep="\t")
        except Exception as exc:  # noqa: BLE001
            logger.warning("run_id=%s: %s unreadable, skipping (%s)", run_id, gene_path, exc)
            gdf = None
        if gdf is not None:
            keep = [c for c in ("gene_id", "n_stages", "slope", "spearman", "direction") if c in gdf.columns]
            gdf = gdf[keep].copy()
            gdf.insert(0, "celltype", celltype)
            gdf.insert(0, "run_id", run_id)
            gdf["strategy"] = strategy
            gene_df = gdf[_GENE_COLUMNS]
    return summary_row, gene_df


#: Strategy subdirs `_switch_trend_dfs` will actually read under
#: `trend/<celltype>/` (classic is handled separately, via the legacy flat
#: layout -- see below). Anything else found there (e.g. a scratch/backup
#: dir from out-of-band engine-writer work happening directly on the
#: analysis server) is skipped, not ingested as a fabricated strategy.
_KNOWN_LENGTH_TREND_SUBDIRS = {"proportion", "shannon"}


def _switch_trend_dfs(run_id: str, run_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Real-run 3'UTR-length-trend-across-stages source (the professor
    headline finding), now covering all three `B3_switch/length` strategies
    (2026-08-14, was classic-only): `run-x-celltype summary
    (slope/spearman/direction/mean_by_stage) and `length_trend_by_gene.tsv`
    (per-gene rows, a few thousand per celltype -- cheap to fully ingest,
    unlike B3_switch/length's per-cell files, see `_switch_availability_df`).

    Two directory layouts, both read here (see schema.py's `strategy` column
    docstring for why they differ): classic is what the pipeline itself
    always computed, directly at the legacy flat path
    `trend/<celltype>/length_trend.json`; proportion/shannon are computed
    out-of-band (the pipeline never ran `ema switch trend` for them -- no
    comparable per-celltype summary existed) into a per-strategy subdir,
    `trend/<celltype>/<strategy>/length_trend.json`, mirroring
    `B3_switch/length/<celltype>/<strategy>/`'s own layout. A celltype can
    have any subset of the three; each is independent (2026-08-14 principle:
    "surface all strategies, let the user select"). Returns `(summary_df,
    gene_df)`, both possibly empty (never raises) when `B3_switch/trend`
    doesn't exist.
    """
    trend_root = run_dir / "B3_switch" / "trend"
    if not trend_root.is_dir():
        return pd.DataFrame(columns=_SUMMARY_COLUMNS), pd.DataFrame(columns=_GENE_COLUMNS)
    summary_rows: list[dict] = []
    gene_frames: list[pd.DataFrame] = []
    for celltype_dir in sorted(p for p in trend_root.iterdir() if p.is_dir()):
        celltype = celltype_dir.name
        # classic: legacy flat layout, files directly in celltype_dir.
        summary_row, gene_df = _read_one_trend(run_id, celltype, "classic", celltype_dir)
        if summary_row is not None:
            summary_rows.append(summary_row)
        if gene_df is not None:
            gene_frames.append(gene_df)
        # proportion/shannon: one subdir each, named after the strategy.
        # Restricted to the known set (2026-08-14 FINDING: a scratch/backup
        # dir -- e.g. 'proportion_PRE_FIX_bak', left behind by out-of-band
        # engine-writer fix work happening directly on the analysis server
        # -- would otherwise be silently ingested as if it were a real
        # fourth strategy, since this used to iterate EVERY subdirectory
        # unconditionally. Anything not in `_KNOWN_LENGTH_TREND_SUBDIRS` is
        # skipped, not fabricated into a findings_long strategy value.
        for strategy_dir in sorted(p for p in celltype_dir.iterdir() if p.is_dir() and p.name in _KNOWN_LENGTH_TREND_SUBDIRS):
            summary_row, gene_df = _read_one_trend(run_id, celltype, strategy_dir.name, strategy_dir)
            if summary_row is not None:
                summary_rows.append(summary_row)
            if gene_df is not None:
                gene_frames.append(gene_df)
    summary_df = pd.DataFrame(summary_rows, columns=_SUMMARY_COLUMNS) if summary_rows else pd.DataFrame(columns=_SUMMARY_COLUMNS)
    gene_df = pd.concat(gene_frames, ignore_index=True) if gene_frames else pd.DataFrame(columns=_GENE_COLUMNS)
    return summary_df, gene_df


# `ema switch trend`'s own direction vocabulary (increasing/decreasing/flat,
# see length_trend_by_gene.tsv) mapped to FindingRow's Direction enum
# (lengthen/shorten/flat/undetermined) -- anything not in this map (missing,
# or a future engine value) falls back to 'undetermined', never left blank.
_LENGTH_DIRECTION_MAP = {"decreasing": "shorten", "increasing": "lengthen", "flat": "flat"}


def _switch_length_findings_df(switch_trend_gene_df: pd.DataFrame) -> pd.DataFrame:
    """Fold the length-strategy per-gene trend rows (classic/proportion/
    shannon, already parsed by `_switch_trend_dfs` into `switch_trend_gene_df`
    -- no second file read) into findings_long-shaped pseudo-findings too
    (2026-08-14) -- so classic/proportion/shannon become selectable
    `strategy` values in the Findings browse, not only via the separate
    per-celltype browsable table (ResultsCelltypeView's LengthTrendTable).
    Same "surface all strategies, let the user select" principle as
    `_switch_nb_multi_findings_df`, and the reason the Findings tab's
    strategy facet used to show fisher only even though nb_multi AND all
    three length strategies were fully computed and browsable one level
    down.

    A genuinely DIFFERENT grain than a per-PAS diff finding -- one row per
    (gene, celltype, strategy), no PAS/qvalue/pvalue concept at all
    (`ema switch trend` reports a per-gene slope/Spearman-across-stages,
    not a per-PAS significance test). Handled explicitly, not fabricated:
    * `pas_uid` stays None -- there is no PAS. Naturally excludes these
      rows from every PAS-scoped query (geneview overlay, `/pas/{id}`
      detail both filter `pas_uid IN (...)`); they stay fully visible in
      the general Findings browse and gene-scoped queries.
    * `qvalue`/`pvalue`/`n_reads`/`delta_proportion`/`n_cells` are all None
      -- no such measurement exists for a slope-across-stages call.
      `slope`/`spearman` (2026-08-14 new findings_long columns) carry the
      real numbers instead -- a differently-shaped row, not a blank one.
    * `canonical_cluster` uses the sentinel `'ALL_STAGES'` (same rationale
      as nb_multi -- spans every stage, not one pairwise pair).
    * `direction` is mapped via `_LENGTH_DIRECTION_MAP` above, never left
      blank (D8).
    * `arm` is `switch_length:<strategy>`, parallel to nb_multi's
      `switch_diff:nb_multi` -- lets a caller distinguish diff vs length
      pseudo-findings by arm prefix without checking `strategy`.
    * `strategy='proportion'` rows ARE included (science-reports: the
      engine pads uncovered pairs with 1/n_PAS, so the trend is a
      near-constant, not real biology -- see ResultsCelltypeView's
      LENGTH_STRATEGIES docstring) -- the frontend flags them invalid at
      display time, same as the length-strategy selector; the indexer's
      job is completeness, not deciding what's trustworthy.

    finding_uid uses an empty `pas_uid_value` component (no PAS exists to
    fold in) -- (celltype, gene_id, strategy) is already unique at this
    grain (one trend row per gene per celltype per strategy).

    Returns an empty DataFrame (never raises) when `switch_trend_gene_df`
    is empty.
    """
    if switch_trend_gene_df.empty:
        return pd.DataFrame()
    from peakatail_contract import ids

    df = switch_trend_gene_df.copy()
    mapped_direction = df["direction"].map(_LENGTH_DIRECTION_MAP).fillna("undetermined")
    # `ids.finding_uid`'s separator guard rejects ':' in `arm` -- mint with
    # 'switch_length_<strategy>' (underscore); the STORED `arm` column below
    # still uses 'switch_length:<strategy>' (colon), matching nb_multi's/
    # fisher's own 'switch_diff:...' display convention. See
    # _switch_nb_multi_findings_df's identical comment for why minting and
    # storage are allowed to differ here.
    df["finding_uid"] = [
        ids.finding_uid(celltype, gene_id, strategy, f"switch_length_{strategy}", "")
        for celltype, gene_id, strategy in zip(df["celltype"], df["gene_id"], df["strategy"], strict=True)
    ]
    n = len(df)
    return pd.DataFrame(
        {
            "run_id": df["run_id"],
            "finding_uid": df["finding_uid"],
            "pas_uid": [None] * n,
            "gene_id": df["gene_id"],
            "canonical_cluster": ["ALL_STAGES"] * n,
            "comparison_cluster": [None] * n,
            "celltype": df["celltype"],
            "strategy": df["strategy"],
            "arm": "switch_length:" + df["strategy"].astype(str),
            "direction": mapped_direction,
            "utr_class": [None] * n,
            "qvalue": [None] * n,
            "pvalue": [None] * n,
            "delta_proportion": [None] * n,
            "log2fc": [None] * n,
            "odds_ratio": [None] * n,
            "n_cells": [None] * n,
            "n_reads": [None] * n,
            "n_cells_subject": [None] * n,
            "n_cells_comparison": [None] * n,
            "n_reads_subject": [None] * n,
            "n_reads_comparison": [None] * n,
            "slope": df["slope"],
            "spearman": df["spearman"],
        }
    )


def _switch_availability_df(run_id: str, run_dir: Path) -> pd.DataFrame:
    """Cheap (stat-only, never reads full file contents) inventory of what
    switch-analysis results exist per celltype, for `B3_switch/length`
    (classic/proportion/shannon -- NOT fully ingested: these are per-cell x
    per-gene rows, seen up to ~112GB for a single 24-celltype cohort run, so
    even a row count would mean reading gigabytes at index time, violating
    "keep indexing fast and independent of data size") and `B3_switch/match`
    (cluster_match.tsv, run-level, no celltype). Diff availability is not
    duplicated here -- it's fully queryable from `findings_long` itself
    (`arm LIKE 'switch_diff:%'`) once `_switch_diff_findings_df` has run.

    One row per (celltype, kind, subkind) with the primary file's size in
    bytes (`os.stat`, not a read) so a "results" view can show what's
    available and roughly how big it is without ever opening the file.
    """
    switch_root = run_dir / "B3_switch"
    if not switch_root.is_dir():
        return pd.DataFrame()
    rows: list[dict] = []

    length_root = switch_root / "length"
    _length_primary = {"classic": "pdui_classic.tsv", "proportion": "proportion.tsv", "shannon": "entropy_shannon.tsv"}
    if length_root.is_dir():
        for celltype_dir in sorted(p for p in length_root.iterdir() if p.is_dir()):
            # Restricted to the known 3 strategies (2026-08-14, same finding
            # as `_KNOWN_LENGTH_TREND_SUBDIRS` above) -- a scratch/backup
            # dir here would otherwise show up as a fabricated "4th
            # strategy" file-size badge in the UI.
            for strategy_dir in sorted(
                p for p in celltype_dir.iterdir() if p.is_dir() and p.name in _length_primary
            ):
                fname = _length_primary.get(strategy_dir.name)
                fpath = (strategy_dir / fname) if fname else None
                if fpath is None or not fpath.exists():
                    candidates = sorted(strategy_dir.glob("*.tsv"))
                    fpath = candidates[0] if candidates else None
                size = fpath.stat().st_size if fpath is not None and fpath.exists() else None
                rows.append(
                    {
                        "run_id": run_id,
                        "celltype": celltype_dir.name,
                        "kind": "length",
                        "subkind": strategy_dir.name,
                        "file_path": str(fpath.relative_to(run_dir)) if fpath is not None else None,
                        "file_size_bytes": size,
                    }
                )

    match_path = switch_root / "match" / "cluster_match.tsv"
    if match_path.exists():
        rows.append(
            {
                "run_id": run_id,
                "celltype": None,
                "kind": "match",
                "subkind": None,
                "file_path": str(match_path.relative_to(run_dir)),
                "file_size_bytes": match_path.stat().st_size,
            }
        )

    return pd.DataFrame(rows)


def _length_df(run_id: str, run: Run) -> pd.DataFrame:
    rows = run.length_rows()
    return pd.DataFrame(
        [
            {
                "run_id": run_id,
                "strategy": r.strategy.value,
                "gene_id": r.gene_id,
                "transcript_id": r.transcript_id,
                "cell_uid": r.cell_uid,
                "canonical_cluster": r.canonical_cluster,
                "value": r.value,
                "pas_uid": r.pas_uid,
                "rank": r.rank,
                "direction": r.direction.value if r.direction is not None else None,
            }
            for r in rows
        ]
    )


def _umap_df_from_adata(run_id: str, dataset_id: str | None, adata: Any) -> pd.DataFrame:
    """Build one dataset's slice of `umap_points` from an already-open
    (backed) AnnData. Split out of `_umap_points_df` so it can be called once
    per dataset on a multi-dataset run (see there) as well as once for a
    single-dataset/fixture run.
    """
    obsm_key = "X_umap" if "X_umap" in adata.obsm else next(iter(adata.obsm.keys()), None)
    if obsm_key is None:
        logger.warning(
            "run_id=%s dataset_id=%s: clusters.h5ad has no obsm embedding, umap_points will be empty",
            run_id, dataset_id,
        )
        xy = None
    else:
        xy = adata.obsm[obsm_key]

    obs = adata.obs
    n = adata.n_obs

    def _obs_col(name: str) -> list[str | None]:
        if name in obs.columns:
            return [None if pd.isna(v) else str(v) for v in obs[name]]
        return [None] * n

    dataset_ids: list[str | None]
    if dataset_id is not None:
        # Real per-dataset clusters.h5ad (07_clustering/<dataset_id>/) has no
        # obs['dataset_id'] column of its own -- the caller already knows
        # which dataset this h5ad belongs to (it opened it via
        # clusters_h5ad_path(dataset_id=...)), so trust that over any
        # same-named obs column.
        dataset_ids = [dataset_id] * n
    else:
        dataset_ids = _obs_col("dataset_id")
        if all(d is None for d in dataset_ids):
            # Fall back to parsing "{dataset_id}:{barcode}" out of cell_uid.
            dataset_ids = [str(cid).split(":", 1)[0] for cid in adata.obs_names]

    return pd.DataFrame(
        {
            "run_id": [run_id] * n,
            "dataset_id": dataset_ids,
            "cell_uid": [str(c) for c in adata.obs_names],
            "x": xy[:, 0] if xy is not None else [None] * n,
            "y": xy[:, 1] if xy is not None else [None] * n,
            "leiden": _obs_col("leiden"),
            "canonical_cluster": _obs_col("canonical_cluster"),
            # Gated per spec §7c (A1/A2/B2/B7) -- always None until the
            # engine emits these obs columns on real runs.
            "celltype": _obs_col("celltype"),
            "stage": _obs_col("stage"),
            "sample": _obs_col("sample"),
        }
    )


def _umap_points_df(run_id: str, run: Run) -> pd.DataFrame:
    """The ONE place (besides gene_counts()) this indexer touches
    clusters.h5ad -- via `Run.open_clusters_h5ad()`, never scattered
    elsewhere (task brief: "the ONE place in the indexer that touches the
    heavy h5ad reader — call it explicitly, don't scatter h5ad opens
    elsewhere").

    MULTI-DATASET FIX (2026-08-13): a real cohort run (`B1_cohort_full`,
    grid/*) has NO single unified `clusters.h5ad` -- clustering runs
    per-dataset (`07_clustering/<dataset_id>/clusters.h5ad`, one per
    `manifest.datasets` entry, 6-17 on the runs seen so far). Calling
    `open_clusters_h5ad()` with no `dataset_id` on such a run hits
    `clusters_h5ad_path`'s ">1 candidate, dataset_id=None" ambiguity guard
    and raises -- which `index_run` used to catch and silently leave
    `umap_points` empty for the whole run. Fixed by iterating every
    registered dataset explicitly and opening its own h5ad
    (`open_clusters_h5ad(dataset_id=ds)`), tagging each with that
    `dataset_id`, and concatenating -- so the UMAP view gets every dataset's
    points, filterable via `?dataset_id=`. A single-dataset/fixture run
    (`manifest.datasets` empty, e.g. the packages/contract fixture) falls
    back to the original bare `open_clusters_h5ad()` call.

    Per-dataset opens are independent and best-effort: one dataset's h5ad
    being missing/unreadable is logged and skipped, not fatal to the whole
    run's UMAP coverage (matches this indexer's existing "umap indexing is
    best-effort" posture for real runs).

    GUARD (found via the contract fixture, which registers 2
    `manifest.datasets` entries but only ONE shared `clusters.h5ad`
    artifact): naively looping `manifest.datasets` and calling
    `open_clusters_h5ad(dataset_id=ds)` for each would, in that shape,
    resolve every dataset_id to the SAME single file (`clusters_h5ad_path`
    only scopes by dataset_id when there's more than one h5ad candidate to
    disambiguate between) -- duplicating every cell once per dataset entry.
    So the per-dataset loop only runs when the manifest actually registers
    MORE THAN ONE h5ad clustering artifact; otherwise this falls back to the
    single bare `open_clusters_h5ad()` open, exactly like the pre-fix
    behavior, regardless of how many datasets are listed.
    """
    from peakatail_contract.models import Format  # local import: avoids a module-load-order dependency

    h5ad_candidates = [
        a for a in run.manifest.artifacts
        if a.format == Format.H5AD and ("cluster" in a.stage.lower() or a.schema_name == "clusters.h5ad")
    ]
    dataset_ids = [d.dataset_id for d in run.manifest.datasets]
    if len(h5ad_candidates) <= 1 or not dataset_ids:
        adata = run.open_clusters_h5ad()
        return _umap_df_from_adata(run_id, None, adata)

    frames: list[pd.DataFrame] = []
    for ds in dataset_ids:
        try:
            adata = run.open_clusters_h5ad(dataset_id=ds)
        except Exception as exc:  # noqa: BLE001 -- one bad dataset must not blank the whole run's UMAP
            logger.warning("run_id=%s dataset_id=%s: clusters.h5ad open failed, skipping (%s)", run_id, ds, exc)
            continue
        frames.append(_umap_df_from_adata(run_id, ds, adata))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _insert_df(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    con.register("_tmp_df", df)
    try:
        con.execute(f"INSERT INTO {table} SELECT * FROM _tmp_df")  # noqa: S608 -- table name from fixed whitelist
    finally:
        con.unregister("_tmp_df")


def _run_headline_stats(run_dir: Path, run: "Run", n_findings: int, n_length: int) -> dict:
    """Headline run stats for the dashboard. The engine's entity_counts keys vary
    by run type (`ema run` writes ip stats only; `ema reannotate` writes
    final_*_total), so derive n_pas/n_cells/n_genes from the real artifacts and
    fall back to whatever entity_counts provides. Cheap: pasbed is a line count;
    clusters.h5ad reads are backed (metadata only)."""
    ec = run.manifest.entity_counts or {}
    n_pas = ec.get("n_pas") or ec.get("final_pas_total")
    for name in ("pasbed.bed", "annotatedpas.bed"):
        p = run_dir / name
        if p.exists():
            try:
                n_pas = sum(1 for _ in open(p)); break
            except Exception:
                pass
    n_cells = ec.get("n_cells") or ec.get("final_cells_total")
    n_genes = ec.get("n_genes")
    if n_cells is None or n_genes is None:
        try:
            import anndata as ad
            tot, nv = 0, 0
            for h in sorted((run_dir / "07_clustering").glob("*/clusters.h5ad")):
                try:
                    a = ad.read_h5ad(h, backed="r"); tot += int(a.n_obs); nv = max(nv, int(a.n_vars))
                except Exception:
                    pass
            if n_cells is None and tot:
                n_cells = tot
            if n_genes is None and nv:
                n_genes = nv
        except Exception:
            pass
    return {"n_pas": n_pas, "n_cells": n_cells, "n_genes": n_genes,
            "n_datasets": ec.get("n_datasets"), "n_findings": n_findings, "n_length_rows": n_length}


def index_run(con: duckdb.DuckDBPyConnection, run_dir: Path, source_id: str | None = None) -> str:
    """(Re)index one run directory. Returns the run_id. Raises on any
    validation or read failure -- callers (index_runs_root) are responsible
    for catching per-run so one bad run doesn't abort the whole pass.

    `source_id`, when given, tags the `runs` row with which registered
    `sources` entry (see api/sources.py) discovered this run. It has NO
    effect on the idempotency gate above (manifest_checksum +
    artifacts_fingerprint) -- an unchanged run still raises `_UnchangedRun`
    even if it's being (re)discovered under a different/new source. Callers
    that care about source attribution surviving that skip (index_source,
    below) must handle `_UnchangedRun` themselves and re-point source_id via
    `queries.touch_run_source`.
    """
    manifest_path = run_dir / "run_manifest.json"
    checksum = _manifest_checksum(manifest_path)
    manifest_json = json.loads(manifest_path.read_text())
    # NOTE (2026-07-14): engine-team's real E2 writer does not yet emit a
    # top-level `run_id` key (their message only listed contract_version/
    # timestamp/artifacts/resolved_config/id_grammar/stratum_to_label) even
    # though our frozen RunManifest schema requires one and this indexer
    # keys every DuckDB table on it. Falling back to the run directory name
    # so real engine runs can still be indexed while that's reconciled --
    # flagged back to engine-team as a required manifest addition. Remove
    # this fallback once `run_id` is always present.
    run_id = manifest_json.get("run_id") or run_dir.name
    artifacts_fp = _artifacts_fingerprint(run_dir, manifest_json)

    existing = _existing_fingerprints(con, run_id)
    if existing == (checksum, artifacts_fp):
        logger.info(
            "run_id=%s: manifest + all registered artifacts unchanged, skipping", run_id
        )
        raise _UnchangedRun(run_id)
    if existing is not None and existing[0] == checksum and existing[1] != artifacts_fp:
        logger.info(
            "run_id=%s: manifest bytes unchanged but a registered artifact's size/mtime "
            "changed -- re-indexing (this is the case manifest-checksum-only used to miss)",
            run_id,
        )

    run = Run.from_dir(run_dir)
    # NOTE (2026-07-14): engine's provenance/pas_ledger.tsv is being wired
    # incrementally (atlas-snap drop site first; cb-filter/pas-gene/
    # preprocess still pending per engine-team). Until every drop site is
    # wired, rows(pas_ledger where dropped_at="") != n_vars(clusters.h5ad)
    # by construction (D2-D7 drops aren't recorded yet), so we must NOT
    # enforce that invariant here or every real run would fail indexing.
    # Fixtures/contract-level tests keep enforcing it (default True there);
    # this is the one call site that's deliberately lenient for real runs.
    # PERF: the pas/cell provenance ledgers are the ONLY 6M-row artifacts and feed
    # only the Audit view. Reading them per-row (pydantic) is O(ledger size) and
    # dominates index time on real cohorts. Skip them by default (lazy-load per-run
    # on demand); set HUB_INDEX_LEDGERS=1 to index them + run the full validation.
    if os.environ.get("HUB_INDEX_LEDGERS", "0").lower() in ("1", "true", "yes"):
        validate_run(run, check_ledger_invariant=False)
        pas_df = _pas_ledger_df(run_id, run)
        cell_df = _cell_ledger_df(run_id, run)
    else:
        pas_df = pd.DataFrame()
        cell_df = pd.DataFrame()
    # Real-run PAS+gene source override (independent of HUB_INDEX_LEDGERS --
    # annotatedpas.bed is cheap, ~100k-200k rows read natively, not the
    # 6M-row provenance ledgers that flag gates). See `_pas_annot_df`
    # docstring: on every real run inspected, provenance/pas_ledger.tsv is
    # an empty stub (blank coordinates/gene_id) while annotatedpas.bed is
    # the real, final annotated-PAS artifact -- prefer it whenever present
    # so the PAS/Genes browsers and geneview show real data instead of an
    # empty table. Fixture/demo runs (no annotatedpas.bed) keep whatever
    # `_pas_ledger_df` produced above (or stay empty if ledgers were skipped).
    annot_df = _pas_annot_df(run_id, run_dir)
    if not annot_df.empty:
        pas_df = annot_df
    findings_df = _findings_df(run_id, run)
    switch_findings_df = _switch_diff_findings_df(run_id, run_dir)
    if not switch_findings_df.empty:
        findings_df = (
            pd.concat([findings_df, switch_findings_df], ignore_index=True)
            if not findings_df.empty
            else switch_findings_df
        )
    length_df = _length_df(run_id, run)
    try:
        umap_df = _umap_points_df(run_id, run)
    except Exception as _umap_e:  # multi-dataset runs: umap indexing is best-effort
        logger.warning("run_id=%s: umap points skipped (%s)", run_id, _umap_e)
        umap_df = pd.DataFrame()
    switch_trend_summary_df, switch_trend_gene_df = _switch_trend_dfs(run_id, run_dir)
    switch_availability_df = _switch_availability_df(run_id, run_dir)
    # pas_id -> gene_id / pas_id -> pas_uid lookups for _switch_nb_multi_df's
    # and _switch_nb_multi_findings_df's joins, built from THIS run's own
    # just-computed pas_df (same run-level unified pas_id space as
    # annotatedpas.bed/orig_pas_key -- see _pas_annot_df) -- skipped (empty
    # lookups, gene_id/pas_uid stay null) when pas_df is empty.
    _pas_df_deduped = pas_df.drop_duplicates(subset="orig_pas_key", keep="first") if not pas_df.empty else pas_df
    pas_gene_lookup = _pas_df_deduped.set_index("orig_pas_key")["gene_id"] if not pas_df.empty else pd.Series(dtype=str)
    pas_uid_lookup = _pas_df_deduped.set_index("orig_pas_key")["pas_uid"] if not pas_df.empty else pd.Series(dtype=str)
    switch_nb_multi_df = _switch_nb_multi_df(run_id, run_dir, pas_gene_lookup)
    # 2026-08-14: fold nb_multi (diff) + classic/proportion/shannon (length)
    # into findings_long too, alongside fisher above -- see
    # _switch_nb_multi_findings_df/_switch_length_findings_df's docstrings
    # for why this used to be impossible without fabricating fields, and
    # what changed (delta_proportion/n_reads went Optional on the contract;
    # slope/spearman are new findings_long columns for the length grain).
    # This is the fix for "Findings tab only ever shows fisher" -- nb_multi
    # and all three length strategies were already fully computed and
    # individually browsable, just never folded into the unified
    # strategy-filterable Findings browse.
    for extra_df in (
        _switch_nb_multi_findings_df(switch_nb_multi_df, pas_uid_lookup),
        _switch_length_findings_df(switch_trend_gene_df),
    ):
        if not extra_df.empty:
            findings_df = pd.concat([findings_df, extra_df], ignore_index=True) if not findings_df.empty else extra_df
    # Reindex to findings_long's real column order right before insert --
    # _insert_df's `INSERT INTO t SELECT * FROM df` is POSITIONAL, and the
    # four source frames above (engine fixture findings, fisher, nb_multi,
    # length) each supply a different column subset/order; this guarantees
    # the final frame matches regardless (missing columns -> NaN, never a
    # silent column-shift). See _FINDINGS_INSERT_COLUMNS's own docstring.
    if not findings_df.empty:
        findings_df = findings_df.reindex(columns=_FINDINGS_INSERT_COLUMNS)

    _stats = _run_headline_stats(run_dir, run, len(findings_df), len(length_df))
    atlas_snap_available = _atlas_snap_available(run_dir)
    con.execute("BEGIN TRANSACTION")
    try:
        _delete_run(con, run_id)
        _insert_df(con, "pas_ledger", pas_df)
        _insert_df(con, "cell_ledger", cell_df)
        _insert_df(con, "findings_long", findings_df)
        _insert_df(con, "length_long", length_df)
        _insert_df(con, "umap_points", umap_df)
        _insert_df(con, "switch_trend_summary", switch_trend_summary_df)
        _insert_df(con, "switch_trend_gene", switch_trend_gene_df)
        _insert_df(con, "switch_availability", switch_availability_df)
        _insert_df(con, "switch_nb_multi", switch_nb_multi_df)
        con.execute(
            """
            INSERT INTO runs (
                run_id, root, contract_version, manifest_checksum, artifacts_fingerprint,
                resolved_config, stratum_to_label,
                n_pas, n_cells, n_genes, n_datasets, n_findings, n_length_rows,
                source_id, atlas_snap_available, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
            """,
            [
                run_id,
                run.manifest.root,
                run.manifest.contract_version,
                checksum,
                artifacts_fp,
                json.dumps(run.manifest.resolved_config),
                json.dumps(run.manifest.stratum_to_label),
                _stats["n_pas"],
                _stats["n_cells"],
                _stats["n_genes"],
                _stats["n_datasets"],
                _stats["n_findings"],
                _stats["n_length_rows"],
                source_id,
                atlas_snap_available,
            ],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    logger.info("run_id=%s: indexed (%d pas, %d cells, %d findings)", run_id, len(pas_df), len(cell_df), len(findings_df))
    return run_id


class _UnchangedRun(Exception):
    def __init__(self, run_id: str):
        self.run_id = run_id


def index_runs_root(con: duckdb.DuckDBPyConnection, runs_root: Path) -> IndexReport:
    report = IndexReport()
    for run_dir in find_run_dirs(runs_root):
        try:
            run_id = index_run(con, run_dir)
            report.indexed.append(run_id)
        except _UnchangedRun as unchanged:
            report.skipped_unchanged.append(unchanged.run_id)
        except ContractValidationError as exc:
            logger.error("run_dir=%s: FAILED validation, skipping:\n%s", run_dir, exc)
            report.failed[str(run_dir)] = str(exc)
        except Exception as exc:  # noqa: BLE001 -- keep indexing other runs no matter what
            logger.error("run_dir=%s: FAILED to index, skipping: %s", run_dir, exc)
            report.failed[str(run_dir)] = str(exc)
    return report


def index_source(con: duckdb.DuckDBPyConnection, source_id: str, runs_root: Path) -> IndexReport:
    """Like `index_runs_root`, but every freshly-(re)indexed run's `runs`
    row is tagged with `source_id` (dashboard SOURCES manager, api/sources.py).

    Handles the case `index_runs_root`/the bare CLI never has to: a run
    under this directory that's ALREADY indexed and completely unchanged
    (e.g. registered earlier via `hub index` directly, or discovered under a
    second source pointing at a copy of the same run_id) still needs its
    `source_id` re-pointed at *this* source so "which source did this run
    come from" stays accurate -- `index_run` deliberately skips all of that
    row's other columns on an unchanged run (that's the whole idempotency
    contract, see module docstring), so this does a targeted UPDATE instead
    of forcing a full re-index just to fix one column.
    """
    from peakatail_hub.store import queries  # local import: avoid a store<->index cycle at module load

    report = IndexReport()
    for run_dir in find_run_dirs(runs_root):
        try:
            run_id = index_run(con, run_dir, source_id=source_id)
            report.indexed.append(run_id)
        except _UnchangedRun as unchanged:
            queries.touch_run_source(con, unchanged.run_id, source_id)
            report.skipped_unchanged.append(unchanged.run_id)
        except ContractValidationError as exc:
            logger.error("run_dir=%s: FAILED validation, skipping:\n%s", run_dir, exc)
            report.failed[str(run_dir)] = str(exc)
        except Exception as exc:  # noqa: BLE001 -- keep indexing other runs no matter what
            logger.error("run_dir=%s: FAILED to index, skipping: %s", run_dir, exc)
            report.failed[str(run_dir)] = str(exc)
    return report
