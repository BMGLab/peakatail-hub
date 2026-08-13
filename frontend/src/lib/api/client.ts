// Interim typed API client.
//
// USE_MOCKS controls whether calls resolve against in-memory fixtures
// (src/lib/api/mockData.ts) or hit the real FastAPI backend. Default is
// mocks-on until the backend package lands; flip via VITE_USE_MOCKS=false
// in a .env file, or import.meta.env at build time. Swapping a single hook
// from mock to real fetch is intended to be a one-line change (see the
// `if (USE_MOCKS)` branches below — the real branch is stubbed with a
// `fetchJson` helper ready to point at the API base URL).
import type {
  BackendSearchResults,
  CellDetail,
  CellLedgerRow,
  FindingRow,
  GeneListRow,
  GeneSummary,
  GeneviewClusterTrack,
  GeneviewIsoform,
  GeneviewLayerData,
  GeneviewRenderMeta,
  LengthRow,
  PasDetail,
  PasLedgerRow,
  RunQc,
  RunSummary,
  SearchResult,
  Source,
  SourceScanReport,
  SourceScanResult,
  StubResponse,
  SwitchNbMultiRow,
  SwitchResults,
  SwitchTrendGeneRow,
  UmapPoint,
} from '@lib/contract/types'
import {
  mockBenchmarks,
  mockCells,
  mockCellsPage,
  mockConcordance,
  mockFindings,
  mockGenes,
  mockGenesPage,
  mockGeneviewData,
  mockGeneviewMeta,
  mockPasForGene,
  mockPasPage,
  mockRunQc,
  mockRuns,
  mockSearch,
  mockSources,
  mockSwitchNbMulti,
  mockSwitchResults,
  mockSwitchTrendGenes,
  mockUmap,
} from './mockData'

export const USE_MOCKS: boolean =
  (import.meta.env.VITE_USE_MOCKS ?? 'true') !== 'false'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

async function fetchJson<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(`${API_BASE}${path}`, window.location.origin)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) url.searchParams.set(k, String(v))
    }
  }
  const res = await fetch(url.toString())
  if (!res.ok) {
    throw new Error(`API error ${res.status} for ${path}`)
  }
  return (await res.json()) as T
}

// POST/DELETE variant of fetchJson -- the sources router (add/delete/rescan)
// is the first mutating surface this client talks to (everything else is a
// GET). Surfaces the backend's `detail` message on 4xx (e.g. "Path does not
// exist: ...") rather than a bare status code, since the SOURCES panel needs
// to show that text directly to the user.
async function sendJson<T>(method: 'POST' | 'DELETE', path: string, body?: unknown): Promise<T> {
  const url = new URL(`${API_BASE}${path}`, window.location.origin)
  // `exactOptionalPropertyTypes` forbids assigning an explicit `undefined` to
  // RequestInit's optional `headers`/`body` keys -- omit the keys entirely
  // (via spread) rather than set them to `undefined`, instead of widening
  // RequestInit's own types.
  const init: RequestInit = {
    method,
    ...(body !== undefined ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}),
  }
  const res = await fetch(url.toString(), init)
  if (!res.ok) {
    const detail = await res
      .json()
      .then((j) => (typeof j?.detail === 'string' ? j.detail : null))
      .catch(() => null)
    throw new Error(detail ?? `API error ${res.status} for ${path}`)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

// Simulated network latency so loading states are visible/testable in dev.
function delay<T>(value: T, ms = 120): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

// ---------------------------------------------------------------------------
// Sources (dashboard multi-directory manager) -- mock-mode state.
//
// Every other mock in this file is a pure derivation of static fixture data;
// this is the one surface with real mutations (add/rescan/delete), so it
// needs a live, mutable store. A browser `fetch`-free mock can't actually
// walk a filesystem, so `addMockSource`/`rescanMockSource` never discover
// real runs -- they only exercise the CRUD/error-path UI (empty-path,
// duplicate-path, unknown-id), which is what the SOURCES panel needs to be
// developable without the real backend running.
// ---------------------------------------------------------------------------

let mockSourcesState: Source[] = mockSources.map((s) => ({ ...s }))
let mockSourceCounter = 0

function emptyScanReport(): SourceScanReport {
  return { indexed: [], skipped_unchanged: [], failed: {} }
}

function mockScanSource(source: Source): SourceScanResult {
  source.last_scanned_at = new Date().toISOString()
  source.last_scan_status = 'empty'
  source.last_scan_error = 'No run_manifest.json found anywhere under this path (mock mode never walks a real filesystem).'
  return { source: { ...source }, scan: emptyScanReport() }
}

export interface FindingsParams {
  /** Scopes to one indexed run -- the real deployment has 19+; omitting
   * this used to silently mix every run's findings together (FIX 2026-08-14,
   * see FindingsView's own doc comment on why it now always threads the
   * TopBar Scope selector's run through here). */
  run_id?: string | undefined
  arm?: string
  strategy?: FindingRow['strategy']
  celltype?: string | undefined
  direction?: FindingRow['direction']
  utr_class?: string
  q_max?: number
  min_reads?: number
  // Opaque cursor (base64-encoded offset), per the backend's
  // store/queries.py encode_cursor/decode_cursor. `undefined` means "first
  // page" -- never send a literal 0, decode_cursor() base64-decodes
  // whatever it's given.
  cursor?: string
  limit?: number
}

export interface FindingsPage {
  rows: FindingRow[]
  nextCursor: string | null
  total: number
}

// ---------------------------------------------------------------------------
// Browse: GET /genes, /pas, /cells -- same page-envelope shape as
// FindingsPage above (rows/nextCursor/total, translated from the backend's
// snake_case items/next_cursor/total). Backing the gene/PAS/cell browsers +
// the TopBar location bar's chr:coords -> gene resolution.
// ---------------------------------------------------------------------------

// Optional fields are `T | undefined` (not bare `T?`) so callers can pass an
// explicit `{ q: undefined, run_id: runId ?? undefined }` literal under
// tsconfig's `exactOptionalPropertyTypes` -- the browse views build the param
// object from possibly-undefined state, which a plain `q?: string` rejects.
export interface GenesBrowseParams {
  q?: string | undefined
  /** Locus-overlap filter (not exact-match) -- resolves a raw chr:start-end
   * search to the gene(s) whose span overlaps it. All three optional. */
  chrom?: string | undefined
  start?: number | undefined
  end?: number | undefined
  run_id?: string | undefined
  cursor?: string | undefined
  limit?: number | undefined
}

export interface BrowseParams {
  q?: string | undefined
  run_id?: string | undefined
  cursor?: string | undefined
  limit?: number | undefined
}

export interface GenesBrowsePage {
  rows: GeneListRow[]
  nextCursor: string | null
  total: number
}

export interface PasBrowsePage {
  rows: PasLedgerRow[]
  nextCursor: string | null
  total: number
}

export interface CellsBrowsePage {
  rows: CellLedgerRow[]
  nextCursor: string | null
  total: number
}

interface BackendGenesPage {
  items: GeneListRow[]
  next_cursor: string | null
  total: number
}

interface BackendPasPage {
  items: PasLedgerRow[]
  next_cursor: string | null
  total: number
}

interface BackendCellsPage {
  items: CellLedgerRow[]
  next_cursor: string | null
  total: number
}

// Backend's actual /findings response shape (schemas.py FindingsPage):
// snake_case, `items` not `rows`. Translated to the FindingsPage above
// immediately after fetch so every other module in the frontend only ever
// sees the mock-compatible shape.
interface BackendFindingsPage {
  items: FindingRow[]
  next_cursor: string | null
  total: number
}

interface BackendFacetValue {
  value: string | null
  count: number
}

interface BackendFindingsFacets {
  arm: BackendFacetValue[]
  strategy: BackendFacetValue[]
  celltype: BackendFacetValue[]
  direction: BackendFacetValue[]
  utr_class: BackendFacetValue[]
  total: number
}

export interface FindingsFacets {
  arm: string[]
  strategy: string[]
  celltype: string[]
  direction: string[]
  utr_class: string[]
}

// Backend schemas.py GeneSpan/GeneSummary -- coordinates nested under a
// nullable `span` (null when the gene has zero surviving PAS). `gene_name`
// is now backend-sourced (GTF `gene_name` attribute, see genes.py) but is
// `""` (never null/absent) when no GTF was configured for the run or the
// gene wasn't found in it -- treat empty-string as "unknown", not as a
// signal to trust `gene_id` as a symbol.
interface BackendGeneSpan {
  chrom: string
  start: number
  end: number
  strand: '+' | '-'
  n_pas: number
}

interface BackendGeneSummary {
  gene_id: string
  run_id: string
  gene_name: string
  n_pas: number
  n_findings: number
  n_length_rows: number
  span: BackendGeneSpan | null
}

/** Flattens a wire-shape GeneSummary into the frontend's ergonomic flat
 * shape; `gene_name` falls back to `gene_id` only when the backend's own
 * `gene_name` is empty (no GTF configured / gene not found in it) -- shared
 * by both `getGene` and `getGeneviewData` (the latter's
 * `/genes/{id}/geneview-data` response embeds the same gene_id/span pair,
 * just without n_findings/n_length_rows scoped the same way, which is why
 * that call site passes its own window-scoped counts through). */
function toFrontendGeneSummary(g: BackendGeneSummary): GeneSummary {
  return {
    gene_id: g.gene_id,
    gene_name: g.gene_name || g.gene_id,
    chrom: g.span?.chrom ?? null,
    start: g.span?.start ?? null,
    end: g.span?.end ?? null,
    strand: g.span?.strand ?? null,
    n_pas: g.n_pas,
  }
}

interface BackendGeneviewPas {
  pas_uid: string
  chrom: string
  start: number
  end: number
  strand: '+' | '-'
  unified_pas_id: string
  gene_distance_bp: number | null
  snap_distance_bp: number | null
  tier: string | null
}

interface BackendGeneviewData {
  gene_id: string
  run_id: string
  gene_name: string
  span: BackendGeneSpan | null
  window: { start: number | null; end: number | null }
  pas: BackendGeneviewPas[]
  findings: FindingRow[]
  length_rows: LengthRow[]
  gates: string[]
  isoforms: GeneviewIsoform[]
  cluster_tracks: GeneviewClusterTrack[]
}

// `/pas/{id}` and `/pas/{id}/provenance`'s `.pas` both serialize
// PasLedgerRow directly (same fields as the contract model, pas_uid
// computed) -- no gene_name/per_cluster_counts/umi_deduplicated, the
// PasDetail-only additions.
type BackendPasLedgerRow = Omit<PasDetail, 'gene_name' | 'per_cluster_counts' | 'umi_deduplicated'>

function toFrontendPasDetail(p: BackendPasLedgerRow): PasDetail {
  return {
    ...p,
    gene_name: null, // no Ensembl-id -> symbol mapping in the contract yet
    per_cluster_counts: {}, // not carried by either PAS endpoint (spec §7a heavy-import split)
    umi_deduplicated: false,
  }
}

export const api = {
  getRuns(): Promise<RunSummary[]> {
    if (USE_MOCKS) return delay(mockRuns)
    return fetchJson('/runs')
  },

  getRunQc(runId: string): Promise<RunQc | null> {
    if (USE_MOCKS) return delay(mockRunQc[runId] ?? null)
    return fetchJson(`/runs/${runId}/qc`)
  },

  // -------------------------------------------------------------------------
  // B3_switch results (2026-08-14) -- "cell types -> stages -> genes", the
  // PRIMARY navigation the professor's headline finding (3'UTR shortening
  // across disease stages, per cell type) needs. Backs ResultsView.
  // -------------------------------------------------------------------------

  getRunSwitch(runId: string): Promise<SwitchResults> {
    if (USE_MOCKS) return delay(mockSwitchResults(runId))
    return fetchJson(`/runs/${runId}/switch`)
  },

  getRunSwitchTrendGenes(runId: string, celltype: string, strategy = 'classic', limit = 50): Promise<SwitchTrendGeneRow[]> {
    if (USE_MOCKS) return delay(mockSwitchTrendGenes(celltype, strategy))
    return fetchJson(`/runs/${runId}/switch/${encodeURIComponent(celltype)}/trend-genes`, { strategy, limit })
  },

  /** Per-PAS drill-down behind SwitchCelltypeResult.nb_multi's counts -- a
   * different result grain than fisher (omnibus LRT, no canonical_cluster/
   * direction), not queryable via getFindings. */
  getRunSwitchNbMulti(runId: string, celltype: string, limit = 50): Promise<SwitchNbMultiRow[]> {
    if (USE_MOCKS) return delay(mockSwitchNbMulti(celltype))
    return fetchJson(`/runs/${runId}/switch/${encodeURIComponent(celltype)}/nb-multi`, { limit })
  },

  getFindings(params: FindingsParams): Promise<FindingsPage> {
    if (USE_MOCKS) {
      let rows = mockFindings
      if (params.arm) rows = rows.filter((r) => r.arm === params.arm)
      if (params.strategy) rows = rows.filter((r) => r.strategy === params.strategy)
      if (params.celltype) rows = rows.filter((r) => r.celltype === params.celltype)
      if (params.direction) rows = rows.filter((r) => r.direction === params.direction)
      if (params.utr_class) rows = rows.filter((r) => r.utr_class === params.utr_class)
      // qvalue/n_reads are null for length-strategy rows (no PAS-level test
      // at that grain) -- a q_max/min_reads filter can't confirm those
      // rows satisfy it, so they're excluded rather than ambiguously kept.
      if (params.q_max !== undefined) rows = rows.filter((r) => r.qvalue !== null && r.qvalue <= params.q_max!)
      if (params.min_reads !== undefined) rows = rows.filter((r) => r.n_reads !== null && r.n_reads >= params.min_reads!)
      const total = rows.length
      const offset = params.cursor ? Number(params.cursor) : 0
      const limit = params.limit ?? 100
      const page = rows.slice(offset, offset + limit)
      const nextOffset = offset + limit
      const nextCursor = nextOffset < total ? String(nextOffset) : null
      return delay({ rows: page, nextCursor, total })
    }
    return fetchJson<BackendFindingsPage>('/findings', params as Record<string, string | number | undefined>).then(
      (page) => ({ rows: page.items, nextCursor: page.next_cursor, total: page.total }),
    )
  },

  getFindingsFacets(params: FindingsParams): Promise<FindingsFacets> {
    if (USE_MOCKS) {
      const uniq = (xs: (string | null)[]) => Array.from(new Set(xs.filter((x): x is string => x !== null)))
      return delay({
        arm: uniq(mockFindings.map((r) => r.arm)),
        strategy: uniq(mockFindings.map((r) => r.strategy)),
        celltype: uniq(mockFindings.map((r) => r.celltype)),
        direction: uniq(mockFindings.map((r) => r.direction)),
        utr_class: uniq(mockFindings.map((r) => r.utr_class)),
      })
    }
    // Facets are computed over the currently-applied filters (true full-set
    // counts, spec §3 "not counts of the current page") -- forward every
    // filter param except pagination (cursor/limit have no meaning here).
    const { cursor: _cursor, limit: _limit, ...facetParams } = params
    return fetchJson<BackendFindingsFacets>(
      '/findings/facets',
      facetParams as Record<string, string | number | undefined>,
    ).then((f) => {
      const values = (xs: BackendFacetValue[]) => xs.map((x) => x.value).filter((v): v is string => v !== null)
      return {
        arm: values(f.arm),
        strategy: values(f.strategy),
        celltype: values(f.celltype),
        direction: values(f.direction),
        utr_class: values(f.utr_class),
      }
    })
  },

  getFinding(id: string): Promise<FindingRow | null> {
    if (USE_MOCKS) return delay(mockFindings.find((f) => f.finding_uid === id) ?? null)
    return fetchJson(`/findings/${id}`)
  },

  // `run_id` is REQUIRED once more than one run is indexed (backend
  // genes.py `_resolve_run_id` 400s rather than guess) -- both callers
  // thread the TopBar Scope selector's `useScopeStore().runId` through
  // (see GeneView.tsx), so a real multi-run/multi-source deployment (the
  // dashboard's SOURCES manager can register >1) never silently 400s the
  // geneview centerpiece just because a second run exists.
  getGene(id: string, runId?: string): Promise<GeneSummary | null> {
    if (USE_MOCKS) return delay(mockGenes.find((g) => g.gene_id === id) ?? null)
    return fetchJson<BackendGeneSummary>(`/genes/${id}`, { run_id: runId }).then(toFrontendGeneSummary)
  },

  getGeneviewData(
    id: string,
    params?: {
      start?: number | undefined
      end?: number | undefined
      lod?: number | undefined
      clusters?: string[] | undefined
      diff_strategies?: string[] | undefined
      length_strategies?: string[] | undefined
      run_id?: string | undefined
    },
  ): Promise<GeneviewLayerData | null> {
    if (USE_MOCKS) return delay(mockGeneviewData(id))
    return fetchJson<BackendGeneviewData>(`/genes/${id}/geneview-data`, {
      start: params?.start,
      end: params?.end,
      run_id: params?.run_id,
    }).then((r) => ({
      gene: toFrontendGeneSummary({
        gene_id: r.gene_id,
        run_id: r.run_id,
        gene_name: r.gene_name,
        n_pas: r.pas.length,
        n_findings: r.findings.length,
        n_length_rows: r.length_rows.length,
        span: r.span,
      }),
      window: { chrom: r.span?.chrom ?? null, start: r.window.start, end: r.window.end },
      // GeneviewPas has no per_cluster_counts on the wire (spec §7a: the
      // heavy /genes/{id}/counts join is a separate endpoint) -- default to
      // {} (flat stems) rather than fabricate numbers; PASStemLayer/
      // DetailPanel both degrade gracefully on an empty object.
      pas: r.pas.map((p) => ({ ...p, per_cluster_counts: {} })),
      diff: r.findings,
      length: r.length_rows,
      coverage: null,
      gates: r.gates,
      isoforms: r.isoforms,
      clusterTracks: r.cluster_tracks,
    }))
  },

  getGeneCounts(id: string): Promise<PasDetail[]> {
    if (USE_MOCKS) return delay(mockPasForGene(id))
    return fetchJson(`/genes/${id}/counts`)
  },

  // -------------------------------------------------------------------------
  // Real ema geneview (2026-08-14) -- GeneView embeds these two figure
  // endpoints directly (iframe/img `src`, not fetched through this client)
  // once getGeneviewMeta confirms the figure is generated/cached; see
  // geneviewHtmlUrl/geneviewPngUrl below and GeneView.tsx.
  // -------------------------------------------------------------------------

  /** Triggers on-demand generation (~10-25s on a cold cache; the backend
   * itself retries across a few datasets if the first pick has no PAS for
   * this gene -- see api/geneview.py) and returns metadata + the real
   * PAS-distance table once the figure is ready/cached. GeneView awaits
   * this BEFORE pointing the iframe/img at geneviewHtmlUrl/geneviewPngUrl,
   * so those always hit an already-warm cache (near-instant) rather than
   * racing a cold render with no loading indicator. */
  getGeneviewMeta(id: string, runId?: string, datasetId?: string): Promise<GeneviewRenderMeta | null> {
    if (USE_MOCKS) return delay(mockGeneviewMeta(id))
    return fetchJson<GeneviewRenderMeta>(`/genes/${id}/geneview/meta`, { run_id: runId, dataset_id: datasetId })
  },

  getPas(id: string): Promise<PasDetail | null> {
    if (USE_MOCKS) {
      for (const g of mockGenes) {
        const found = mockPasForGene(g.gene_id).find((p) => p.pas_uid === id)
        if (found) return delay(found)
      }
      return delay(null)
    }
    // /pas/{id} returns a plain PasLedgerRow (schemas.py response_model) --
    // no gene_name/per_cluster_counts/umi_deduplicated, the PasDetail-only
    // fields. Fill them in the same way getPasProvenance does below.
    return fetchJson<BackendPasLedgerRow>(`/pas/${id}`).then(toFrontendPasDetail).catch(() => null)
  },

  getPasProvenance(id: string): Promise<PasDetail | null> {
    if (USE_MOCKS) return api.getPas(id)
    // /pas/{id}/provenance wraps it in {pas, findings, length_rows, trail}
    // (schemas.py PasProvenance) -- not a flat PasDetail. Unwrap `.pas`;
    // findings/length_rows/trail aren't surfaced by AuditView today (it
    // only needs the ledger row + StageStepper), left for a future pass.
    return fetchJson<{ pas: BackendPasLedgerRow }>(`/pas/${id}/provenance`)
      .then((r) => toFrontendPasDetail(r.pas))
      .catch(() => null)
  },

  getCell(id: string): Promise<CellDetail | null> {
    if (USE_MOCKS) return delay(mockCells.find((c) => c.cell_uid === id) ?? null)
    return fetchJson<CellDetail>(`/cells/${id}`)
      .then((c) => ({ ...c, celltype: null }))
      .catch(() => null)
  },

  getCellProvenance(id: string): Promise<CellDetail | null> {
    if (USE_MOCKS) return api.getCell(id)
    // /cells/{id}/provenance wraps it in {cell, length_rows, trail}
    // (schemas.py CellProvenance) -- unwrap `.cell`. `celltype` is always
    // null: not populated until engine A1 (+A2/B2), spec §7c.
    return fetchJson<{ cell: CellDetail }>(`/cells/${id}/provenance`)
      .then((r) => ({ ...r.cell, celltype: null }))
      .catch(() => null)
  },

  getUmap(_datasetId: string, params?: { color?: string; bbox?: [number, number, number, number]; lod?: number }): Promise<UmapPoint[]> {
    if (USE_MOCKS) return delay(mockUmap)
    // Backend wraps points in `{run_id, color, n_points, points}` (schemas.py
    // UmapResponse), not a bare array -- and 501s with a structured
    // `{available:false,...}` body (not `points`) when `color` isn't gated
    // in yet (spec §7c: celltype/stage/sample need engine A1/A2/B2/B7).
    return fetchJson<{ points?: UmapPoint[]; available?: false }>(`/datasets/${_datasetId}/umap`, {
      color: params?.color,
    }).then((r) => r.points ?? [])
  },

  // Backend's `run_id` query param is REQUIRED on both of these (no
  // contract schema for either artifact exists yet, spec §5.5 -- the
  // response is always a single `{run_id, available: false, note}` stub,
  // never a per-pair/per-metric array; the earlier ConcordanceSummary[]/
  // BenchmarkSummary[] return types never matched a real response and
  // omitting run_id 422'd every call).
  getConcordance(runId: string): Promise<StubResponse> {
    if (USE_MOCKS) return delay(mockConcordance[runId] ?? { run_id: runId, available: false, note: 'no mock data for this run' })
    return fetchJson('/concordance', { run_id: runId })
  },

  getBenchmarks(runId: string): Promise<StubResponse> {
    if (USE_MOCKS) return delay(mockBenchmarks[runId] ?? { run_id: runId, available: false, note: 'no mock data for this run' })
    return fetchJson('/benchmarks', { run_id: runId })
  },

  search(q: string): Promise<SearchResult[]> {
    if (USE_MOCKS) return delay(mockSearch(q), 60)
    // Backend returns three separately-typed arrays (`{q, genes, pas,
    // cells}`, schemas.py SearchResults), not a unified SearchResult[] --
    // fold them into the frontend's normalized shape here, the one place
    // that needs to know about the wire format.
    return fetchJson<BackendSearchResults>('/search', { q }).then((r) => [
      ...r.genes.map((g) => ({ kind: 'gene' as const, id: g.gene_id, label: g.gene_id, sublabel: null })),
      ...r.pas.map((p) => ({ kind: 'pas' as const, id: p.pas_uid, label: p.pas_uid, sublabel: p.gene_id || null })),
      ...r.cells.map((c) => ({ kind: 'cell' as const, id: c.cell_uid, label: c.cell_uid, sublabel: c.dataset_id })),
    ])
  },

  // -------------------------------------------------------------------------
  // Browse: the gene/PAS/cell browsers (searchable, paginated, virtualized
  // lists -- see views/browse/**) plus the TopBar location bar's chr:coords
  // resolution (listGenes with chrom/start/end set, no `q`).
  // -------------------------------------------------------------------------

  listGenes(params: GenesBrowseParams): Promise<GenesBrowsePage> {
    if (USE_MOCKS) return delay(mockGenesPage(params))
    return fetchJson<BackendGenesPage>('/genes', params as Record<string, string | number | undefined>).then((p) => ({
      rows: p.items,
      nextCursor: p.next_cursor,
      total: p.total,
    }))
  },

  listPas(params: BrowseParams): Promise<PasBrowsePage> {
    if (USE_MOCKS) return delay(mockPasPage(params))
    return fetchJson<BackendPasPage>('/pas', params as Record<string, string | number | undefined>).then((p) => ({
      rows: p.items,
      nextCursor: p.next_cursor,
      total: p.total,
    }))
  },

  listCells(params: BrowseParams): Promise<CellsBrowsePage> {
    if (USE_MOCKS) return delay(mockCellsPage(params))
    return fetchJson<BackendCellsPage>('/cells', params as Record<string, string | number | undefined>).then((p) => ({
      rows: p.items,
      nextCursor: p.next_cursor,
      total: p.total,
    }))
  },

  // -------------------------------------------------------------------------
  // Sources: the dashboard's multi-directory SOURCES manager. Every PeakATail
  // run output lives in some directory somewhere -- registering a directory
  // here walks it (existing indexer, arbitrary depth) and merges every run it
  // finds into the one shared DuckDB store. See backend/src/peakatail_hub/
  // api/sources.py for the exact semantics (idempotent by resolved path,
  // 'empty'/'ok'/'error' scan status, delete cascades the runs it owns).
  // -------------------------------------------------------------------------

  getSources(): Promise<Source[]> {
    if (USE_MOCKS) return delay(mockSourcesState.map((s) => ({ ...s })))
    return fetchJson('/sources')
  },

  addSource(path: string, label?: string): Promise<SourceScanResult> {
    if (USE_MOCKS) {
      const trimmed = path.trim()
      if (!trimmed) return Promise.reject(new Error('path must not be empty'))
      const existing = mockSourcesState.find((s) => s.path === trimmed)
      if (existing) return delay(mockScanSource(existing))
      mockSourceCounter += 1
      const source: Source = {
        source_id: `src_mock_new_${mockSourceCounter}`,
        path: trimmed,
        label: label ?? null,
        added_at: new Date().toISOString(),
        last_scanned_at: null,
        last_scan_status: null,
        last_scan_error: null,
        run_count: 0,
      }
      mockSourcesState = [...mockSourcesState, source]
      return delay(mockScanSource(source))
    }
    return sendJson('POST', '/sources', { path, label })
  },

  deleteSource(sourceId: string): Promise<void> {
    if (USE_MOCKS) {
      const before = mockSourcesState.length
      mockSourcesState = mockSourcesState.filter((s) => s.source_id !== sourceId)
      if (mockSourcesState.length === before) return Promise.reject(new Error(`source_id=${sourceId} not registered`))
      return delay(undefined)
    }
    return sendJson('DELETE', `/sources/${sourceId}`)
  },

  rescanSource(sourceId: string): Promise<SourceScanResult> {
    if (USE_MOCKS) {
      const source = mockSourcesState.find((s) => s.source_id === sourceId)
      if (!source) return Promise.reject(new Error(`source_id=${sourceId} not registered`))
      return delay(mockScanSource(source))
    }
    return sendJson('POST', `/sources/${sourceId}/rescan`)
  },

  rescanAllSources(): Promise<SourceScanResult[]> {
    if (USE_MOCKS) return delay(mockSourcesState.map((s) => mockScanSource(s)))
    return sendJson<{ sources: SourceScanResult[] }>('POST', '/sources/rescan-all').then((r) => r.sources)
  },
}

// ---------------------------------------------------------------------------
// Real ema geneview -- served by a SEPARATE host-side microservice
// (geneview_svc.py, per-celltype renders, plotly+matplotlib+distance table,
// on-demand + cached), reached via a same-origin nginx proxy at
// `/geneview/*` (NOT under API_BASE/`/api` -- a sibling location block,
// wired by whoever deploys the frontend). Exported as a plain URL builder
// (not an `api.*` method that fetches/parses a body) because GeneView hands
// this straight to an <iframe src>/<img src>, which does its own request/
// loading outside this client -- the first (uncached) render takes ~15s,
// during which the browser just shows its native "loading" affordance for
// that element; GeneView pairs this with an explicit loading message of its
// own rather than relying on that alone.
// ---------------------------------------------------------------------------

export interface GeneviewRenderParams {
  run: string
  celltype: string
  gene: string
  engine: 'plotly' | 'matplotlib'
  /** obs column driving cluster grouping -- 'stage' (disease stage, the
   * professor's headline axis) or 'leiden' (raw per-dataset cluster). */
  cluster_key?: string | undefined
  /** obs column to additionally tint tracks by (e.g. a condition/sample axis). */
  color_key?: string | undefined
  pas_distance_table?: boolean | undefined
}

export function geneviewRenderUrl(params: GeneviewRenderParams): string {
  const qs = new URLSearchParams()
  qs.set('run', params.run)
  qs.set('celltype', params.celltype)
  qs.set('gene', params.gene)
  qs.set('engine', params.engine)
  if (params.cluster_key) qs.set('cluster_key', params.cluster_key)
  if (params.color_key) qs.set('color_key', params.color_key)
  if (params.pas_distance_table !== undefined) qs.set('pas_distance_table', String(params.pas_distance_table))
  return `/geneview/render?${qs.toString()}`
}

export type GeneviewCheckResult =
  | { ok: true }
  | { ok: false; status: number; message: string }

/**
 * Pre-flight check for `geneviewRenderUrl` (2026-08-14) -- GeneView calls
 * this BEFORE pointing the <iframe>/<img> `src` at the render URL, so it
 * can tell a genuine "no PAS for this gene in this cell type" (a common,
 * legitimate case -- the renderer returns a clean 404 with a plain-text
 * body like "gene <id> has no PAS expressed in cell type <ct> — no APA
 * data to plot here.") apart from a real failure, and render a friendly
 * empty state instead of a broken/blank iframe or a scary error banner.
 * This request is what actually triggers on-demand generation on a
 * cache-miss (~15s) -- the iframe/img src that follows on success always
 * hits an already-warm cache.
 */
/** Pure `Response -> GeneviewCheckResult` mapping, split out from
 * `checkGeneviewRender` so it's unit-testable against a constructed
 * `Response` directly -- `checkGeneviewRender` itself short-circuits to
 * `{ok: true}` under USE_MOCKS (no real service to hit in mock mode), which
 * would otherwise make the parsing logic here untestable in this repo's
 * mocks-on-by-default test setup. */
export async function parseGeneviewCheckResponse(res: Response): Promise<GeneviewCheckResult> {
  if (res.ok) return { ok: true }
  const text = await res.text().catch(() => '')
  return { ok: false, status: res.status, message: text.trim() || `Failed to generate geneview (HTTP ${res.status}).` }
}

export async function checkGeneviewRender(url: string): Promise<GeneviewCheckResult> {
  if (USE_MOCKS) return { ok: true } // nothing real to check under mocks -- see geneviewRenderUrl's doc comment
  try {
    return await parseGeneviewCheckResponse(await fetch(url))
  } catch (err) {
    return { ok: false, status: 0, message: err instanceof Error ? err.message : String(err) }
  }
}
