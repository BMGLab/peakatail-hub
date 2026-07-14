# peakatail-hub — design spec (frontend cockpit + backend read layer)

Status: **approved design**, entering implementation. Companion to the engine-side
plan `PeakATail/reports/PeakATail_Architecture_and_Implementation_Plan.md`.

## 0. Decisions locked (from brainstorming)

| # | Decision |
|---|---|
| Stack | **FastAPI (Python 3.12) + React/Vite/TS SPA + DuckDB.** Not a Python data-app. |
| North star | **Analyst's exploration cockpit** (power-user, dense, interactive). Landing = Findings browser. |
| Comparison | **Faceted single pool + pin-to-compare** side-by-side (not a separate silo). |
| Actions | **Read-only for data + render-on-demand** into the hub's own cache. Never writes run dirs. |
| Export | Every figure exports **high-DPI PNG + vector SVG**. SVG kept as source end-to-end. |
| Framework | **React** (TanStack Table + Query, react-plotly, Zustand). |
| Geneview | **Interactive custom canvas/SVG renderer** (centerpiece); Plotly for surrounding charts. |
| Coverage | v1 = **PAS stems** split by cluster/celltype (approach A). True bigWig coverage = **roadmap B**. |
| Data rule | **Never trim/downsample.** Index everything; window-load only what's in view (LOD/tiling), fetch more on scroll/zoom. |
| Auth | v1 = **local single-user, no auth**. Auth/sharing added when it becomes a web app. |
| Coupling | Engine ↔ hub coupled ONLY by `peakatail-contract` (schemas + IDs + `Run` read-facade). |

## 1. Interactive geneview (centerpiece)

One gene, shared genomic x-axis, a stack of independent toggleable layers:
1. **Ruler + gene model** (exons/introns/3′UTR, strand arrow) — always on.
2. **PAS stems** — each PAS a stick at its 3′-end; height = read count in selected
   cluster/celltype; color-by cluster|celltype; multi-select which render.
3. **`switch diff` overlays** — one sub-row per strategy (fisher / nb_pairwise /
   nb_multi); tick per called PAS encoding q + delta_proportion; each strategy
   enable/disable; filter `q ≤ slider`, "significant only".
4. **`switch length` overlays** — one sub-row per strategy (classic / proportion /
   shannon); shorten/lengthen/flat direction; each toggleable; filter by direction.
5. **Coverage lane** — reserved; filled per-cluster curve (roadmap B); hidden v1.
6. **★ Agreement highlight** — emphasize PAS called by ≥N strategies (concordance).

**Interaction:** zoom (scroll/box), pan (drag), reset-to-gene-span, coordinate
search. Windowed range fetch: only features in visible `[chrom,start,end]` at the
current LOD; toggling one layer never refetches the others. Hover PAS → tooltip;
click PAS → detail panel with full metadata (pas_uid, coords/strand, gene, tier,
gene/snap distance + atlas provenance from ledger, per-cluster counts+proportions,
per-strategy diff q/Δ/log2fc + length direction). Click gene/exon → gene detail.
Export current view → PNG (high-DPI) + SVG.

**Renderer:** custom. Layers: `CoordinateScale`, `Ruler`, `GeneModelLayer`,
`PASStemLayer`, `DiffOverlayLayer`, `LengthOverlayLayer`, `CoverageLayer` (stub),
`LayerPanel`, `GeneviewCanvas`, `useGeneviewWindow`, `ExportButton`.

## 2. App shell + views

Top bar (global search gene/pas_uid/barcode · scope selector · pin tray · settings),
left nav, shared right **detail panel** (PAS/gene/cell + actions: geneview, trace
provenance, pin), pin tray.

1. **Findings browser (landing)** — virtualized server-paged TanStack table ←
   DuckDB. Facets: arm·strategy·celltype·direction·utr_class·q·min_reads. **Caveat
   flags inline** (omnibus double-dip, width-confound, atlas-circularity). Row →
   gene; multi-select → pin.
2. **Gene detail / geneview** — §1 + Plotly companions (PDUI-by-stage line, isoform
   table, PAS list w/ provenance, cross-arm aggregate).
3. **UMAP / celltype explorer** — reuse package embeddings; Plotly scattergl recolor
   by leiden/celltype/stage/sample; spatial-tiling window-load (no point-dropping);
   marker→celltype table.
4. **Run / QC dashboard** — 7-stage drop funnel (stage stats + ledger reconciled),
   config diff, concordance (ARI/AMI), benchmarks.
5. **Provenance / audit** — trace any PAS/cell through the ledger (entered → survived
   thresholds → dropped where/why).
6. **Compare** — pin tray → side-by-side geneview/funnels + "findings in X not Y".

## 3. Data flow + endpoints

`React → TanStack Query → FastAPI → { DuckDB (in-proc) | Run loader → h5ad slice on
drill-down | render cache (~/.peakatail-hub/cache, LRU, never writes run dirs) }`.

Windowed loading: tables (SQL filter/sort/facet-count + cursor pagination + virtual
scroll); geneview (range endpoint + LOD); UMAP (bbox+LOD tiles). Full fidelity,
nothing trimmed; facet counts always show true totals.

Endpoints: `/runs`, `/runs/{id}/qc`; `/findings?…&cursor&limit`, `/findings/facets`,
`/findings/{id}`; `/genes/{id}`, **`/genes/{id}/geneview-data?start&end&lod&clusters&
diff_strategies&length_strategies`**, `/genes/{id}/geneview.svg|.png`,
`/genes/{id}/counts`; `/pas/{id}`, `/pas/{id}/provenance`, `/cells/{id}`,
`/cells/{id}/provenance`; `/datasets/{id}/umap?color&bbox&lod`; `/concordance`,
`/benchmarks`, `/search?q`.

## 4. Modules + repo boundary

Frontend `app/`, `lib/api` (generated from OpenAPI), `lib/contract` (TS types from
contract JSON Schema), `views/{findings,gene/geneview,umap,qc,audit,compare}`,
`state/` (Zustand), `charts/`, `export/`.

Backend `api/` routers, `index/` (`hub index`), `store/` (DuckDB + range/tile),
`render/` (on-demand + LRU cache).

**Boundary:** engine writes contract artifacts; hub reads them. Both depend only on
`peakatail-contract`. Refinement: the **`Run` read-facade lives in the contract
package**, so the hub never depends on the full engine (no pysam/scanpy in the web
service).

## 5. States, errors, testing

States per view: loading/empty-for-filter (≠ not-indexed)/error/streaming/stale.
Fail loud: contract-version mismatch banner; missing artifact → "coordinates
unavailable" not blank; render failure → fallback to static package SVG; caveat
flags surfaced not hidden.

Testing: contract round-trip (engine writes → validate → hub reads) + integrity
invariant `rows(pas_ledger where dropped_at="") == n_vars(clusters.h5ad)`; backend
API against fixture DuckDB; indexer (validate/keys/idempotent); range/tile assert
full counts reconcile (nothing trimmed); render-cache hit/miss + never-writes-run-dir;
frontend layer-renderer + `useGeneviewWindow` + export snapshot.

## 6. Build order

1. `peakatail-contract` v0 (models + IDs + validate + **fixtures**). 2. Backend skeleton
(FastAPI + DuckDB store + routers + indexer). 3. Frontend shell + findings + detail
panel. 4. Geneview renderer + `geneview-data`. 5. UMAP/QC/audit. 6. Compare +
render-on-demand + export polish.

---

## 7. Review resolutions (SUPERSEDES anything above that conflicts)

Validated by architect review 2026-07-12; verdict ready-with-caveats. These are binding.

### 7a. Package boundary — split the reader out of the contract
- `peakatail-contract` is **schema-only**: pydantic models, ID grammar, `validate()`,
  and **fixtures**. **Zero heavy deps** (no anndata/h5py/scipy/scanpy/pysam).
- The h5ad/mtx/bed **reader (the `Run` facade) moves to a separate `peakatail-io`
  package** (or `peakatail-contract[io]` optional-extra) with **lazy imports** of
  anndata/scipy *inside* the counts-drilldown functions only. FastAPI imports the
  heavy reader on exactly one path (`/genes/{id}/counts`, raw PAS/cell). Every
  DuckDB-backed endpoint stays dep-light. (Reconciles with engine E4, which put the
  facade engine-side: the shared reader lives in `peakatail-io`, depended on by hub
  and — later — the engine.)

### 7b. Fixtures-first — the whole hub builds against fixtures
Ship a **complete fixture run** in `peakatail-contract` (manifest + pas/cell ledgers +
findings_long + length_long + a tiny `clusters.h5ad` + pasbed) as **step 1**. Every
hub feature (indexer, DuckDB store, all endpoints, all six views, the geneview
renderer) builds and tests against fixtures **in parallel** with the engine work.
Only "index a real run dir" is gated on the engine. Use one real Laughney
`clusters.h5ad` to validate the h5ad read path early.

### 7c. Engine→hub dependency gates (do NOT point these at real runs until the engine change lands; build on fixtures now)
| Hub feature | Blocked on |
|---|---|
| Findings `direction`/`utr_class` cols+facets | **E5** (+D8 direction) |
| Findings `celltype` facet | **A1** (+A2/B2 labels) |
| Findings correct per-finding coords | **B4** |
| Geneview diff overlays (q/Δ per strategy) | **B4** coords + **E1** stable join |
| Geneview length overlays (per-PAS direction) | **E5** (only `proportion` is per-PAS) |
| Geneview agreement highlight (≥N strategies) | **E1** + **E5** |
| PAS detail tier/gene-dist/snap-dist | **E3** ledger |
| Provenance/audit view (+ cell side) | **E3** (+**B3**) |
| QC 7-stage funnel | **B5** multi-sample stats (+**E3**) |
| Config diff | **B0** resolved config (+**E2**) |
| UMAP recolor by celltype/stage/sample | **A1**+**A2/B2**+**B7** |
| Cross-sample compare by cluster | **B6** canonical_cluster |
| Global search by pas_uid | **E1** |
| Indexer over real run dirs | **E2** manifest (+**E1**) |

Immediately real-run-capable: **UMAP recolor by leiden** + reading a raw `clusters.h5ad`.

### 7d. Correctness defenses the hub MUST implement when reading real runs
- **Join on `var_names`, never `var['gene_id']`** (the column is ~59% NaN — B7). The
  round-trip test asserts this, not just the `n_vars` count.
- **Resolve arm/celltype via the manifest `stratum_to_label` map, never the 48-char
  truncated directory name** (D10).
- **Use the indexer-minted `pas_uid` (chrom:end:strand), never raw `pas_id`** (run-local,
  strand-colliding — B1/E1) for search and all cross-strategy joins.
- **Config-diff reads the resolved config from the E2 manifest**, not `run_config.json`
  (which records argparse defaults — B0).
- **Source PAS coordinates from `pasbed.bed`/manifest**, never the coord columns in
  `switch diff` TSVs (blank until B4).
- **Cross-sample compare/UMAP-by-leiden** mixes clusters across samples until B6
  round-trips `canonical_cluster` — gate it.

### 7e. Data caveats to surface as flags (like the stats caveats)
- **Reads are NOT UMI-deduplicated** → PAS-stem height / counts are molecule-inflated. Flag it.
- **`obs['n_genes']` is PAS-per-cell, not genes** — never label it "genes" in cell detail/QC.

### 7f. UMAP renderer — simplify
For 25k–100k cells, render the **full point set in one Plotly `scattergl` trace** (WebGL
is fine to ~500k) — satisfies "never drop points" without the bbox+LOD tiling, which is
**premature** and fights Plotly. Keep bbox as a *fetch-detail-on-zoom* optimization only.
Document a cutover to **deck.gl / server-side datashader raster tiles** only past ~500k
cells. Geneview window-load stays (trivial), but LOD there is optional (tens–hundreds of
PAS/gene).

### 7g. `finding_uid` minting
Mint from the **manifest-resolved label + `var_names`**, not raw `celltype`/`gene_id`
strings (truncation D10 + NaN B7 would collide/break it).
