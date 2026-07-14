"""`/datasets/{id}/umap` -- per spec §7f, full point set in one response (no
bbox/LOD tiling server-side; that's a frontend `scattergl` rendering
concern). `{id}` here is the run_id (the embedding is computed once per run
across its constituent datasets) -- see the docstring below for why, and
`?dataset_id=` to further narrow within a run if needed.
"""

from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from peakatail_hub.api.deps import get_db
from peakatail_hub.schemas import UmapPoint, UmapResponse
from peakatail_hub.store import queries

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("/{run_id}/umap")
def get_umap(
    run_id: str,
    color: str = Query(default="leiden", pattern="^(leiden|celltype|stage|sample)$"),
    dataset_id: str | None = Query(default=None),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
):
    if queries.get_run(con, run_id) is None:
        raise HTTPException(status_code=404, detail=f"run_id={run_id!r} not indexed")

    if not queries.umap_color_available(con, run_id, color):
        # Spec §7c: celltype/stage/sample recolor gated on A1+A2/B2+B7 --
        # real runs don't carry these obs columns yet. Fail loud with a
        # structured body, not a silently-empty 200.
        return JSONResponse(
            status_code=501,
            content={
                "available": False,
                "color": color,
                "gate": (
                    "UMAP recolor by celltype/stage/sample requires engine "
                    "A1 (+A2/B2/B7); this run's umap_points has no non-null "
                    f"{color!r} values. color='leiden' always works."
                ),
            },
        )

    points = queries.umap_points(con, run_id)
    if dataset_id is not None:
        points = [p for p in points if p["dataset_id"] == dataset_id]
    return UmapResponse(
        run_id=run_id,
        color=color,
        n_points=len(points),
        points=[UmapPoint(**p) for p in points],
    )
