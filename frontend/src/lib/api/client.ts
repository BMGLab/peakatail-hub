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
  BenchmarkSummary,
  CellDetail,
  ConcordanceSummary,
  FindingRow,
  GeneSummary,
  GeneviewLayerData,
  PasDetail,
  RunQc,
  RunSummary,
  SearchResult,
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
  cursor?: number
  limit?: number
}

export interface FindingsPage {
  rows: FindingRow[]
  nextCursor: number | null
  total: number
}

export interface FindingsFacets {
  arm: string[]
  strategy: string[]
  celltype: string[]
  direction: string[]
  utr_class: string[]
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
      const cursor = params.cursor ?? 0
      const limit = params.limit ?? 100
      const page = rows.slice(cursor, cursor + limit)
      const nextCursor = cursor + limit < total ? cursor + limit : null
      return delay({ rows: page, nextCursor, total })
    }
    return fetchJson('/findings', params as Record<string, string | number | undefined>)
  },

  getFindingsFacets(_params: FindingsParams): Promise<FindingsFacets> {
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
    return fetchJson('/findings/facets')
  },

  getFinding(id: string): Promise<FindingRow | null> {
    if (USE_MOCKS) return delay(mockFindings.find((f) => f.finding_uid === id) ?? null)
    return fetchJson(`/findings/${id}`)
  },

  getGene(id: string): Promise<GeneSummary | null> {
    if (USE_MOCKS) return delay(mockGenes.find((g) => g.gene_id === id) ?? null)
    return fetchJson(`/genes/${id}`)
  },

  getGeneviewData(
    id: string,
    _params?: { start?: number; end?: number; lod?: number; clusters?: string[]; diff_strategies?: string[]; length_strategies?: string[] },
  ): Promise<GeneviewLayerData | null> {
    if (USE_MOCKS) return delay(mockGeneviewData(id))
    return fetchJson(`/genes/${id}/geneview-data`)
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
    return fetchJson(`/pas/${id}`)
  },

  getPasProvenance(id: string): Promise<PasDetail | null> {
    if (USE_MOCKS) return api.getPas(id)
    return fetchJson(`/pas/${id}/provenance`)
  },

  getCell(id: string): Promise<CellDetail | null> {
    if (USE_MOCKS) return delay(mockCells.find((c) => c.cell_uid === id) ?? null)
    return fetchJson(`/cells/${id}`)
  },

  getCellProvenance(id: string): Promise<CellDetail | null> {
    if (USE_MOCKS) return api.getCell(id)
    return fetchJson(`/cells/${id}/provenance`)
  },

  getUmap(_datasetId: string, _params?: { color?: string; bbox?: [number, number, number, number]; lod?: number }): Promise<UmapPoint[]> {
    if (USE_MOCKS) return delay(mockUmap)
    return fetchJson(`/datasets/${_datasetId}/umap`)
  },

  getConcordance(): Promise<ConcordanceSummary[]> {
    if (USE_MOCKS) return delay(mockConcordance)
    return fetchJson('/concordance')
  },

  getBenchmarks(): Promise<BenchmarkSummary[]> {
    if (USE_MOCKS) return delay(mockBenchmarks)
    return fetchJson('/benchmarks')
  },

  search(q: string): Promise<SearchResult[]> {
    if (USE_MOCKS) return delay(mockSearch(q), 60)
    return fetchJson('/search', { q })
  },
}
