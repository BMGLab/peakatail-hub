"""`/genes/{gene_id}/geneview.{html,png}` + `/geneview/meta` -- the REAL
`ema switch geneview` output (interactive plotly / static matplotlib),
generated on demand via the host-side worker and served straight through.

Replaces the old hand-rolled IGV-style track (`GeneviewData`'s custom
`pas`/`isoforms`/`cluster_tracks` fields, rendered by a bespoke canvas
component on the frontend) entirely -- see the 2026-08-14 fix. This module
does NOT reimplement any part of what ema draws; it only resolves a run_id
to a run, asks the geneview worker to (re)generate the figure if needed, and
serves whatever file it produced.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from peakatail_hub.api.deps import get_db
from peakatail_hub.geneview import GeneviewWorkerError, container_run_dir, request_geneview
from peakatail_hub.schemas import GeneviewPasDistanceRow, GeneviewRender
from peakatail_hub.store import queries

router = APIRouter(prefix="/genes", tags=["geneview"])

_DISTANCE_INT_COLS = {"rank", "start", "end", "width_bp", "summit_pos", "gap_to_next_bp", "summit_dist_to_next_bp"}


def _resolve_run(con: duckdb.DuckDBPyConnection, run_id: str | None) -> dict:
    """Same "run_id required once >1 run is indexed" rule as
    `api/genes.py::_resolve_run_id`, but returns the full run row (this
    module needs `root` to reach the geneview worker/reconcile paths, not
    just the id)."""
    if run_id is not None:
        row = queries.get_run(con, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"run_id={run_id!r} not indexed")
        return row
    runs = queries.list_runs(con)
    if len(runs) == 1:
        return runs[0]
    raise HTTPException(
        status_code=400,
        detail=f"run_id query param is required when more than one run is indexed (found {len(runs)})",
    )


def _generate_or_502(run_row: dict, gene_id: str, dataset_id: str | None, force: bool) -> dict:
    try:
        return request_geneview(run_row["root"], gene_id, dataset_id=dataset_id, force=force)
    except GeneviewWorkerError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


def _served_path(run_row: dict, relpath: str | None) -> Path | None:
    if relpath is None:
        return None
    return container_run_dir(run_row["root"]) / relpath


@router.get("/{gene_id}/geneview.html")
def geneview_html(
    gene_id: str,
    run_id: str | None = Query(default=None),
    dataset_id: str | None = Query(default=None),
    force: bool = Query(default=False, description="Bypass the on-disk cache and re-render even if a cached figure exists."),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> FileResponse:
    """The real interactive plotly figure -- served as a standalone HTML
    document (ema writes a full `<html>...</html>` file with the plotly.js
    CDN script tag already inlined); the frontend embeds this via an
    `<iframe>`, it is not meant to be parsed/re-rendered client-side.
    """
    run_row = _resolve_run(con, run_id)
    result = _generate_or_502(run_row, gene_id, dataset_id, force)
    path = _served_path(run_row, result["files"]["html"])
    if path is None or not path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"geneview worker reported success but {path} is not visible through this container's /runs mount "
            "-- check HUB_RUNS_ROOT_HOST matches the host path PEAKATAIL_RUNS/docker-compose mounts as /runs.",
        )
    return FileResponse(path, media_type="text/html")


@router.get("/{gene_id}/geneview.png")
def geneview_png(
    gene_id: str,
    run_id: str | None = Query(default=None),
    dataset_id: str | None = Query(default=None),
    force: bool = Query(default=False),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> FileResponse:
    """The real static matplotlib figure (same gene track + PAS-distance
    table as the plotly version, minus interactivity)."""
    run_row = _resolve_run(con, run_id)
    result = _generate_or_502(run_row, gene_id, dataset_id, force)
    path = _served_path(run_row, result["files"]["png"])
    if path is None or not path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"geneview worker reported success but {path} is not visible through this container's /runs mount "
            "-- check HUB_RUNS_ROOT_HOST matches the host path PEAKATAIL_RUNS/docker-compose mounts as /runs.",
        )
    return FileResponse(path, media_type="image/png")


@router.get("/{gene_id}/geneview/meta", response_model=GeneviewRender)
def geneview_meta(
    gene_id: str,
    run_id: str | None = Query(default=None),
    dataset_id: str | None = Query(default=None),
    force: bool = Query(default=False),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> GeneviewRender:
    """Metadata + the PAS-distance table for the currently-cached/just-
    generated geneview -- lets the frontend show a compact summary (gene
    span, n_pas, n_isoforms) and a real, sortable distance table next to the
    embedded figure, rather than relying on the user reading it off the
    rendered image."""
    run_row = _resolve_run(con, run_id)
    result = _generate_or_502(run_row, gene_id, dataset_id, force)
    files = result["files"]

    meta: dict = {}
    meta_path = _served_path(run_row, files.get("meta_json"))
    if meta_path is not None and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:  # noqa: BLE001 -- malformed metadata must not 500 the whole response
            meta = {}

    distances: list[GeneviewPasDistanceRow] = []
    csv_path = _served_path(run_row, files.get("pas_distances_csv"))
    if csv_path is not None and csv_path.exists():
        with csv_path.open(newline="") as fh:
            for rec in csv.DictReader(fh):
                row = {k: (None if v == "" else v) for k, v in rec.items()}
                for col in _DISTANCE_INT_COLS:
                    if row.get(col) is not None:
                        row[col] = int(float(row[col]))
                distances.append(GeneviewPasDistanceRow(**row))

    return GeneviewRender(
        gene_id=gene_id,
        gene_name=meta.get("gene_name", ""),
        run_id=run_row["run_id"],
        dataset_id=result["dataset_id"],
        cluster_key=result["cluster_key"],
        chrom=meta.get("chrom"),
        start=meta.get("start"),
        end=meta.get("end"),
        strand=meta.get("strand"),
        n_pas=meta.get("n_pas"),
        n_clusters_rendered=meta.get("n_clusters_rendered"),
        n_isoforms=meta.get("n_isoforms"),
        cached=result["cached"],
        duration_sec=result["duration_sec"],
        pas_distances=distances,
    )
