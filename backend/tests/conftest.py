from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from peakatail_hub.index import index_run
from peakatail_hub.io_compat import Run
from peakatail_hub.store.db import connect

# packages/contract/fixtures/ was already complete (manifest + both ledgers +
# findings_long/length_long parquet + pasbed.bed + a tiny clusters.h5ad) when
# this backend was built, so tests point straight at it -- no interim
# backend/tests/fixtures/ run dir was needed (task brief §5 fallback not
# required here).
CONTRACT_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "packages" / "contract" / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def _check_fixtures_exist():
    assert (CONTRACT_FIXTURES_DIR / "run_manifest.json").exists(), (
        f"expected packages/contract fixtures at {CONTRACT_FIXTURES_DIR}; "
        "if this ever goes missing, generate an interim backend/tests/fixtures/ "
        "run dir mirroring the same shapes (see packages/contract/scripts/make_fixtures.py)."
    )


@pytest.fixture()
def fixture_run() -> Run:
    return Run.from_dir(CONTRACT_FIXTURES_DIR)


@pytest.fixture()
def fixture_run_id() -> str:
    manifest = json.loads((CONTRACT_FIXTURES_DIR / "run_manifest.json").read_text())
    return manifest["run_id"]


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "hub.duckdb"


@pytest.fixture()
def indexed_con(db_path: Path) -> duckdb.DuckDBPyConnection:
    """A DuckDB connection with the contract fixture run already indexed."""
    con = connect(db_path, read_only=False)
    index_run(con, CONTRACT_FIXTURES_DIR)
    yield con
    con.close()


@pytest.fixture()
def indexed_db_path(db_path: Path) -> Path:
    """Like `indexed_con`, but closes the connection and hands back the
    path -- for tests (e.g. the API tests) that need a fresh connection of
    their own (DuckDB is single-writer; the app's lifespan opens its own).
    """
    con = connect(db_path, read_only=False)
    try:
        index_run(con, CONTRACT_FIXTURES_DIR)
    finally:
        con.close()
    return db_path


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, indexed_db_path: Path, tmp_path: Path):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("HUB_DB_PATH", str(indexed_db_path))
    monkeypatch.setenv("HUB_CACHE_DIR", str(tmp_path / "cache"))

    # Re-import so `peakatail_hub.app` reads the freshly-set env vars via
    # `config.db_path()`/`config.cache_dir()` at lifespan-startup time
    # (both are read lazily inside functions, not at module import time, so
    # a plain import is enough -- no importlib.reload needed).
    from peakatail_hub.app import app

    with TestClient(app) as test_client:
        yield test_client
