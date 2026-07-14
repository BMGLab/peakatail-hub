"""DuckDB connection management.

v1 concurrency model: DuckDB is single-process/single-writer-friendly; the
indexer (`hub index`, a short-lived CLI process) opens its own read-write
connection, does its writes inside a transaction, and exits. The API
process opens one long-lived read-only-by-convention connection (nothing in
`api/` ever writes) at startup via the FastAPI lifespan and reuses it for
every request -- see `peakatail_hub.app`.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from peakatail_hub.store.schema import apply_schema


def connect(path: Path | str, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path), read_only=read_only)
    if not read_only:
        apply_schema(con)
    return con
