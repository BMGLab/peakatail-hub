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
    findings_df = _findings_df(run_id, run)
    length_df = _length_df(run_id, run)
    try:
        umap_df = _umap_points_df(run_id, run)
    except Exception as _umap_e:  # multi-dataset runs: umap indexing is best-effort
        logger.warning("run_id=%s: umap points skipped (%s)", run_id, _umap_e)
        umap_df = pd.DataFrame()

    _stats = _run_headline_stats(run_dir, run, len(findings_df), len(length_df))
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
                run_id, root, contract_version, manifest_checksum, artifacts_fingerprint,
                resolved_config, stratum_to_label,
                n_pas, n_cells, n_genes, n_datasets, n_findings, n_length_rows,
                source_id, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
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
