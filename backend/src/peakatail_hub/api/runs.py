from __future__ import annotations

import json

import duckdb
from fastapi import APIRouter, Depends, HTTPException

from peakatail_hub.api.deps import get_db
from peakatail_hub.schemas import QcFunnel, RunSummary
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
    )


@router.get("/runs", response_model=list[RunSummary])
def list_runs(con: duckdb.DuckDBPyConnection = Depends(get_db)) -> list[RunSummary]:
    return [_to_run_summary(r) for r in queries.list_runs(con)]


@router.get("/runs/{run_id}/qc", response_model=QcFunnel)
def run_qc(run_id: str, con: duckdb.DuckDBPyConnection = Depends(get_db)) -> QcFunnel:
    if queries.get_run(con, run_id) is None:
        raise HTTPException(status_code=404, detail=f"run_id={run_id!r} not indexed")
    return QcFunnel(**queries.qc_funnel(con, run_id))
