// TanStack Query hooks wrapping lib/api/client.ts. Views should import these,
// never `api` directly, so query-key/caching/staleness policy lives in one
// place. Swapping mocks -> real backend happens inside client.ts; these hooks
// don't change.
import { useQuery } from '@tanstack/react-query'
import { api, type FindingsParams } from './client'

export function useRuns() {
  return useQuery({ queryKey: ['runs'], queryFn: api.getRuns })
}

export function useRunQc(runId: string | null) {
  return useQuery({
    queryKey: ['runQc', runId],
    queryFn: () => api.getRunQc(runId!),
    enabled: runId !== null,
  })
}

export function useFindings(params: FindingsParams) {
  return useQuery({
    queryKey: ['findings', params],
    queryFn: () => api.getFindings(params),
    placeholderData: (prev) => prev,
  })
}

export function useFindingsFacets(params: FindingsParams) {
  return useQuery({
    queryKey: ['findingsFacets', params],
    queryFn: () => api.getFindingsFacets(params),
  })
}

export function useFinding(id: string | null) {
  return useQuery({
    queryKey: ['finding', id],
    queryFn: () => api.getFinding(id!),
    enabled: id !== null,
  })
}

export function useGene(id: string | null) {
  return useQuery({
    queryKey: ['gene', id],
    queryFn: () => api.getGene(id!),
    enabled: id !== null,
  })
}

export function useGeneviewData(
  id: string | null,
  params?: { start?: number; end?: number; lod?: number; clusters?: string[]; diff_strategies?: string[]; length_strategies?: string[] },
) {
  return useQuery({
    queryKey: ['geneviewData', id, params],
    queryFn: () => api.getGeneviewData(id!, params),
    enabled: id !== null,
  })
}

export function useGeneCounts(id: string | null) {
  return useQuery({
    queryKey: ['geneCounts', id],
    queryFn: () => api.getGeneCounts(id!),
    enabled: id !== null,
  })
}

export function usePas(id: string | null) {
  return useQuery({
    queryKey: ['pas', id],
    queryFn: () => api.getPas(id!),
    enabled: id !== null,
  })
}

export function usePasProvenance(id: string | null) {
  return useQuery({
    queryKey: ['pasProvenance', id],
    queryFn: () => api.getPasProvenance(id!),
    enabled: id !== null,
  })
}

export function useCell(id: string | null) {
  return useQuery({
    queryKey: ['cell', id],
    queryFn: () => api.getCell(id!),
    enabled: id !== null,
  })
}

export function useCellProvenance(id: string | null) {
  return useQuery({
    queryKey: ['cellProvenance', id],
    queryFn: () => api.getCellProvenance(id!),
    enabled: id !== null,
  })
}

export function useUmap(datasetId: string | null, params?: { color?: string; bbox?: [number, number, number, number]; lod?: number }) {
  return useQuery({
    queryKey: ['umap', datasetId, params],
    queryFn: () => api.getUmap(datasetId!, params),
    enabled: datasetId !== null,
  })
}

export function useConcordance(runId: string | null) {
  return useQuery({
    queryKey: ['concordance', runId],
    queryFn: () => api.getConcordance(runId!),
    enabled: runId !== null,
  })
}

export function useBenchmarks(runId: string | null) {
  return useQuery({
    queryKey: ['benchmarks', runId],
    queryFn: () => api.getBenchmarks(runId!),
    enabled: runId !== null,
  })
}

export function useSearch(q: string) {
  return useQuery({
    queryKey: ['search', q],
    queryFn: () => api.search(q),
    enabled: q.trim().length > 0,
  })
}
