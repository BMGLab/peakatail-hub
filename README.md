# peakatail-hub

Standalone analyst cockpit for exploring PeakATail results — findings, an
interactive multi-strategy geneview, UMAP/QC, and full PAS→gene→cell provenance.

**This is a separate repo from the PeakATail engine.** The two are coupled only by
`peakatail-contract` (versioned schemas + stable IDs). The hub is a **read-only
consumer** of run directories; it never writes into them (render-on-demand output
goes to the hub's own cache).

## Layout (monorepo for now; `contract` graduates to its own repo when the engine consumes it)

```
packages/contract/   peakatail-contract — pydantic models, JSON Schema, id grammar,
                     validate(), and fixtures. Schema-only, zero heavy deps.
                     Both the engine and the hub depend on THIS (nothing else).
packages/io/         peakatail-io — the Run read-facade (h5ad/anndata reader).
                     The one package allowed to depend on anndata/h5py/scipy
                     (lazy-imported); backend depends on it for h5ad drill-down.
backend/             FastAPI read API + DuckDB store + indexer + render cache.
frontend/            React + Vite + TS SPA (findings, geneview, umap, qc, audit, compare).
docs/                Design spec.
```

## Running it

See **[RUNNING.md](RUNNING.md)** for exact install/index/serve commands —
verified working end-to-end against the fixture data in
`packages/contract/fixtures/`.

## Design
See `docs/2026-07-12-peakatail-hub-frontend-design.md` and the engine-side plan
`PeakATail/reports/PeakATail_Architecture_and_Implementation_Plan.md`.

## Status
Contract + io + backend + frontend all present and working against the
fixture run: `hub index` builds a DuckDB from it, the backend serves all
routers (runs/findings/genes/pas/cells/datasets(umap)/misc), and all six
frontend views (Findings/UMAP/Run-QC/Gene/Audit/Compare) render real data
with no console errors, verified in a real headless-Chromium browser.
107 Python tests (contract 50 + io 18 + backend 39) + 10 frontend tests,
`tsc` clean. Indexing a *real* PeakATail run directory is gated on the
engine's E2 manifest writer landing; everything else here is real, not a
stub.
