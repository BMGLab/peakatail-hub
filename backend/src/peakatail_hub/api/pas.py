from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, HTTPException

from peakatail_contract import FindingRow, PasLedgerRow
from peakatail_hub.api.deps import get_db
from peakatail_hub.schemas import PasProvenance
from peakatail_hub.store import queries

router = APIRouter(prefix="/pas", tags=["pas"])


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
