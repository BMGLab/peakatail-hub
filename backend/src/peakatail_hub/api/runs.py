from __future__ import annotations

import json

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query

from peakatail_hub.api.deps import get_db
from peakatail_hub.schemas import QcFunnel, RunDataset, RunSummary, SwitchResults, SwitchTrendGene
from peakatail_hub.store import queries

router = APIRouter(tags=["runs"])


def _to_run_summary(row: dict) -> RunSummary:
    return RunSummary(
        run_id=row["run_id"],
        root=row["root"],
        contract_version=row["contract_version"],
        resolved_config=json.loads(row["resolved_config"]) if row["resolved_config"] else {},
        stratum_to_label=json.loads(row["stratum_to_label"]) if row["stratum_to_label"] else {},
        n_pas=row["n_pas"],
        n_cells=row["n_cells"],
        n_genes=row["n_genes"],
        n_datasets=row["n_datasets"],
        n_findings=row["n_findings"],
        n_length_rows=row["n_length_rows"],
        indexed_at=str(row["indexed_at"]) if row["indexed_at"] is not None else None,
        source_id=row.get("source_id"),
        source_path=row.get("source_path"),
        source_label=row.get("source_label"),
        n_celltypes=row.get("n_celltypes"),
        atlas_snap_available=row.get("atlas_snap_available"),
    )


@router.get("/runs", response_model=list[RunSummary])
def list_runs(con: duckdb.DuckDBPyConnection = Depends(get_db)) -> list[RunSummary]:
    return [_to_run_summary(r) for r in queries.list_runs(con)]


@router.get("/runs/{run_id}/qc", response_model=QcFunnel)
def run_qc(run_id: str, con: duckdb.DuckDBPyConnection = Depends(get_db)) -> QcFunnel:
    if queries.get_run(con, run_id) is None:
        raise HTTPException(status_code=404, detail=f"run_id={run_id!r} not indexed")
    return QcFunnel(**queries.qc_funnel(con, run_id))


@router.get("/runs/{run_id}/datasets", response_model=list[RunDataset])
def run_datasets(run_id: str, con: duckdb.DuckDBPyConnection = Depends(get_db)) -> list[RunDataset]:
    """Every dataset actually indexed for this run (from `umap_points`, one
    row per `07_clustering/<dataset_id>/clusters.h5ad` -- see
    `queries.list_run_datasets`). Empty list (not 404) for a run indexed
    before UMAP points existed, or whose clusters.h5ad couldn't be opened --
    a truthful "no per-dataset clustering data available", not an error.
    """
    if queries.get_run(con, run_id) is None:
        raise HTTPException(status_code=404, detail=f"run_id={run_id!r} not indexed")
    return [RunDataset(**r) for r in queries.list_run_datasets(con, run_id)]


@router.get("/runs/{run_id}/switch", response_model=SwitchResults)
def run_switch_results(run_id: str, con: duckdb.DuckDBPyConnection = Depends(get_db)) -> SwitchResults:
    """The run's B3_switch results (diff/length/trend), one entry per
    celltype actually seen -- see `queries.switch_summary`. `celltypes: []`
    (not 404/empty-error) for a run with no B3_switch directory at all
    (single-dataset `reannotate`/`grid` runs don't have one) -- callers
    should render an honest "no switch analysis for this run" empty state.
    """
    if queries.get_run(con, run_id) is None:
        raise HTTPException(status_code=404, detail=f"run_id={run_id!r} not indexed")
    return SwitchResults(**queries.switch_summary(con, run_id))


@router.get("/runs/{run_id}/switch/{celltype}/trend-genes", response_model=list[SwitchTrendGene])
def run_switch_trend_genes(
    run_id: str,
    celltype: str,
    limit: int = Query(default=50, ge=1, le=500),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[SwitchTrendGene]:
    """Per-gene drill-down behind one celltype's length-trend-across-stages
    headline (`SwitchResults.celltypes[].trend`) -- top genes by |slope|,
    the professor headline finding (3'UTR shortening/lengthening across
    disease stages) at gene resolution.
    """
    if queries.get_run(con, run_id) is None:
        raise HTTPException(status_code=404, detail=f"run_id={run_id!r} not indexed")
    return [SwitchTrendGene(**r) for r in queries.switch_trend_top_genes(con, run_id, celltype, limit)]
