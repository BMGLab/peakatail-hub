# Running peakatail-hub

Everything below has been run and verified working against the fixture data
shipped in `packages/contract/fixtures/`. Python 3.12 (via `uv`) + Node
throughout. Run these from the repo root unless noted.

## 0. Prerequisites

- [`uv`](https://docs.astral.sh/uv/) (Python 3.12 package/venv manager)
- Node.js (for the frontend; `npm` ships with it)

## 1. Install everything

```bash
# contract (schema-only, zero heavy deps)
cd packages/contract && uv venv --python 3.12 && uv sync --extra test && cd ../..

# io (the h5ad/anndata reader -- heavier deps, lazy-imported)
cd packages/io && uv venv --python 3.12 && uv sync --extra test && cd ../..

# backend (FastAPI + DuckDB; depends on both packages above as editable local deps)
cd backend && uv venv --python 3.12 && uv sync --extra test && cd ..

# frontend
cd frontend && npm install && cd ..
```

## 2. Run the tests (optional but recommended first)

```bash
(cd packages/contract && uv run pytest -q)   # 50 passed
(cd packages/io && uv run pytest -q)         # 18 passed
(cd backend && uv run pytest -q)             # 39 passed
(cd frontend && npx tsc -b && npx vitest run)  # tsc clean, 10 passed
```

## 3. Build the DuckDB index from the fixture run

```bash
cd backend
HUB_DB_PATH=/tmp/hub.duckdb uv run hub index ../packages/contract/fixtures
```

`hub index` walks the given directory for any `run_manifest.json`, validates
each run against the contract, and (re)writes it into the DuckDB file at
`HUB_DB_PATH` (default `~/.peakatail-hub/hub.duckdb` if unset). Re-running it
on an unchanged run is a fast no-op (keyed on the manifest's sha256) — to
force a rebuild, either point `HUB_DB_PATH` at a fresh file or delete the
existing one first.

To index a **real** PeakATail run directory instead of the fixture, point
`hub index` at its parent directory (anywhere containing one or more
`run_manifest.json` files, at any depth) once the engine's E2 manifest
writer has run.

## 4. Start the backend API

```bash
cd backend
HUB_DB_PATH=/tmp/hub.duckdb uv run hub serve --port 8000
# or with auto-reload during development:
HUB_DB_PATH=/tmp/hub.duckdb uv run hub serve --port 8000 --reload
```

Verify: `curl http://127.0.0.1:8000/health` → `{"status":"ok"}`.
Interactive API docs: `http://127.0.0.1:8000/docs`.

`HUB_DB_PATH` must match what you passed to `hub index` in step 3. Other
env vars (all optional): `HUB_CACHE_DIR` (render cache, default
`~/.peakatail-hub/cache`), `HUB_CACHE_MAX_BYTES` (default 512 MiB).

## 5. Start the frontend

```bash
cd frontend
VITE_USE_MOCKS=false npm run dev -- --port 5173
```

Open **http://localhost:5173/**. `VITE_USE_MOCKS=false` is required to hit
the real backend from step 4 — omitting it (or setting it to anything else)
falls back to in-memory mock data (`src/lib/api/mockData.ts`), which is the
default for quick UI iteration without a backend running. The dev server
proxies `/api/*` to `http://127.0.0.1:8000` (see `vite.config.ts`), so the
backend must already be listening on port 8000 (step 4) — adjust the proxy
target there if you run the backend on a different port.

Once loaded: pick **fixture-run-0001** from the **Scope** selector in the
top bar (most views are scoped to a run and are correctly empty until one is
selected) to see real findings, UMAP, QC funnel, and gene/PAS/cell
provenance rendered from the fixture data.

## 6. One-shot smoke check

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/runs
curl -s "http://127.0.0.1:8000/findings?limit=5"
```

All three should return real JSON (not connection-refused / 404 / 500) once
steps 3–4 are done.

## Troubleshooting

- **`DuckDB ... Conflicting lock is held`**: only one process may hold a
  read-write connection to a given `HUB_DB_PATH` file at a time. Stop any
  other `hub index`/`hub serve` process using the same path first.
- **Frontend shows real headers/counts but empty tables/charts**: almost
  certainly `VITE_USE_MOCKS` wasn't set to `false`, or the backend isn't
  reachable at the vite proxy's target — check the browser network tab for
  `/api/*` requests actually reaching `127.0.0.1:8000`.
- **A view is empty with "Select a run/dataset scope from the top bar
  first"**: expected — most views (UMAP, QC, Audit trace) need a run picked
  from the Scope selector; Findings does not (it defaults to the only/most
  recently indexed run).
