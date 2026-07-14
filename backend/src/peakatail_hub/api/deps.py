from __future__ import annotations

import duckdb
from fastapi import Request


def get_db(request: Request) -> duckdb.DuckDBPyConnection:
    return request.app.state.db
