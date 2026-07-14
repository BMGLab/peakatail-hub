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
                     validate(), and the manifest-driven Run read-facade.
                     Both the engine and the hub depend on THIS (nothing else).
backend/             FastAPI read API + DuckDB store + indexer + render cache.
frontend/            React + Vite + TS SPA (app shell, findings, geneview, umap, qc, audit).
docs/                Design spec.
```

## Design
See `docs/2026-07-12-peakatail-hub-frontend-design.md` and the engine-side plan
`PeakATail/reports/PeakATail_Architecture_and_Implementation_Plan.md`.

## Status
Scaffold / foundation. Contract package + backend skeleton first, then the SPA.
