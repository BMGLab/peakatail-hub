"""`hub index <runs_root>` — walk a runs-root directory, validate each run,
and (re)write its rows into the DuckDB store.

Idempotency contract (task brief: "re-running `hub index` on an unchanged
run must be a fast no-op"): each indexed run's row in the `runs` table
stores `manifest_checksum`, the sha256 of the raw `run_manifest.json` bytes.
On a subsequent pass, a run whose manifest bytes are byte-identical to what
was last indexed is skipped entirely -- no reads of the ledgers/findings/
h5ad, no deletes, no inserts against any table. This is stronger than an
mtime/size check (survives copies/rsyncs that preserve content but not
mtimes) and cheaper than re-validating (a single hash of a small JSON file).
A run whose manifest changed (including "never indexed before") is fully
re-processed: its previous rows (if any) are deleted and freshly re-inserted
inside one transaction, so a partial failure never leaves stale + fresh rows
mixed for the same run_id.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
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


def find_run_dirs(runs_root: Path) -> list[Path]:
    """Every directory under `runs_root` containing a `run_manifest.json`,
    one dir per run (the manifest itself may be arbitrarily deep).
    """
    return sorted(p.parent for p in Path(runs_root).rglob("run_manifest.json"))


def _existing_checksum(con: duckdb.DuckDBPyConnection, run_id: str) -> str | None:
    row = con.execute("SELECT manifest_checksum FROM runs WHERE run_id = ?", [run_id]).fetchone()
    return row[0] if row else None


def _delete_run(con: duckdb.DuckDBPyConnection, run_id: str) -> None:
    for table in ("runs", "pas_ledger", "cell_ledger", "findings_long", "length_long", "umap_points"):
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
                "gene_distance_bp": r.gene_distance_bp,
                "tier": r.tier.value if r.tier is not None else None,
                "last_stage": r.last_stage,
                "dropped_at": r.dropped_at,
                "drop_reason": r.drop_reason,
            }
            for r in rows
        ]
    )


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


def _umap_points_df(run_id: str, run: Run) -> pd.DataFrame:
    """The ONE place (besides gene_counts()) this indexer touches
    clusters.h5ad -- via `Run.open_clusters_h5ad()`, never scattered
    elsewhere (task brief: "the ONE place in the indexer that touches the
    heavy h5ad reader — call it explicitly, don't scatter h5ad opens
    elsewhere").
    """
    adata = run.open_clusters_h5ad()
    obsm_key = "X_umap" if "X_umap" in adata.obsm else next(iter(adata.obsm.keys()), None)
    if obsm_key is None:
        logger.warning("run_id=%s: clusters.h5ad has no obsm embedding, umap_points will be empty", run_id)
        xy = None
    else:
        xy = adata.obsm[obsm_key]

    obs = adata.obs
    n = adata.n_obs

    def _obs_col(name: str) -> list[str | None]:
        if name in obs.columns:
            return [None if pd.isna(v) else str(v) for v in obs[name]]
        return [None] * n

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


def _insert_df(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    con.register("_tmp_df", df)
    try:
        con.execute(f"INSERT INTO {table} SELECT * FROM _tmp_df")  # noqa: S608 -- table name from fixed whitelist
    finally:
        con.unregister("_tmp_df")


def index_run(con: duckdb.DuckDBPyConnection, run_dir: Path) -> str:
    """(Re)index one run directory. Returns the run_id. Raises on any
    validation or read failure -- callers (index_runs_root) are responsible
    for catching per-run so one bad run doesn't abort the whole pass.
    """
    manifest_path = run_dir / "run_manifest.json"
    checksum = _manifest_checksum(manifest_path)
    manifest_json = json.loads(manifest_path.read_text())
    run_id = manifest_json["run_id"]

    existing = _existing_checksum(con, run_id)
    if existing == checksum:
        logger.info("run_id=%s: manifest unchanged (checksum match), skipping", run_id)
        raise _UnchangedRun(run_id)

    run = Run.from_dir(run_dir)
    validate_run(run)  # raises ContractValidationError on any violation

    pas_df = _pas_ledger_df(run_id, run)
    cell_df = _cell_ledger_df(run_id, run)
    findings_df = _findings_df(run_id, run)
    length_df = _length_df(run_id, run)
    umap_df = _umap_points_df(run_id, run)

    con.execute("BEGIN TRANSACTION")
    try:
        _delete_run(con, run_id)
        _insert_df(con, "pas_ledger", pas_df)
        _insert_df(con, "cell_ledger", cell_df)
        _insert_df(con, "findings_long", findings_df)
        _insert_df(con, "length_long", length_df)
        _insert_df(con, "umap_points", umap_df)
        con.execute(
            """
            INSERT INTO runs (
                run_id, root, contract_version, manifest_checksum,
                resolved_config, stratum_to_label,
                n_pas, n_cells, n_genes, n_datasets, n_findings, n_length_rows,
                indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
            """,
            [
                run_id,
                run.manifest.root,
                run.manifest.contract_version,
                checksum,
                json.dumps(run.manifest.resolved_config),
                json.dumps(run.manifest.stratum_to_label),
                run.manifest.entity_counts.get("n_pas"),
                run.manifest.entity_counts.get("n_cells"),
                run.manifest.entity_counts.get("n_genes"),
                run.manifest.entity_counts.get("n_datasets"),
                run.manifest.entity_counts.get("n_findings"),
                run.manifest.entity_counts.get("n_length_rows"),
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
