"""FastAPI routers, one module per resource family (spec §3/§4 `api/`).

Every router function takes its DuckDB connection via the `get_db` FastAPI
dependency (see `deps.py`) -- none of them import `peakatail_hub.app` or
touch global state directly, so they're importable/testable in isolation
(see `backend/tests/test_api_*.py`).
"""

from peakatail_hub.api import cells, datasets, findings, genes, misc, pas, runs, sources

ALL_ROUTERS = [
    runs.router,
    findings.router,
    genes.router,
    pas.router,
    cells.router,
    datasets.router,
    misc.router,
    sources.router,
]

__all__ = ["ALL_ROUTERS"]
