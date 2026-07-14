# peakatail-hub backend

FastAPI + DuckDB read-only API for exploring PeakATail pipeline run
directories. See `docs/2026-07-12-peakatail-hub-frontend-design.md` (repo
root `docs/`) for the full design; this README is the practical "how do I
run it" reference.

## Install

```bash
cd backend
uv venv --python 3.12
uv sync --extra test
```

This installs `peakatail-contract` and `peakatail-io` as editable local path
dependencies (`../packages/contract`, `../packages/io`). `peakatail-io` did
not exist as an installable package anywhere in the monorepo when this
backend was *started* (see `peakatail_hub/io_stub/README.md` for that
history); it landed partway through and this backend now depends on it
directly. The bundled stub is kept only as a fallback for a checkout that
hasn't `uv sync`'d `packages/io/` yet.

## Index a runs directory

```bash
uv run hub index /path/to/runs_root
# writes to ~/.peakatail-hub/hub.duckdb by default; override with:
uv run hub index /path/to/runs_root --db /custom/path/hub.duckdb
# or: HUB_DB_PATH=/custom/path/hub.duckdb uv run hub index /path/to/runs_root
```

Walks `runs_root` for every `run_manifest.json`, validates each run
(`peakatail_contract.validate()` via the `Run` facade), and (re)writes its
rows into DuckDB. Idempotent: an unchanged run (byte-identical manifest, by
sha256) is a no-op on the next pass — see `peakatail_hub/index/indexer.py`
docstring and `tests/test_indexer.py::test_idempotent_reindex_is_noop`.

## Run the API

```bash
uv run hub serve --reload
# or directly:
uv run uvicorn peakatail_hub.app:app --reload
```

Interactive docs at `http://127.0.0.1:8000/docs`; OpenAPI JSON at
`http://127.0.0.1:8000/openapi.json` — **this is the frontend's `lib/api`
codegen target** (spec §4: "`lib/api` (generated from OpenAPI)"). Regenerate
the frontend client whenever a router changes shape.

Configuration (env vars, all optional):

| Var | Default | Purpose |
|---|---|---|
| `HUB_DB_PATH` | `~/.peakatail-hub/hub.duckdb` | DuckDB file the API reads from |
| `HUB_CACHE_DIR` | `~/.peakatail-hub/cache` | Render cache directory |
| `HUB_CACHE_MAX_BYTES` | `536870912` (512 MiB) | Render cache size cap |

Both defaults live **outside any run directory** by design — the hub never
writes into data it only reads (`tests/test_render_cache.py` and the
`runs`-table `root` column both exist to keep this true and checkable).

## Tests

```bash
uv run pytest
```

Tests build/index a fixture run into a `tmp_path` DuckDB (currently
`packages/contract/fixtures/`, see "Fixtures" below) and exercise every
router through `fastapi.testclient.TestClient`.

## What's functional vs. stubbed/gated

**Functional against fixtures (and against any real run once the engine
lands the fields below):**
- Indexer (`hub index`): manifest walk, validation, checksum-gated
  idempotency, all 5 tables + `umap_points`.
- All of `/runs`, `/runs/{id}/qc`, `/findings*`, `/genes/{id}`,
  `/genes/{id}/geneview-data`, `/pas/{id}(+/provenance)`,
  `/cells/{id}(+/provenance)`, `/datasets/{id}/umap?color=leiden`, `/search`.

**Stubbed (this backend's own placeholder, not an engine gate):**
- `peakatail_hub/io_stub/` — a fallback `Run`/`validate_run()` implementation
  used only if `peakatail-io` isn't importable (see `io_stub/README.md`).
  `peakatail-io` is now a real dependency and is what actually runs
  (`peakatail_hub.io_compat.USING_IO_STUB is False` in a synced venv); the
  stub was written before it landed and was kept in sync with its final
  interface (notably `Run.gene_counts(var_name, cluster=None)` -> a
  `GeneCounts` object, per-PAS not per-gene) so the fallback path stays
  correct if it's ever exercised.
- `/genes/{id}/geneview.svg` and `.png` — return a placeholder SVG from the
  render cache (proves the cache-location contract; the real layered
  renderer is frontend-side per spec §1 and is a later wave per the task
  brief).
- `/concordance`, `/benchmarks` — return `{available: false, note: ...}`;
  no contract schema exists yet for either artifact type.

**Gated per spec §7c (engine work required, NOT built even against
fixtures where the fixture itself has no such data to show):**
- `/datasets/{id}/umap?color=celltype|stage|sample` returns HTTP 501 with a
  `{available: false, color, gate}` body unless the indexed run's
  `umap_points` rows actually carry that column (gated on A1+A2/B2+B7);
  `color=leiden` always works.
- `/findings` `celltype` facet and `/genes/{id}/geneview-data`'s per-strategy
  celltype overlay are flagged (not blocked) via a `gates: [...]` list in the
  response when the underlying data is entirely `None` — see `FindingRow`
  docstrings for the A1/B4/E1/E5 gates each field is waiting on.
- `/runs/{id}/qc` always returns run-aggregate ledger dropped_at counts
  (works today) but sets `per_sample_stats_available: false` — true
  per-dataset stage-entry counts need engine B5.
- Cross-sample compare by `canonical_cluster` is not implemented as a
  distinct endpoint in v1 (gated on B6); `canonical_cluster` is stored and
  queryable per-run today.

## Fixtures

Tests point at `packages/contract/fixtures/` (a complete, contract-validated
fixture run — manifest, both ledgers, `findings_long.parquet`,
`length_long.parquet`, `pasbed.bed`, and a tiny `clusters.h5ad`), which was
already complete when this backend was built. No interim
`backend/tests/fixtures/` run dir was needed.
