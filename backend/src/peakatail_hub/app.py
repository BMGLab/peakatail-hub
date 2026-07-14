"""FastAPI application factory.

One long-lived DuckDB connection is opened at startup (via the lifespan
context manager) and reused for every request -- see `store/db.py`'s
docstring for the concurrency rationale. The OpenAPI schema this app
generates (`/openapi.json`) is the frontend's `lib/api` codegen target
(spec §4).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from peakatail_hub import config
from peakatail_hub.api import ALL_ROUTERS
from peakatail_hub.store.db import connect


@asynccontextmanager
async def lifespan(app: FastAPI):
    con = connect(config.db_path(), read_only=False)
    app.state.db = con
    try:
        yield
    finally:
        con.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="peakatail-hub",
        version="0.1.0",
        description=(
            "Read-only analyst cockpit API over indexed PeakATail run directories. "
            "Never writes into run dirs; render-on-demand output goes to its own cache."
        ),
        lifespan=lifespan,
    )
    for router in ALL_ROUTERS:
        app.include_router(router)

    @app.get("/health", tags=["misc"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
