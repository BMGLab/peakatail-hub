from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, Query

from peakatail_hub.api.deps import get_db
from peakatail_hub.schemas import SearchResults, StubResponse
from peakatail_hub.store import queries

router = APIRouter(tags=["misc"])


@router.get("/concordance", response_model=StubResponse)
def concordance(run_id: str = Query(...)) -> StubResponse:
    return StubResponse(**queries.concordance_stub(run_id))


@router.get("/benchmarks", response_model=StubResponse)
def benchmarks(run_id: str = Query(...)) -> StubResponse:
    return StubResponse(**queries.benchmarks_stub(run_id))


@router.get("/search", response_model=SearchResults)
def search(q: str = Query(..., min_length=1), con: duckdb.DuckDBPyConnection = Depends(get_db)) -> SearchResults:
    from peakatail_contract import CellLedgerRow, PasLedgerRow

    results = queries.search(con, q)
    return SearchResults(
        q=q,
        genes=results["genes"],
        pas=[PasLedgerRow(**r) for r in results["pas"]],
        cells=[CellLedgerRow(**r) for r in results["cells"]],
    )
