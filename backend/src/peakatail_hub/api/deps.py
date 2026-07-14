from __future__ import annotations

import duckdb
from fastapi import Request


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
