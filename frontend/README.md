# peakatail-hub frontend

React + Vite + TypeScript SPA for the peakatail-hub analyst cockpit. See
`../docs/2026-07-12-peakatail-hub-frontend-design.md` for the full design spec
this scaffold implements.

## Running

```bash
npm install
npm run dev       # dev server on :5173, proxies /api -> http://127.0.0.1:8000
npm run build     # tsc -b && vite build -> dist/
npm run preview   # preview the production build
npm run test      # vitest run (see "Tests" below)
npm run lint      # eslint .
```

Node 20+, npm 10+. All commands above have been run successfully in this
sandbox (`npm install`, `npx tsc -b`, `npx vitest run`, `npm run build`,
`npx eslint .` all pass -- see the accompanying task report for exact output).

## How mocks work

Every API call goes through `src/lib/api/client.ts`'s `api` object, which is
consumed exclusively via the React Query hooks in `src/lib/api/hooks.ts`
(views should never import `api` directly except for the odd
imperative-fetch case, e.g. `TopBar`'s search-result click handler).

`USE_MOCKS` (exported from `client.ts`) is `true` by default and reads from
`src/lib/api/mockData.ts` (small deterministic in-memory fixtures matching the
`lib/contract/types.ts` shapes -- 240 findings, 4 genes, 800 UMAP points,
etc). Set `VITE_USE_MOCKS=false` in a `.env` file to hit a real backend
instead; `VITE_API_BASE` controls the base path (defaults to `/api`, proxied
in dev to `http://127.0.0.1:8000` per `vite.config.ts`'s `server.proxy`).

Swapping a single hook from mock to real data is a one-line change: every
`api.*` function has an `if (USE_MOCKS) { ...mock... } return fetchJson(...)`
shape, so deleting the mock branch (or flipping the env var) is all that's
needed once the backend/`packages/io` land.

## What's real vs stubbed

**Real (functional against mock data), not placeholder-only:**
- App shell: `TopBar` (search, scope selector, pin indicator), `NavRail`
  (react-router-dom routes to all 6 views), `DetailPanel` (polymorphic
  gene/PAS/cell selection with real field rendering + action buttons),
  `PinTray` (add/remove, persisted to localStorage via zustand `persist`).
- State: `useSelectionStore`, `usePinStore`, `useScopeStore` (all typed,
  small, tested).
- `FindingsView`: TanStack Table + `@tanstack/react-virtual` virtualized
  table, facet sidebar wired to `useFindingsFacets`/`useFindings` (filters
  actually filter the mock data), row click -> DetailPanel + navigate to
  gene, checkbox multi-select -> pin.
- `GeneView` + `views/gene/geneview/*`: `CoordinateScale` (plain linear-scale
  math, see decision below), `Ruler`, `PASStemLayer`, `DiffOverlayLayer`,
  `LengthOverlayLayer`, `LayerPanel` (toggle checkboxes), `useGeneviewWindow`
  (zoom/pan/reset-to-gene-span state) are all real, minimal implementations
  rendering mock data with working zoom (mouse wheel)/pan/reset. `PDUI by
  stage` and `PAS list` companion panels are real (Plotly + a real table).
- `UmapView`: single `scattergl` trace over 800 mock points, real
  color-by-field selector with `celltype`/`stage`/`sample` genuinely disabled
  (not just decorative) per design §7c, tooltip explains why.
- `QcView`: real funnel bar chart + stage table from mock 7-stage counts,
  real concordance/benchmarks tables.
- `AuditView`: real search-by-PAS/cell-UID with a stage stepper showing
  survived/dropped status per stage.
- `CompareView`: reads live pin-tray state; gene panels show real fields.
- `ExportButton`: functional PNG (canvas re-render at configurable DPI scale)
  + SVG (serialize) export against whatever DOM node ref is passed in.

**Deliberately stubbed / rough placeholder (documented inline with `TODO`/
comments at the point of stubbing):**
- `lib/contract/types.ts`: hand-written interim TS types (see header comment
  `// TODO: replace with codegen from packages/contract JSON Schema once
  available`). Field names are IDENTICAL to the spec's entity block so the
  future codegen swap is type-only.
- `lib/api/client.ts`: real-fetch branches (`fetchJson`) are written but
  untested against a live backend (none exists yet in this build wave).
- `GeneModelLayer`: renders one evenly-segmented placeholder block per gene,
  not real per-exon GTF coordinates (not available via contract/io yet).
- `CoverageLayer`: intentionally a stub note, hidden by default -- true
  bigWig coverage is roadmap B per design §0/§1.5.
- `LengthOverlayLayer`: `classic`/`shannon` strategies render an aggregate
  badge instead of per-PAS ticks, since only `proportion` is per-PAS until
  engine change E5 lands (design §7c).
- `QcView` config diff: placeholder text when `config_diff` is absent
  (real version must read the E2 manifest's resolved config, not
  `run_config.json`, per design §7d).
- `CompareView`: non-gene pinned entities (PAS/cell) render a stub message;
  full side-by-side geneview/funnel comparison is gated on `canonical_cluster`
  (B6) per design §7c.
- Caveat-flag *conditions* in `views/findings/caveatFlags.ts` (omnibus
  double-dip / width-confound / atlas-circularity) are explicitly marked
  STUB logic -- the badges/UI plumbing are real, but the trigger conditions
  are placeholders (e.g. `strategy === 'nb_multi'`) until the real ledger
  joins are available. The two caveats that ARE fully real everywhere counts
  are shown: "not UMI-deduplicated" (PAS stems + PAS detail panel) and
  `n_pas` labeled "PAS, not genes" (cell detail panel + audit view) -- these
  are hardcoded facts from design §7e, not stubs.
- `GeneviewCanvas`: each layer renders its own independent `<svg>` (so
  per-layer toggle/refetch stays independent per design §1); `ExportButton`
  therefore only captures the first layer's SVG today -- a later wave should
  merge the stack into one `<svg>` with a `<g>` per layer for full-view
  export. Called out inline in the component.

## Architecture decisions worth flagging to other package agents

- **No `d3` dependency.** `views/gene/geneview/CoordinateScale.ts` implements
  the genomic-coordinate <-> pixel linear scale by hand (~15 lines,
  unit-testable, tree-shakes to zero). If a later wave needs d3's
  zoom-behavior/brush helpers specifically, prefer adding a targeted
  `d3-zoom`/`d3-selection` dependency rather than the `d3` umbrella package.
  Documented at the top of `CoordinateScale.ts`.
- **`react-plotly.js` + `plotly.js-dist-min`, via the `factory` entry point.**
  `react-plotly.js`'s default export hardcodes `plotly.js/dist/plotly` (the
  full package), so using the smaller `plotly.js-dist-min` bundle requires
  importing `react-plotly.js/factory` and binding it manually
  (`src/charts/PlotlyChart.tsx`). `plotly.js-dist-min` ships no type
  declarations, so `src/types/plotly-dist-min.d.ts` aliases it to
  `@types/plotly.js`'s types (same public API). Even with the `-dist-min`
  bundle, Plotly is the dominant contributor to the ~5.2MB (1.6MB gzip)
  production JS bundle -- flagged as an open question below rather than
  solved here (code-splitting the geneview/QC/UMAP Plotly usages behind
  `React.lazy()` is the obvious next step but out of scope for this scaffold
  wave).
- **`pas_uid` grammar assumed as `chrom:pos:strand`.** Both mock data and
  `parsePasUid()` in `CoordinateScale.ts` assume this exact format (matching
  design §7d's "indexer-minted `pas_uid`"). If the contract package mints a
  different grammar, `parsePasUid` is the single place to update.
- **Supporting types beyond the 5 given entities** (`RunSummary`, `RunQc`,
  `GeneSummary`, `PasDetail`, `CellDetail`, `GeneviewLayerData`, `UmapPoint`,
  `ConcordanceSummary`, `BenchmarkSummary`, `SearchResult`, `SelectedEntity`,
  `PinnedEntity`) were added to `lib/contract/types.ts` to type the
  endpoints/shell described in design §2-3. These are clearly separated in
  the file with their own header comment and are NOT part of the literal
  5-entity block the contract package was given -- please reconcile field
  names against the real manifest/`Run` models when available, especially
  `RunQc.config_diff` (shape guessed) and `GeneviewLayerData` (assembled from
  the 5 given entities plus a `gene`/`window` wrapper).
- **TypeScript strictness**: `tsconfig.app.json` enables `strict`,
  `noUncheckedIndexedAccess`, and `exactOptionalPropertyTypes`. The latter is
  unusually strict for React/JSX code (most component libraries -- including
  `react-plotly.js`'s bundled types -- declare optional props as `foo?: T`
  rather than `foo?: T | undefined`, which are NOT equivalent under this
  flag). Where this caused friction, the fix applied was either (a) widening
  our OWN prop types to `foo?: T | undefined` explicitly, or (b) conditionally
  spreading a prop instead of always passing it (see `PlotlyChart.tsx`). No
  compiler flags were relaxed to work around this.

## Testing

`npm run test` runs Vitest + Testing Library. Current suite (8 tests, all
passing):
- `src/app/AppShell.test.tsx` -- nav rail links render, detail panel renders
  its empty state, search input present.
- `src/app/DetailPanel.test.tsx` -- empty state vs. populated (gene) state,
  including action buttons.
- `src/state/usePinStore.test.ts` -- pin / de-dupe / unpin.
- `src/views/findings/FindingsView.test.tsx` -- loading -> loaded transition,
  headers render, facet dropdown filtering actually changes the row count.

jsdom gaps worth knowing about (handled in `src/test/setup.ts`): no
`ResizeObserver` (needed by `@tanstack/react-virtual`), no
`URL.createObjectURL`/`revokeObjectURL` and no working `<canvas>` context
(both needed because `plotly.js` runs browser feature-detection at *import*
time, not just render time -- any test file that pulls in a view importing
`PlotlyChart` needs these polyfills or the import itself throws). All three
are stubbed globally in the Vitest setup file.

## Open questions / follow-ups for later waves

1. Production bundle is dominated by Plotly (~5.2MB / 1.6MB gzip single
   chunk). Recommend code-splitting per-view Plotly usage with `React.lazy`
   once there's a second view to split against meaningfully.
2. `GeneviewCanvas` renders one `<svg>` per layer; export-quality "capture
   the whole stack" needs a unified `<svg>` with layered `<g>` groups --
   flagged inline in the component, not solved here (explicitly a later-wave
   task per the task brief).
3. `RunQc.config_diff`'s shape (`Record<string, {resolved, default}>`) is a
   guess pending the E2 manifest's actual resolved-config format.
4. The DetailPanel/PinTray "click PAS in TopBar search result" path fetches
   via `api.getPas`/`api.getCell` directly (bypassing React Query hooks)
   since it's a one-off imperative lookup on click, not a rendered query --
   worth revisiting once search results carry richer payloads from a real
   backend and don't need a follow-up fetch at all.
