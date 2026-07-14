from __future__ import annotations

import duckdb
from fastapi import HTTPException, Request

from peakatail_hub.store import queries


def resolve_run_id(con: duckdb.DuckDBPyConnection, run_id: str | None) -> str:
    """Shared v1 simplification (see genes.py's original `_resolve_run_id`,
    which this mirrors): PAS/cell browse-list IDs are not namespaced by run
    in the endpoint paths, so callers SHOULD pass `?run_id=`; when omitted
    we fall back to the single indexed run if there is exactly one, and
    fail loud (400, not a silent guess) otherwise.
    """
    if run_id is not None:
        return run_id
    runs = queries.list_runs(con)
    if len(runs) == 1:
        return runs[0]["run_id"]
    raise HTTPException(
        status_code=400,
        detail=(
            "run_id query param is required when more than one run is indexed "
            f"(found {len(runs)}: {[r['run_id'] for r in runs]})"
        ),
    )


def get_db(request: Request) -> duckdb.DuckDBPyConnection:
    """One independent cursor per request, not the shared app-lifetime
    connection directly.

    FastAPI runs sync path functions in a thread pool (`run_in_threadpool`),
    so concurrent requests (e.g. the frontend firing `/findings` and
    `/findings/facets` together on mount) can land on different worker
    threads at the same time. A single `duckdb.DuckDBPyConnection` is NOT
    safe for concurrent queries from multiple threads -- two interleaved
    queries on the same connection object corrupt each other's execution
    state, observed here as intermittent 500s (`fetchone()` returning
    `None` for a `SELECT count(*)`) and, worse, intermittent wrong-but-200
    responses (an empty result on a non-empty table). `Connection.cursor()`
    returns a new handle sharing the same underlying database with its own
    independent execution/transaction state, which IS safe to use
    concurrently -- see https://duckdb.org/docs/stable/connect/concurrency.
    """
    return request.app.state.db.cursor()
