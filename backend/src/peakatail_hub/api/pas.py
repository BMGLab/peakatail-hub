from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query

from peakatail_contract import FindingRow, PasLedgerRow
from peakatail_hub.api.deps import get_db, resolve_run_id
from peakatail_hub.schemas import PasPage, PasProvenance
from peakatail_hub.store import queries

router = APIRouter(prefix="/pas", tags=["pas"])


@router.get("", response_model=PasPage)
def list_pas(
    q: str | None = Query(default=None, description="Substring match on pas_uid / gene_id / unified_pas_id."),
    run_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> PasPage:
    """The PAS browser: searchable, paginated listing over the full ledger
    (survived + dropped, see `queries.list_pas` -- a provenance browser, not
    a render feed).
    """
    rid = resolve_run_id(con, run_id)
    offset = queries.decode_cursor(cursor)
    total = queries.count_pas(con, rid, q)
    rows = queries.list_pas(con, rid, q, offset, limit)
    next_offset = offset + limit
    next_cursor = queries.encode_cursor(next_offset) if next_offset < total else None
    return PasPage(items=[PasLedgerRow(**r) for r in rows], next_cursor=next_cursor, total=total)


@router.get("/{pas_uid}", response_model=PasLedgerRow)
def get_pas(pas_uid: str, con: duckdb.DuckDBPyConnection = Depends(get_db)) -> PasLedgerRow:
    row = queries.get_pas(con, pas_uid)
    if row is None:
        raise HTTPException(status_code=404, detail=f"pas_uid={pas_uid!r} not found")
    return PasLedgerRow(**row)


@router.get("/{pas_uid}/provenance", response_model=PasProvenance)
def pas_provenance(pas_uid: str, con: duckdb.DuckDBPyConnection = Depends(get_db)) -> PasProvenance:
    result = queries.pas_provenance(con, pas_uid)
    if result is None:
        raise HTTPException(status_code=404, detail=f"pas_uid={pas_uid!r} not found")
    return PasProvenance(
        pas=PasLedgerRow(**result["pas"]),
        findings=[FindingRow(**f) for f in result["findings"]],
        length_rows=result["length_rows"],
        trail=result["trail"],
    )
