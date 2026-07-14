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


def list_runs(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    cols = [
        "run_id", "root", "contract_version", "manifest_checksum",
        "resolved_config", "stratum_to_label",
        "n_pas", "n_cells", "n_genes", "n_datasets", "n_findings", "n_length_rows",
        "indexed_at",
    ]
    rows = con.execute(f"SELECT {_select_list(cols)} FROM runs ORDER BY run_id").fetchall()  # noqa: S608
    return [dict(zip(cols, row, strict=True)) for row in rows]


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
