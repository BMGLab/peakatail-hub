"""Multi-directory SOURCES manager (dashboard "collect runs from everywhere"
feature). A `sources` row is a registered runs-root directory; adding or
rescanning one walks it with the existing indexer (`index.index_source`,
which is `index_runs_root` plus source attribution) and merges every run it
finds into the single shared DuckDB store -- never a separate database per
source.

Endpoints (task brief):
    GET    /sources
    POST   /sources             {path, label?}
    DELETE /sources/{source_id}
    POST   /sources/{source_id}/rescan
    POST   /sources/rescan-all
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from peakatail_hub.api.deps import get_db
from peakatail_hub.index import IndexReport, find_run_dirs, index_source
from peakatail_hub.schemas import (
    SourceRescanAllResponse,
    SourceScanReport,
    SourceScanResponse,
    SourceSummary,
)
from peakatail_hub.store import queries

router = APIRouter(tags=["sources"])


class SourceCreate(BaseModel):
    path: str
    label: str | None = None


def _source_id_for(resolved_path: Path) -> str:
    """Deterministic id derived from the resolved absolute path, so adding
    the same directory twice (even across hub restarts) always maps to the
    same source_id rather than minting a fresh one -- `POST /sources` on an
    already-registered path re-scans the existing row instead of erroring
    or duplicating it.
    """
    digest = hashlib.sha256(str(resolved_path).encode()).hexdigest()[:16]
    return f"src_{digest}"


def _to_source_summary(row: dict) -> SourceSummary:
    return SourceSummary(
        source_id=row["source_id"],
        path=row["path"],
        label=row.get("label"),
        added_at=str(row["added_at"]) if row.get("added_at") is not None else "",
        last_scanned_at=str(row["last_scanned_at"]) if row.get("last_scanned_at") is not None else None,
        last_scan_status=row.get("last_scan_status"),
        last_scan_error=row.get("last_scan_error"),
        run_count=row.get("run_count", 0),
    )


def _to_scan_report(report: IndexReport) -> SourceScanReport:
    return SourceScanReport(indexed=report.indexed, skipped_unchanged=report.skipped_unchanged, failed=report.failed)


def _scan_and_record(con: duckdb.DuckDBPyConnection, source_id: str, resolved_path: Path) -> IndexReport:
    """Run the indexer over `resolved_path` tagging every discovered run
    with `source_id`, then persist the outcome onto the `sources` row
    (last_scanned_at/last_scan_status/last_scan_error) so `GET /sources`
    reflects it without re-scanning.
    """
    run_dirs = find_run_dirs(resolved_path)
    if not run_dirs:
        queries.update_source_scan_result(
            con, source_id, "empty", "No run_manifest.json found anywhere under this path."
        )
        return IndexReport()

    report = index_source(con, source_id, resolved_path)
    if report.failed:
        error_summary = "; ".join(
            f"{Path(run_dir).name}: {msg.splitlines()[0]}" for run_dir, msg in report.failed.items()
        )
        queries.update_source_scan_result(con, source_id, "error", error_summary)
    else:
        queries.update_source_scan_result(con, source_id, "ok", None)
    return report


@router.get("/sources", response_model=list[SourceSummary])
def list_sources(con: duckdb.DuckDBPyConnection = Depends(get_db)) -> list[SourceSummary]:
    return [_to_source_summary(s) for s in queries.list_sources(con)]


@router.post("/sources", response_model=SourceScanResponse, status_code=201)
def add_source(body: SourceCreate, con: duckdb.DuckDBPyConnection = Depends(get_db)) -> SourceScanResponse:
    raw = body.path.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="path must not be empty")

    resolved = Path(raw).expanduser().resolve()
    if not resolved.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {resolved}")
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {resolved}")

    existing = queries.get_source_by_path(con, str(resolved))
    if existing is not None:
        # Re-adding an already-registered directory is idempotent: treat it
        # as "rescan this source" rather than a 409/duplicate-row error --
        # friendlier for a user who forgot they'd already added it, or is
        # re-running the same "collect everything" workflow.
        source_id = existing["source_id"]
    else:
        source_id = _source_id_for(resolved)
        queries.insert_source(con, source_id, str(resolved), body.label)

    report = _scan_and_record(con, source_id, resolved)
    source_row = queries.get_source(con, source_id)
    assert source_row is not None  # just inserted/already existed above
    return SourceScanResponse(source=_to_source_summary(source_row), scan=_to_scan_report(report))


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(source_id: str, con: duckdb.DuckDBPyConnection = Depends(get_db)) -> None:
    if queries.get_source(con, source_id) is None:
        raise HTTPException(status_code=404, detail=f"source_id={source_id!r} not registered")
    # Cascades to every run this source owns (see queries.delete_source_cascade
    # docstring) -- a run no longer discoverable under any registered
    # directory shouldn't linger on the dashboard pointing at a deleted source.
    queries.delete_source_cascade(con, source_id)


@router.post("/sources/{source_id}/rescan", response_model=SourceScanResponse)
def rescan_source(source_id: str, con: duckdb.DuckDBPyConnection = Depends(get_db)) -> SourceScanResponse:
    source_row = queries.get_source(con, source_id)
    if source_row is None:
        raise HTTPException(status_code=404, detail=f"source_id={source_id!r} not registered")

    resolved = Path(source_row["path"])
    if not resolved.is_dir():
        queries.update_source_scan_result(con, source_id, "error", f"Path no longer exists or not a directory: {resolved}")
        source_row = queries.get_source(con, source_id)
        return SourceScanResponse(source=_to_source_summary(source_row), scan=SourceScanReport(indexed=[], skipped_unchanged=[], failed={}))

    report = _scan_and_record(con, source_id, resolved)
    source_row = queries.get_source(con, source_id)
    assert source_row is not None
    return SourceScanResponse(source=_to_source_summary(source_row), scan=_to_scan_report(report))


@router.post("/sources/rescan-all", response_model=SourceRescanAllResponse)
def rescan_all_sources(con: duckdb.DuckDBPyConnection = Depends(get_db)) -> SourceRescanAllResponse:
    responses: list[SourceScanResponse] = []
    for source_row in queries.list_sources(con):
        source_id = source_row["source_id"]
        resolved = Path(source_row["path"])
        if not resolved.is_dir():
            queries.update_source_scan_result(con, source_id, "error", f"Path no longer exists or not a directory: {resolved}")
            report = IndexReport()
        else:
            report = _scan_and_record(con, source_id, resolved)
        refreshed = queries.get_source(con, source_id)
        assert refreshed is not None
        responses.append(SourceScanResponse(source=_to_source_summary(refreshed), scan=_to_scan_report(report)))
    return SourceRescanAllResponse(sources=responses)
