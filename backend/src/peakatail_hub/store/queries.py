"""Parametrized DuckDB query helpers backing the API routers.

Every function takes an already-open `duckdb.DuckDBPyConnection` and plain
Python arguments; none of them know about FastAPI. Keeping this layer
separate from `api/` is what makes the "windowed reads never drop rows"
tests (`tests/test_reconcile.py`) easy to write directly against the store,
without spinning up the app.

Cursor pagination note: v1 uses a simple opaque offset cursor (base64 of a
decimal integer), not real keyset pagination. That's a legitimate "your
call" per the task brief for a DuckDB-backed table with a stable ORDER BY;
it is documented here rather than silently assumed so a future keyset
migration knows what it's replacing.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

import duckdb

#: Column names that collide with a DuckDB reserved keyword and must be
#: double-quoted when used in a SELECT list (they're already quoted
#: correctly in WHERE/GROUP BY clauses elsewhere in this module; this is
#: specifically for the `", ".join(cols)`-style SELECT projections).
_RESERVED_COLUMNS = {"end"}


def _select_list(cols: list[str]) -> str:
    return ", ".join(f'"{c}"' if c in _RESERVED_COLUMNS else c for c in cols)


# --------------------------------------------------------------------------
# Cursor helpers
# --------------------------------------------------------------------------


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    return int(base64.urlsafe_b64decode(cursor.encode()).decode())


# --------------------------------------------------------------------------
# runs
# --------------------------------------------------------------------------


_RUN_SUMMARY_COLUMNS = [
    "run_id", "root", "contract_version", "manifest_checksum",
    "resolved_config", "stratum_to_label",
    "n_pas", "n_cells", "n_genes", "n_datasets", "n_findings", "n_length_rows",
    "indexed_at", "source_id", "source_path", "source_label", "n_celltypes",
    "atlas_snap_available",
]


def list_runs(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Every indexed run, aggregated across ALL registered `sources` (a run
    indexed before the sources feature existed, or via the bare `hub index`
    CLI outside any registered source, has `source_id`/`source_path`/
    `source_label` = NULL -- that's a legitimate state, not an error).
    `n_celltypes` is a cheap correlated subquery (distinct non-null celltype
    values in findings_long for that run) -- the dashboard's per-run cards
    want it and there's no other aggregate endpoint that already carries it.
    """
    sql = """
        SELECT
            r.run_id, r.root, r.contract_version, r.manifest_checksum,
            r.resolved_config, r.stratum_to_label,
            r.n_pas, r.n_cells, r.n_genes, r.n_datasets, r.n_findings, r.n_length_rows,
            r.indexed_at, r.source_id, s.path AS source_path, s.label AS source_label,
            (
                SELECT count(DISTINCT f.celltype)
                FROM findings_long f
                WHERE f.run_id = r.run_id AND f.celltype IS NOT NULL AND f.celltype != ''
            ) AS n_celltypes,
            r.atlas_snap_available
        FROM runs r
        LEFT JOIN sources s ON r.source_id = s.source_id
        ORDER BY r.run_id
    """
    rows = con.execute(sql).fetchall()
    return [dict(zip(_RUN_SUMMARY_COLUMNS, row, strict=True)) for row in rows]


def get_run(con: duckdb.DuckDBPyConnection, run_id: str) -> dict[str, Any] | None:
    runs = [r for r in list_runs(con) if r["run_id"] == run_id]
    return runs[0] if runs else None


# --------------------------------------------------------------------------
# findings
# --------------------------------------------------------------------------

FINDING_COLUMNS = [
    "finding_uid", "pas_uid", "gene_id", "canonical_cluster", "comparison_cluster",
    "celltype", "strategy", "arm", "direction", "utr_class",
    "qvalue", "pvalue", "delta_proportion", "log2fc", "odds_ratio",
    "n_cells", "n_reads", "n_cells_subject", "n_cells_comparison",
    "n_reads_subject", "n_reads_comparison",
]


@dataclass
class FindingsFilter:
    run_id: str | None = None
    arm: str | None = None
    strategy: str | None = None
    celltype: str | None = None
    direction: str | None = None
    utr_class: str | None = None
    q_max: float | None = None
    min_reads: int | None = None
    gene_id: str | None = None

    def where(self) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if self.run_id is not None:
            clauses.append("run_id = ?")
            params.append(self.run_id)
        if self.arm is not None:
            clauses.append("arm = ?")
            params.append(self.arm)
        if self.strategy is not None:
            clauses.append("strategy = ?")
            params.append(self.strategy)
        if self.celltype is not None:
            clauses.append("celltype = ?")
            params.append(self.celltype)
        if self.direction is not None:
            clauses.append("direction = ?")
            params.append(self.direction)
        if self.utr_class is not None:
            clauses.append("utr_class = ?")
            params.append(self.utr_class)
        if self.q_max is not None:
            clauses.append("qvalue <= ?")
            params.append(self.q_max)
        if self.min_reads is not None:
            clauses.append("n_reads >= ?")
            params.append(self.min_reads)
        if self.gene_id is not None:
            clauses.append("gene_id = ?")
            params.append(self.gene_id)
        sql = " AND ".join(clauses) if clauses else "1=1"
        return sql, params


def count_findings(con: duckdb.DuckDBPyConnection, flt: FindingsFilter) -> int:
    where_sql, params = flt.where()
    return con.execute(f"SELECT count(*) FROM findings_long WHERE {where_sql}", params).fetchone()[0]  # noqa: S608


def query_findings(
    con: duckdb.DuckDBPyConnection,
    flt: FindingsFilter,
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    where_sql, params = flt.where()
    sql = (
        f"SELECT {_select_list(FINDING_COLUMNS)} FROM findings_long "  # noqa: S608
        f"WHERE {where_sql} ORDER BY finding_uid LIMIT ? OFFSET ?"
    )
    rows = con.execute(sql, [*params, limit, offset]).fetchall()
    return [dict(zip(FINDING_COLUMNS, row, strict=True)) for row in rows]


def get_finding(con: duckdb.DuckDBPyConnection, finding_uid: str) -> dict[str, Any] | None:
    sql = f"SELECT {_select_list(FINDING_COLUMNS)} FROM findings_long WHERE finding_uid = ?"  # noqa: S608
    row = con.execute(sql, [finding_uid]).fetchone()
    return dict(zip(FINDING_COLUMNS, row, strict=True)) if row else None


def findings_facets(con: duckdb.DuckDBPyConnection, flt: FindingsFilter) -> dict[str, list[dict[str, Any]]]:
    """True facet counts over the FULL filtered result set (all rows matching
    every currently-applied filter), never just the current page -- this is
    the "not counts of the current page" requirement from spec §3.
    """
    where_sql, params = flt.where()
    facets: dict[str, list[dict[str, Any]]] = {}
    for dim in ("arm", "strategy", "celltype", "direction", "utr_class"):
        sql = (
            f"SELECT {dim} AS value, count(*) AS n FROM findings_long "  # noqa: S608
            f"WHERE {where_sql} GROUP BY {dim} ORDER BY n DESC"
        )
        rows = con.execute(sql, params).fetchall()
        facets[dim] = [{"value": v, "count": n} for v, n in rows]
    return facets


# --------------------------------------------------------------------------
# genes / geneview
# --------------------------------------------------------------------------


def gene_pas_span(con: duckdb.DuckDBPyConnection, run_id: str, gene_id: str) -> dict[str, Any] | None:
    """Gene's coordinate span, sourced from pas_ledger (never from
    findings_long, which has no coordinate columns by design -- spec §7d).
    """
    row = con.execute(
        """
        SELECT chrom, min(start) AS start, max("end") AS end, any_value(strand) AS strand, count(*) AS n_pas
        FROM pas_ledger
        WHERE run_id = ? AND gene_id = ? AND dropped_at = ''
        GROUP BY chrom
        """,
        [run_id, gene_id],
    ).fetchone()
    if row is None:
        return None
    cols = ["chrom", "start", "end", "strand", "n_pas"]
    return dict(zip(cols, row, strict=True))


def geneview_pas_in_window(
    con: duckdb.DuckDBPyConnection, run_id: str, gene_id: str, start: int | None, end: int | None
) -> list[dict[str, Any]]:
    cols = [
        "pas_uid", "chrom", "start", "end", "strand", "unified_pas_id",
        "gene_distance_bp", "snap_distance_bp", "tier", "dropped_at",
    ]
    clauses = ["run_id = ?", "gene_id = ?", "dropped_at = ''"]
    params: list[Any] = [run_id, gene_id]
    if start is not None:
        clauses.append('"end" >= ?')
        params.append(start)
    if end is not None:
        clauses.append('"end" <= ?')
        params.append(end)
    sql = f"SELECT {_select_list(cols)} FROM pas_ledger WHERE {' AND '.join(clauses)} ORDER BY \"end\""  # noqa: S608
    rows = con.execute(sql, params).fetchall()
    return [dict(zip(cols, row, strict=True)) for row in rows]


def geneview_findings_for_pas(
    con: duckdb.DuckDBPyConnection, run_id: str, pas_uids: list[str], strategies: list[str] | None
) -> list[dict[str, Any]]:
    if not pas_uids:
        return []
    placeholders = ", ".join("?" for _ in pas_uids)
    clauses = ["run_id = ?", f"pas_uid IN ({placeholders})"]
    params: list[Any] = [run_id, *pas_uids]
    if strategies:
        strat_ph = ", ".join("?" for _ in strategies)
        clauses.append(f"strategy IN ({strat_ph})")
        params.extend(strategies)
    sql = f"SELECT {_select_list(FINDING_COLUMNS)} FROM findings_long WHERE {' AND '.join(clauses)}"  # noqa: S608
    rows = con.execute(sql, params).fetchall()
    return [dict(zip(FINDING_COLUMNS, row, strict=True)) for row in rows]


def geneview_length_for_gene(
    con: duckdb.DuckDBPyConnection, run_id: str, gene_id: str, strategies: list[str] | None
) -> list[dict[str, Any]]:
    cols = ["strategy", "gene_id", "transcript_id", "cell_uid", "canonical_cluster", "value", "pas_uid", "rank", "direction"]
    clauses = ["run_id = ?", "gene_id = ?"]
    params: list[Any] = [run_id, gene_id]
    if strategies:
        strat_ph = ", ".join("?" for _ in strategies)
        clauses.append(f"strategy IN ({strat_ph})")
        params.extend(strategies)
    sql = f"SELECT {_select_list(cols)} FROM length_long WHERE {' AND '.join(clauses)}"  # noqa: S608
    rows = con.execute(sql, params).fetchall()
    return [dict(zip(cols, row, strict=True)) for row in rows]


def count_genes(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    q: str | None = None,
    chrom: str | None = None,
    start: int | None = None,
    end: int | None = None,
) -> int:
    clauses = ["run_id = ?", "dropped_at = ''", "gene_id != ''"]
    params: list[Any] = [run_id]
    if q:
        clauses.append("gene_id ILIKE ?")
        params.append(f"%{q}%")
    if chrom is not None:
        clauses.append("chrom = ?")
        params.append(chrom)
    if start is not None:
        clauses.append('"end" >= ?')
        params.append(start)
    if end is not None:
        clauses.append("start <= ?")
        params.append(end)
    sql = f"SELECT count(DISTINCT gene_id) FROM pas_ledger WHERE {' AND '.join(clauses)}"  # noqa: S608
    return con.execute(sql, params).fetchone()[0]


def list_genes(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    q: str | None = None,
    chrom: str | None = None,
    start: int | None = None,
    end: int | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Browse listing: one row per gene, aggregated from surviving PAS in
    `pas_ledger` (never `findings_long`, which has no coordinate columns --
    same rationale as `gene_pas_span`). `chrom`/`start`/`end` (all optional,
    all-or-nothing not required) do a locus-overlap filter so the TopBar's
    "jump to chr:coords" search can resolve a raw genomic interval to the
    gene(s) it falls inside, the same way it resolves a symbol/ENSG id.
    """
    clauses = ["run_id = ?", "dropped_at = ''", "gene_id != ''"]
    params: list[Any] = [run_id]
    if q:
        clauses.append("gene_id ILIKE ?")
        params.append(f"%{q}%")
    if chrom is not None:
        clauses.append("chrom = ?")
        params.append(chrom)
    if start is not None:
        clauses.append('"end" >= ?')
        params.append(start)
    if end is not None:
        clauses.append("start <= ?")
        params.append(end)
    where = " AND ".join(clauses)
    sql = (
        "SELECT gene_id, any_value(chrom) AS chrom, min(start) AS start, "  # noqa: S608
        'max("end") AS "end", any_value(strand) AS strand, count(*) AS n_pas '
        f"FROM pas_ledger WHERE {where} "
        "GROUP BY gene_id ORDER BY gene_id LIMIT ? OFFSET ?"
    )
    rows = con.execute(sql, [*params, limit, offset]).fetchall()
    cols = ["gene_id", "chrom", "start", "end", "strand", "n_pas"]
    genes = [dict(zip(cols, row, strict=True)) for row in rows]
    if not genes:
        return genes
    # n_findings per gene, one extra query scoped to just this page's gene_ids
    # (mirrors the geneview_findings_for_pas page-scoped join pattern above)
    # rather than a per-row correlated subquery.
    gene_ids = [g["gene_id"] for g in genes]
    placeholders = ", ".join("?" for _ in gene_ids)
    finding_counts = dict(
        con.execute(
            f"SELECT gene_id, count(*) FROM findings_long WHERE run_id = ? AND gene_id IN ({placeholders}) "  # noqa: S608
            "GROUP BY gene_id",
            [run_id, *gene_ids],
        ).fetchall()
    )
    for g in genes:
        g["n_findings"] = finding_counts.get(g["gene_id"], 0)
    return genes


def gene_summary(con: duckdb.DuckDBPyConnection, run_id: str, gene_id: str) -> dict[str, Any]:
    n_pas = con.execute(
        "SELECT count(*) FROM pas_ledger WHERE run_id = ? AND gene_id = ? AND dropped_at = ''", [run_id, gene_id]
    ).fetchone()[0]
    n_findings = con.execute(
        "SELECT count(*) FROM findings_long WHERE run_id = ? AND gene_id = ?", [run_id, gene_id]
    ).fetchone()[0]
    n_length_rows = con.execute(
        "SELECT count(*) FROM length_long WHERE run_id = ? AND gene_id = ?", [run_id, gene_id]
    ).fetchone()[0]
    span = gene_pas_span(con, run_id, gene_id)
    return {
        "gene_id": gene_id,
        "run_id": run_id,
        "n_pas": n_pas,
        "n_findings": n_findings,
        "n_length_rows": n_length_rows,
        "span": span,
    }


# --------------------------------------------------------------------------
# pas / cells / provenance
# --------------------------------------------------------------------------

PAS_COLUMNS = [
    "pas_uid", "orig_pas_key", "chrom", "start", "end", "strand", "unified_pas_id",
    "snap_distance_bp", "gene_id", "gene_distance_bp", "tier", "last_stage",
    "dropped_at", "drop_reason",
]

CELL_COLUMNS = [
    "cell_uid", "barcode", "dataset_id", "total_reads", "n_pas", "dropped_at", "drop_reason", "cluster",
]


def get_pas(con: duckdb.DuckDBPyConnection, pas_uid: str) -> dict[str, Any] | None:
    sql = f"SELECT {_select_list(PAS_COLUMNS)} FROM pas_ledger WHERE pas_uid = ?"  # noqa: S608
    row = con.execute(sql, [pas_uid]).fetchone()
    return dict(zip(PAS_COLUMNS, row, strict=True)) if row else None


def _pas_list_where(run_id: str, q: str | None) -> tuple[str, list[Any]]:
    clauses = ["run_id = ?"]
    params: list[Any] = [run_id]
    if q:
        clauses.append("(pas_uid ILIKE ? OR gene_id ILIKE ? OR unified_pas_id ILIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    return " AND ".join(clauses), params


def count_pas(con: duckdb.DuckDBPyConnection, run_id: str, q: str | None = None) -> int:
    where_sql, params = _pas_list_where(run_id, q)
    return con.execute(f"SELECT count(*) FROM pas_ledger WHERE {where_sql}", params).fetchone()[0]  # noqa: S608


def list_pas(
    con: duckdb.DuckDBPyConnection, run_id: str, q: str | None = None, offset: int = 0, limit: int = 50
) -> list[dict[str, Any]]:
    """Browse listing over the full PAS ledger (survived + dropped alike --
    unlike `geneview_pas_in_window`, this is a provenance browser, not a
    render feed, so dropped rows stay visible with their `dropped_at`/
    `drop_reason` rather than being filtered out).
    """
    where_sql, params = _pas_list_where(run_id, q)
    sql = (
        f"SELECT {_select_list(PAS_COLUMNS)} FROM pas_ledger "  # noqa: S608
        f"WHERE {where_sql} ORDER BY pas_uid LIMIT ? OFFSET ?"
    )
    rows = con.execute(sql, [*params, limit, offset]).fetchall()
    return [dict(zip(PAS_COLUMNS, row, strict=True)) for row in rows]


def pas_provenance(con: duckdb.DuckDBPyConnection, pas_uid: str) -> dict[str, Any] | None:
    pas = get_pas(con, pas_uid)
    if pas is None:
        return None
    findings = con.execute(
        f"SELECT {_select_list(FINDING_COLUMNS)} FROM findings_long WHERE pas_uid = ?", [pas_uid]  # noqa: S608
    ).fetchall()
    length = con.execute(
        "SELECT strategy, gene_id, cell_uid, canonical_cluster, value, rank, direction "
        "FROM length_long WHERE pas_uid = ?",
        [pas_uid],
    ).fetchall()
    return {
        "pas": pas,
        "findings": [dict(zip(FINDING_COLUMNS, row, strict=True)) for row in findings],
        "length_rows": [
            dict(zip(["strategy", "gene_id", "cell_uid", "canonical_cluster", "value", "rank", "direction"], row, strict=True))
            for row in length
        ],
        "trail": _pas_trail(pas),
    }


def _pas_trail(pas: dict[str, Any]) -> list[str]:
    """Human-readable "entered -> survived thresholds -> dropped where/why"
    trail (Data Controller Design §4d "Provenance / audit view").
    """
    steps = [f"entered as orig_pas_key={pas['orig_pas_key']!r} (last alive stage={pas['last_stage']!r})"]
    if pas["snap_distance_bp"] is not None:
        steps.append(f"atlas-snapped, snap_distance_bp={pas['snap_distance_bp']}")
    if pas["gene_id"]:
        steps.append(f"assigned gene_id={pas['gene_id']!r} at gene_distance_bp={pas['gene_distance_bp']} (tier={pas['tier']})")
    if pas["dropped_at"]:
        steps.append(f"DROPPED at stage={pas['dropped_at']!r}: {pas['drop_reason']}")
    else:
        steps.append("SURVIVED to clusters.h5ad")
    return steps


def get_cell(con: duckdb.DuckDBPyConnection, cell_uid: str) -> dict[str, Any] | None:
    sql = f"SELECT {_select_list(CELL_COLUMNS)} FROM cell_ledger WHERE cell_uid = ?"  # noqa: S608
    row = con.execute(sql, [cell_uid]).fetchone()
    return dict(zip(CELL_COLUMNS, row, strict=True)) if row else None


def _cell_list_where(run_id: str, q: str | None) -> tuple[str, list[Any]]:
    clauses = ["run_id = ?"]
    params: list[Any] = [run_id]
    if q:
        clauses.append("(barcode ILIKE ? OR cell_uid ILIKE ? OR cluster ILIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    return " AND ".join(clauses), params


def count_cells(con: duckdb.DuckDBPyConnection, run_id: str, q: str | None = None) -> int:
    where_sql, params = _cell_list_where(run_id, q)
    return con.execute(f"SELECT count(*) FROM cell_ledger WHERE {where_sql}", params).fetchone()[0]  # noqa: S608


def list_cells(
    con: duckdb.DuckDBPyConnection, run_id: str, q: str | None = None, offset: int = 0, limit: int = 50
) -> list[dict[str, Any]]:
    """Browse listing over the full cell ledger (survived + dropped alike,
    same rationale as `list_pas`)."""
    where_sql, params = _cell_list_where(run_id, q)
    sql = (
        f"SELECT {_select_list(CELL_COLUMNS)} FROM cell_ledger "  # noqa: S608
        f"WHERE {where_sql} ORDER BY cell_uid LIMIT ? OFFSET ?"
    )
    rows = con.execute(sql, [*params, limit, offset]).fetchall()
    return [dict(zip(CELL_COLUMNS, row, strict=True)) for row in rows]


def cell_provenance(con: duckdb.DuckDBPyConnection, cell_uid: str) -> dict[str, Any] | None:
    cell = get_cell(con, cell_uid)
    if cell is None:
        return None
    length = con.execute(
        "SELECT strategy, gene_id, canonical_cluster, value, pas_uid, rank, direction "
        "FROM length_long WHERE cell_uid = ?",
        [cell_uid],
    ).fetchall()
    trail = [f"entered dataset_id={cell['dataset_id']!r} barcode={cell['barcode']!r}, total_reads={cell['total_reads']}"]
    if cell["dropped_at"]:
        trail.append(f"DROPPED at stage={cell['dropped_at']!r}: {cell['drop_reason']}")
    else:
        trail.append(f"SURVIVED to clusters.h5ad, cluster={cell['cluster']!r}")
    return {
        "cell": cell,
        "length_rows": [
            dict(zip(["strategy", "gene_id", "canonical_cluster", "value", "pas_uid", "rank", "direction"], row, strict=True))
            for row in length
        ],
        "trail": trail,
    }


# --------------------------------------------------------------------------
# qc funnel
# --------------------------------------------------------------------------

#: The 7 drop points from Data Controller Design §2 (D1-D7), in pipeline order.
QC_STAGES = [
    "atlas_snap", "coord_merge", "matrix_concat", "cb_filter",
    "pas_gene_assignment", "preprocess", "marker_subset",
]


def qc_funnel(con: duckdb.DuckDBPyConnection, run_id: str) -> dict[str, Any]:
    pas_total = con.execute("SELECT count(*) FROM pas_ledger WHERE run_id = ?", [run_id]).fetchone()[0]
    pas_survived = con.execute(
        "SELECT count(*) FROM pas_ledger WHERE run_id = ? AND dropped_at = ''", [run_id]
    ).fetchone()[0]
    cell_total = con.execute("SELECT count(*) FROM cell_ledger WHERE run_id = ?", [run_id]).fetchone()[0]
    cell_survived = con.execute(
        "SELECT count(*) FROM cell_ledger WHERE run_id = ? AND dropped_at = ''", [run_id]
    ).fetchone()[0]

    pas_by_stage = dict(
        con.execute(
            "SELECT dropped_at, count(*) FROM pas_ledger WHERE run_id = ? AND dropped_at != '' GROUP BY dropped_at",
            [run_id],
        ).fetchall()
    )
    cell_by_stage = dict(
        con.execute(
            "SELECT dropped_at, count(*) FROM cell_ledger WHERE run_id = ? AND dropped_at != '' GROUP BY dropped_at",
            [run_id],
        ).fetchall()
    )

    return {
        "run_id": run_id,
        "n_pas_total": pas_total,
        "n_pas_survived": pas_survived,
        "n_cells_total": cell_total,
        "n_cells_survived": cell_survived,
        "pas_drop_by_stage": [{"stage": s, "dropped": pas_by_stage.get(s, 0)} for s in QC_STAGES],
        "cell_drop_by_stage": [{"stage": s, "dropped": cell_by_stage.get(s, 0)} for s in QC_STAGES],
        "per_sample_stats_available": False,
        "gate_note": (
            "Per-dataset/per-sample stage-entry counts require engine B5 (+E3); "
            "this funnel shows run-aggregate ledger dropped_at counts only. "
            "Stages with 0 here may mean 'nothing dropped' OR 'not yet "
            "instrumented at this stage' -- the ledger cannot currently "
            "distinguish those (see Data Controller Design §2 columns "
            "'Dropped set kept?'/'Reason kept?' = NO for several stages)."
        ),
    }


# --------------------------------------------------------------------------
# umap
# --------------------------------------------------------------------------

UMAP_COLUMNS = ["cell_uid", "dataset_id", "x", "y", "leiden", "canonical_cluster", "celltype", "stage", "sample"]


def umap_points(con: duckdb.DuckDBPyConnection, run_id: str) -> list[dict[str, Any]]:
    sql = f"SELECT {_select_list(UMAP_COLUMNS)} FROM umap_points WHERE run_id = ?"  # noqa: S608
    rows = con.execute(sql, [run_id]).fetchall()
    return [dict(zip(UMAP_COLUMNS, row, strict=True)) for row in rows]


def umap_color_available(con: duckdb.DuckDBPyConnection, run_id: str, color: str) -> bool:
    if color == "leiden":
        return True
    if color not in ("celltype", "stage", "sample"):
        return False
    n = con.execute(
        f"SELECT count(*) FROM umap_points WHERE run_id = ? AND {color} IS NOT NULL",  # noqa: S608
        [run_id],
    ).fetchone()[0]
    return n > 0


# --------------------------------------------------------------------------
# run -> datasets -> results (2026-08-13 multi-dataset fix, task brief item 4)
#
# A run truthfully has MULTIPLE results: one clustering per dataset
# (umap_points, now indexed per-dataset -- see index/indexer.py::_umap_points_df)
# and, for cohort runs, a B3_switch analysis per celltype (diff/length/trend).
# This section answers "what datasets/results does run X actually have" from
# what's really indexed, rather than assuming a single-dataset/single-result
# shape.
# --------------------------------------------------------------------------


def list_run_datasets(con: duckdb.DuckDBPyConnection, run_id: str) -> list[dict[str, Any]]:
    """Every dataset with indexed UMAP points for this run, with a cheap
    per-dataset cell count and cluster count. `umap_points.dataset_id` is
    the only per-dataset-reliable column indexed today (cell_ledger is
    gated behind HUB_INDEX_LEDGERS and mostly skipped for real runs) --
    this is deliberately sourced from there, not `runs.n_datasets` (a
    single aggregate count with no per-dataset identity).
    """
    rows = con.execute(
        """
        SELECT dataset_id, count(*) AS n_cells, count(DISTINCT leiden) AS n_clusters
        FROM umap_points
        WHERE run_id = ? AND dataset_id IS NOT NULL
        GROUP BY dataset_id
        ORDER BY dataset_id
        """,
        [run_id],
    ).fetchall()
    return [{"dataset_id": r[0], "n_cells": r[1], "n_clusters": r[2]} for r in rows]


def switch_summary(con: duckdb.DuckDBPyConnection, run_id: str) -> dict[str, Any]:
    """Per-celltype rollup of every B3_switch result kind this run has:
    diff (queried live from findings_long, tagged `arm LIKE 'switch_diff:%'`
    by `_switch_diff_findings_df`), length (stat-only availability, see
    `switch_availability` table docstring for why row counts aren't
    ingested), and trend (the fully-ingested length-trend-across-stages
    headline). One dict per celltype seen in ANY of the three sources, so a
    celltype with e.g. only a trend result (no diff finding survived
    thresholds) still shows up rather than being silently dropped.
    """
    diff_rows = con.execute(
        """
        SELECT celltype, strategy, count(*) AS n
        FROM findings_long
        WHERE run_id = ? AND arm LIKE 'switch_diff:%' AND celltype IS NOT NULL
        GROUP BY celltype, strategy
        """,
        [run_id],
    ).fetchall()
    trend_rows = con.execute(
        "SELECT celltype, n_stages, slope, spearman, direction, value_col, mean_by_stage "
        "FROM switch_trend_summary WHERE run_id = ?",
        [run_id],
    ).fetchall()
    length_rows = con.execute(
        "SELECT celltype, subkind, file_size_bytes FROM switch_availability "
        "WHERE run_id = ? AND kind = 'length'",
        [run_id],
    ).fetchall()
    match_row = con.execute(
        "SELECT file_path, file_size_bytes FROM switch_availability WHERE run_id = ? AND kind = 'match'",
        [run_id],
    ).fetchone()

    by_celltype: dict[str, dict[str, Any]] = {}

    def _entry(celltype: str) -> dict[str, Any]:
        return by_celltype.setdefault(
            celltype, {"celltype": celltype, "diff": {}, "length": {}, "trend": None}
        )

    for celltype, strategy, n in diff_rows:
        _entry(celltype)["diff"][strategy] = n
    for celltype, subkind, size in length_rows:
        _entry(celltype)["length"][subkind] = {"file_size_bytes": size}
    for celltype, n_stages, slope, spearman, direction, value_col, mean_by_stage in trend_rows:
        _entry(celltype)["trend"] = {
            "n_stages": n_stages,
            "slope": slope,
            "spearman": spearman,
            "direction": direction,
            "value_col": value_col,
            "mean_by_stage": json.loads(mean_by_stage) if mean_by_stage else {},
        }

    return {
        "run_id": run_id,
        "celltypes": sorted(by_celltype.values(), key=lambda c: c["celltype"]),
        "cluster_match": {"file_path": match_row[0], "file_size_bytes": match_row[1]} if match_row else None,
    }


def switch_trend_top_genes(
    con: duckdb.DuckDBPyConnection, run_id: str, celltype: str, limit: int = 50
) -> list[dict[str, Any]]:
    """Top genes by |slope| for one celltype's length-trend-across-stages --
    the per-gene drill-down behind the run-level `switch_summary` headline.
    """
    rows = con.execute(
        """
        SELECT gene_id, n_stages, slope, spearman, direction
        FROM switch_trend_gene
        WHERE run_id = ? AND celltype = ?
        ORDER BY abs(slope) DESC NULLS LAST
        LIMIT ?
        """,
        [run_id, celltype, limit],
    ).fetchall()
    cols = ["gene_id", "n_stages", "slope", "spearman", "direction"]
    return [dict(zip(cols, row, strict=True)) for row in rows]


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------


def search(con: duckdb.DuckDBPyConnection, q: str, limit: int = 25) -> dict[str, list[dict[str, Any]]]:
    like = f"%{q}%"
    genes = con.execute(
        "SELECT DISTINCT gene_id FROM pas_ledger WHERE gene_id ILIKE ? AND gene_id != '' LIMIT ?",
        [like, limit],
    ).fetchall()
    pas = con.execute(
        f"SELECT {_select_list(PAS_COLUMNS)} FROM pas_ledger WHERE pas_uid ILIKE ? LIMIT ?",  # noqa: S608
        [like, limit],
    ).fetchall()
    cells = con.execute(
        f"SELECT {_select_list(CELL_COLUMNS)} FROM cell_ledger WHERE barcode ILIKE ? OR cell_uid ILIKE ? LIMIT ?",  # noqa: S608
        [like, like, limit],
    ).fetchall()
    return {
        "genes": [{"gene_id": g[0]} for g in genes],
        "pas": [dict(zip(PAS_COLUMNS, row, strict=True)) for row in pas],
        "cells": [dict(zip(CELL_COLUMNS, row, strict=True)) for row in cells],
    }


# --------------------------------------------------------------------------
# concordance / benchmarks (stubs -- no engine artifact defines these yet)
# --------------------------------------------------------------------------


def concordance_stub(run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "available": False,
        "note": "No concordance (ARI/AMI) artifact schema exists in peakatail-contract yet; nothing to read.",
    }


def benchmarks_stub(run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "available": False,
        "note": "No benchmark artifact schema exists in peakatail-contract yet; nothing to read.",
    }


# --------------------------------------------------------------------------
# sources (multi-directory SOURCES manager -- dashboard feature)
# --------------------------------------------------------------------------

SOURCE_COLUMNS = ["source_id", "path", "label", "added_at", "last_scanned_at", "last_scan_status", "last_scan_error"]


def list_sources(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Every registered source, with a live per-source run count (a
    correlated subquery against `runs.source_id`, not a stored counter --
    always in sync with whatever `index_source` last wrote, including runs
    that moved to a different source on rescan).
    """
    sql = f"""
        SELECT {_select_list(SOURCE_COLUMNS)},
            (SELECT count(*) FROM runs r WHERE r.source_id = sources.source_id) AS run_count
        FROM sources
        ORDER BY added_at
    """  # noqa: S608
    rows = con.execute(sql).fetchall()
    cols = [*SOURCE_COLUMNS, "run_count"]
    return [dict(zip(cols, row, strict=True)) for row in rows]


def get_source(con: duckdb.DuckDBPyConnection, source_id: str) -> dict[str, Any] | None:
    matches = [s for s in list_sources(con) if s["source_id"] == source_id]
    return matches[0] if matches else None


def get_source_by_path(con: duckdb.DuckDBPyConnection, path: str) -> dict[str, Any] | None:
    row = con.execute(f"SELECT {_select_list(SOURCE_COLUMNS)} FROM sources WHERE path = ?", [path]).fetchone()  # noqa: S608
    return dict(zip(SOURCE_COLUMNS, row, strict=True)) if row else None


def insert_source(con: duckdb.DuckDBPyConnection, source_id: str, path: str, label: str | None) -> None:
    con.execute(
        "INSERT INTO sources (source_id, path, label, added_at, last_scanned_at, last_scan_status, last_scan_error) "
        "VALUES (?, ?, ?, now(), NULL, NULL, NULL)",
        [source_id, path, label],
    )


def update_source_scan_result(
    con: duckdb.DuckDBPyConnection, source_id: str, status: str, error: str | None
) -> None:
    con.execute(
        "UPDATE sources SET last_scanned_at = now(), last_scan_status = ?, last_scan_error = ? WHERE source_id = ?",
        [status, error, source_id],
    )


def touch_run_source(con: duckdb.DuckDBPyConnection, run_id: str, source_id: str) -> None:
    """Re-point an already-indexed (unchanged, so not re-inserted) run at
    the source that just (re)discovered it. See index/indexer.py::index_source.
    """
    con.execute("UPDATE runs SET source_id = ? WHERE run_id = ?", [source_id, run_id])


_CHILD_TABLES = (
    "pas_ledger", "cell_ledger", "findings_long", "length_long", "umap_points",
    "switch_trend_summary", "switch_trend_gene", "switch_availability",
)


def delete_source_cascade(con: duckdb.DuckDBPyConnection, source_id: str) -> list[str]:
    """Remove a registered source AND every run it owns (runs.source_id =
    source_id), including their ledger/findings/length/umap rows -- a run
    that's no longer discoverable under any registered directory shouldn't
    keep cluttering the dashboard as an orphan pointing at a deleted source.
    Returns the list of removed run_ids.
    """
    run_ids = [r[0] for r in con.execute("SELECT run_id FROM runs WHERE source_id = ?", [source_id]).fetchall()]
    con.execute("BEGIN TRANSACTION")
    try:
        for run_id in run_ids:
            for table in ("runs", *_CHILD_TABLES):
                con.execute(f"DELETE FROM {table} WHERE run_id = ?", [run_id])  # noqa: S608 -- fixed whitelist above
        con.execute("DELETE FROM sources WHERE source_id = ?", [source_id])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return run_ids
