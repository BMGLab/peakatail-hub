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
  FindingRow,
  GeneSummary,
  GeneviewLayerData,
  LengthRow,
  PasDetail,
  RunQc,
  RunSummary,
  SearchResult,
  StubResponse,
  UmapPoint,
} from '@lib/contract/types'
import {
  mockBenchmarks,
  mockCells,
  mockConcordance,
  mockFindings,
  mockGenes,
  mockGeneviewData,
  mockPasForGene,
  mockRunQc,
  mockRuns,
  mockSearch,
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

// Simulated network latency so loading states are visible/testable in dev.
function delay<T>(value: T, ms = 120): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

export interface FindingsParams {
  arm?: string
  strategy?: FindingRow['strategy']
  celltype?: string
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
// nullable `span` (null when the gene has zero surviving PAS), no
// `gene_name` field at all (no Ensembl-id -> symbol mapping in the
// contract yet).
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
  n_pas: number
  n_findings: number
  n_length_rows: number
  span: BackendGeneSpan | null
}

/** Flattens a wire-shape GeneSummary into the frontend's ergonomic flat
 * shape; `gene_name` falls back to `gene_id` (no symbol mapping exists
 * yet) -- shared by both `getGene` and `getGeneviewData` (the latter's
 * `/genes/{id}/geneview-data` response embeds the same gene_id/span pair,
 * just without n_findings/n_length_rows scoped the same way, which is why
 * that call site passes its own window-scoped counts through). */
function toFrontendGeneSummary(g: BackendGeneSummary): GeneSummary {
  return {
    gene_id: g.gene_id,
    gene_name: g.gene_id,
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
  span: BackendGeneSpan | null
  window: { start: number | null; end: number | null }
  pas: BackendGeneviewPas[]
  findings: FindingRow[]
  length_rows: LengthRow[]
  gates: string[]
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

  getFindings(params: FindingsParams): Promise<FindingsPage> {
    if (USE_MOCKS) {
      let rows = mockFindings
      if (params.arm) rows = rows.filter((r) => r.arm === params.arm)
      if (params.strategy) rows = rows.filter((r) => r.strategy === params.strategy)
      if (params.celltype) rows = rows.filter((r) => r.celltype === params.celltype)
      if (params.direction) rows = rows.filter((r) => r.direction === params.direction)
      if (params.utr_class) rows = rows.filter((r) => r.utr_class === params.utr_class)
      if (params.q_max !== undefined) rows = rows.filter((r) => r.qvalue <= params.q_max!)
      if (params.min_reads !== undefined) rows = rows.filter((r) => r.n_reads >= params.min_reads!)
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

  getGene(id: string): Promise<GeneSummary | null> {
    if (USE_MOCKS) return delay(mockGenes.find((g) => g.gene_id === id) ?? null)
    return fetchJson<BackendGeneSummary>(`/genes/${id}`).then(toFrontendGeneSummary)
  },

  getGeneviewData(
    id: string,
    params?: { start?: number; end?: number; lod?: number; clusters?: string[]; diff_strategies?: string[]; length_strategies?: string[] },
  ): Promise<GeneviewLayerData | null> {
    if (USE_MOCKS) return delay(mockGeneviewData(id))
    return fetchJson<BackendGeneviewData>(`/genes/${id}/geneview-data`, {
      start: params?.start,
      end: params?.end,
    }).then((r) => ({
      gene: toFrontendGeneSummary({ gene_id: r.gene_id, run_id: r.run_id, n_pas: r.pas.length, n_findings: r.findings.length, n_length_rows: r.length_rows.length, span: r.span }),
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
    }))
  },

  getGeneCounts(id: string): Promise<PasDetail[]> {
    if (USE_MOCKS) return delay(mockPasForGene(id))
    return fetchJson(`/genes/${id}/counts`)
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
}
