from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query

from peakatail_contract import FindingRow
from peakatail_hub.api.deps import get_db
from peakatail_hub.schemas import FacetValue, FindingsFacets, FindingsPage
from peakatail_hub.store import queries

router = APIRouter(prefix="/findings", tags=["findings"])


def _filter_from_query(
    run_id: str | None,
    arm: str | None,
    strategy: str | None,
    celltype: str | None,
    direction: str | None,
    utr_class: str | None,
    q_max: float | None,
    min_reads: int | None,
) -> queries.FindingsFilter:
    return queries.FindingsFilter(
        run_id=run_id,
        arm=arm,
        strategy=strategy,
        celltype=celltype,
        direction=direction,
        utr_class=utr_class,
        q_max=q_max,
        min_reads=min_reads,
    )


@router.get("", response_model=FindingsPage)
def list_findings(
    run_id: str | None = Query(default=None),
    arm: str | None = Query(default=None),
    strategy: str | None = Query(default=None),
    celltype: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    utr_class: str | None = Query(default=None),
    q_max: float | None = Query(default=None),
    min_reads: int | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=1000),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> FindingsPage:
    flt = _filter_from_query(run_id, arm, strategy, celltype, direction, utr_class, q_max, min_reads)
    offset = queries.decode_cursor(cursor)
    total = queries.count_findings(con, flt)
    rows = queries.query_findings(con, flt, offset, limit)
    next_offset = offset + len(rows)
    next_cursor = queries.encode_cursor(next_offset) if next_offset < total else None
    return FindingsPage(items=[FindingRow(**r) for r in rows], next_cursor=next_cursor, total=total)


@router.get("/facets", response_model=FindingsFacets)
def findings_facets(
    run_id: str | None = Query(default=None),
    arm: str | None = Query(default=None),
    strategy: str | None = Query(default=None),
    celltype: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    utr_class: str | None = Query(default=None),
    q_max: float | None = Query(default=None),
    min_reads: int | None = Query(default=None),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> FindingsFacets:
    flt = _filter_from_query(run_id, arm, strategy, celltype, direction, utr_class, q_max, min_reads)
    total = queries.count_findings(con, flt)
    facets = queries.findings_facets(con, flt)
    return FindingsFacets(
        arm=[FacetValue(**f) for f in facets["arm"]],
        strategy=[FacetValue(**f) for f in facets["strategy"]],
        celltype=[FacetValue(**f) for f in facets["celltype"]],
        direction=[FacetValue(**f) for f in facets["direction"]],
        utr_class=[FacetValue(**f) for f in facets["utr_class"]],
        total=total,
    )


@router.get("/{finding_uid}", response_model=FindingRow)
def get_finding(finding_uid: str, con: duckdb.DuckDBPyConnection = Depends(get_db)) -> FindingRow:
    row = queries.get_finding(con, finding_uid)
    if row is None:
        raise HTTPException(status_code=404, detail=f"finding_uid={finding_uid!r} not found")
    return FindingRow(**row)
