"""`/genes/{id}` + geneview endpoints.

`/genes/{id}/counts` is THE one heavy-import path documented in spec §7a --
it is the only router function in this whole backend that calls
`Run.gene_counts()` (which lazily imports anndata/scipy). Every other
function in this module is DuckDB-only.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from peakatail_contract import FindingRow, LengthRow
from peakatail_hub.api.deps import get_db
from peakatail_hub.io_compat import GeneNotFoundError, Run, RunReadError
from peakatail_hub.render import render_geneview_placeholder
from peakatail_hub.schemas import GeneSpan, GeneSummary, GeneviewData, GeneviewPas
from peakatail_hub.store import queries

router = APIRouter(prefix="/genes", tags=["genes"])


def _resolve_run_id(con: duckdb.DuckDBPyConnection, run_id: str | None) -> str:
    """v1 simplification (documented, not hidden): gene/PAS/cell IDs are not
    namespaced by run in the endpoint paths (spec §3 lists no `run_id` path
    param for `/genes/{id}` etc). With >1 indexed run this is ambiguous, so
    callers SHOULD pass `?run_id=`; when omitted we fall back to the single
    indexed run if there is exactly one, and fail loud (400, not a silent
    guess) otherwise.
    """
    if run_id is not None:
        return run_id
    runs = queries.list_runs(con)
    if len(runs) == 1:
        return runs[0]["run_id"]
    raise HTTPException(
        status_code=400,
        detail=(
            "run_id query param is required when more than one run is indexed "
            f"(found {len(runs)}: {[r['run_id'] for r in runs]})"
        ),
    )


@router.get("/{gene_id}", response_model=GeneSummary)
def get_gene(
    gene_id: str,
    run_id: str | None = Query(default=None),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> GeneSummary:
    rid = _resolve_run_id(con, run_id)
    summary = queries.gene_summary(con, rid, gene_id)
    span = GeneSpan(**summary["span"]) if summary["span"] else None
    return GeneSummary(**{**summary, "span": span})


@router.get("/{gene_id}/geneview-data", response_model=GeneviewData)
def geneview_data(
    gene_id: str,
    start: int | None = Query(default=None, description="Window start (bp); omit for full gene span."),
    end: int | None = Query(default=None, description="Window end (bp); omit for full gene span."),
    lod: str | None = Query(default=None, description="Level-of-detail hint; reserved, unused in v1 (tens-hundreds of PAS/gene, spec §7f)."),
    clusters: list[str] | None = Query(default=None),
    diff_strategies: list[str] | None = Query(default=None),
    length_strategies: list[str] | None = Query(default=None),
    run_id: str | None = Query(default=None),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> GeneviewData:
    """Windowed range query over pas_ledger/findings_long/length_long,
    coordinates sourced from pas_ledger (never findings_long, which per spec
    §7d and the FindingRow model has no coordinate columns at all -- there is
    no wrong path to accidentally take here).
    """
    rid = _resolve_run_id(con, run_id)
    span = queries.gene_pas_span(con, rid, gene_id)
    pas_rows = queries.geneview_pas_in_window(con, rid, gene_id, start, end)
    pas_uids = [r["pas_uid"] for r in pas_rows]
    finding_rows = queries.geneview_findings_for_pas(con, rid, pas_uids, diff_strategies)
    length_rows = queries.geneview_length_for_gene(con, rid, gene_id, length_strategies)
    if clusters:
        finding_rows = [r for r in finding_rows if r["canonical_cluster"] in clusters]
        length_rows = [r for r in length_rows if r["canonical_cluster"] in clusters]

    gates: list[str] = []
    if finding_rows and all(r["celltype"] is None for r in finding_rows):
        gates.append("celltype facet/overlay gated on engine A1 (+A2/B2) -- not present on this run yet")
    # NOTE (2026-07-14): engine now emits a real `direction` for ALL THREE
    # length strategies (classic/proportion/shannon), not just 'proportion'
    # -- see peakatail_contract.LengthRow.direction's docstring for the
    # one-vs-rest structural methodology. The gate that used to fire here
    # ("classic/shannon have no per-PAS direction yet") is stale and
    # removed; only `pas_uid`/`rank` remain proportion-only (that part of
    # the original design still holds, and needs no gate -- it's a grain
    # difference, not a missing-data one).

    return GeneviewData(
        gene_id=gene_id,
        run_id=rid,
        span=GeneSpan(**span) if span else None,
        window={"start": start, "end": end},
        pas=[GeneviewPas(**r) for r in pas_rows],
        findings=[FindingRow(**r) for r in finding_rows],
        length_rows=[LengthRow(**r) for r in length_rows],
        gates=gates,
    )


@router.get("/{gene_id}/counts")
def gene_counts(
    gene_id: str,
    run_id: str | None = Query(default=None),
    cluster: str | None = Query(default=None, description="Filter to one canonical_cluster/leiden label (forwarded to Run.gene_counts)."),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict:
    """THE one path in this backend that opens clusters.h5ad via
    `Run.gene_counts()` (lazy anndata/scipy import inside peakatail_io,
    per spec §7a). Every DuckDB-backed endpoint in this module stays
    dep-light; this is the deliberate exception.

    `peakatail_io.Run.gene_counts()` is per-var (one PAS/`var_name` at a
    time, resolved via `var_names` -- never `var['gene_id']`, spec §7d), not
    per-gene, so this endpoint resolves `gene_id` -> its surviving PAS'
    `unified_pas_id`s via the DuckDB pas_ledger first (dep-light), then
    calls `gene_counts()` once per var_name and pivots the results into one
    gene-level `{cell_uid: {pas_uid: count}}` table.
    """
    rid = _resolve_run_id(con, run_id)
    run_row = queries.get_run(con, rid)
    if run_row is None:
        raise HTTPException(status_code=404, detail=f"run_id={rid!r} not indexed")

    surviving_pas = queries.geneview_pas_in_window(con, rid, gene_id, None, None)
    if not surviving_pas:
        return {"gene_id": gene_id, "run_id": rid, "n_cells": 0, "pas_uids": [], "cells": []}

    try:
        run = Run.from_dir(Path(run_row["root"]))
    except RunReadError as exc:
        raise HTTPException(status_code=404, detail=f"counts unavailable for gene_id={gene_id!r}: {exc}") from exc

    per_cell: dict[str, dict[str, float]] = {}
    pas_uids_found: list[str] = []
    for row in surviving_pas:
        var_name = row["unified_pas_id"]
        pas_uid = row["pas_uid"]
        try:
            result = run.gene_counts(var_name, cluster=cluster)
        except GeneNotFoundError:
            # This PAS survived to the ledger but its var isn't in the
            # h5ad the manifest points at -- fail loud in logs, not to the
            # caller, since other PAS for this gene may still resolve.
            continue
        except RunReadError as exc:
            raise HTTPException(status_code=404, detail=f"counts unavailable for gene_id={gene_id!r}: {exc}") from exc
        pas_uids_found.append(pas_uid)
        for cell_uid, count in zip(result.cell_uids, result.counts, strict=True):
            per_cell.setdefault(cell_uid, {})[pas_uid] = float(count)

    return {
        "gene_id": gene_id,
        "run_id": rid,
        "n_cells": len(per_cell),
        "pas_uids": pas_uids_found,
        "cells": [{"cell_uid": cell_uid, **counts} for cell_uid, counts in per_cell.items()],
    }


def _placeholder_response(gene_id: str, media_type: str, ext: str) -> FileResponse:
    path = render_geneview_placeholder(gene_id)
    if ext == "png":
        # v1 stub only ever produces SVG (task brief: "geneview.svg/.png
        # stubs can 501/placeholder now"); serve the SVG bytes back with an
        # honest media type rather than faking a PNG.
        return FileResponse(path, media_type="image/svg+xml", filename=f"{gene_id}.svg")
    return FileResponse(path, media_type=media_type, filename=f"{gene_id}.{ext}")


@router.get("/{gene_id}/geneview.svg")
def geneview_svg(gene_id: str) -> FileResponse:
    return _placeholder_response(gene_id, "image/svg+xml", "svg")


@router.get("/{gene_id}/geneview.png")
def geneview_png(gene_id: str) -> FileResponse:
    return _placeholder_response(gene_id, "image/png", "png")
