from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query

from peakatail_contract import CellLedgerRow
from peakatail_hub.api.deps import get_db, resolve_run_id
from peakatail_hub.schemas import CellProvenance, CellsPage
from peakatail_hub.store import queries

router = APIRouter(prefix="/cells", tags=["cells"])


@router.get("", response_model=CellsPage)
def list_cells(
    q: str | None = Query(default=None, description="Substring match on barcode / cell_uid / cluster."),
    run_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> CellsPage:
    """The cell browser: searchable, paginated listing over the full cell
    ledger (survived + dropped, same rationale as `list_pas`).
    """
    rid = resolve_run_id(con, run_id)
    offset = queries.decode_cursor(cursor)
    total = queries.count_cells(con, rid, q)
    rows = queries.list_cells(con, rid, q, offset, limit)
    next_offset = offset + limit
    next_cursor = queries.encode_cursor(next_offset) if next_offset < total else None
    return CellsPage(items=[CellLedgerRow(**r) for r in rows], next_cursor=next_cursor, total=total)


@router.get("/{cell_uid}", response_model=CellLedgerRow)
def get_cell(cell_uid: str, con: duckdb.DuckDBPyConnection = Depends(get_db)) -> CellLedgerRow:
    row = queries.get_cell(con, cell_uid)
    if row is None:
        raise HTTPException(status_code=404, detail=f"cell_uid={cell_uid!r} not found")
    return CellLedgerRow(**row)


@router.get("/{cell_uid}/provenance", response_model=CellProvenance)
def cell_provenance(cell_uid: str, con: duckdb.DuckDBPyConnection = Depends(get_db)) -> CellProvenance:
    result = queries.cell_provenance(con, cell_uid)
    if result is None:
        raise HTTPException(status_code=404, detail=f"cell_uid={cell_uid!r} not found")
    return CellProvenance(
        cell=CellLedgerRow(**result["cell"]),
        length_rows=result["length_rows"],
        trail=result["trail"],
    )
