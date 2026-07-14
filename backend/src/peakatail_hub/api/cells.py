from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, HTTPException

from peakatail_contract import CellLedgerRow
from peakatail_hub.api.deps import get_db
from peakatail_hub.schemas import CellProvenance
from peakatail_hub.store import queries

router = APIRouter(prefix="/cells", tags=["cells"])


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
