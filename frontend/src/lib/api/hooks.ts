// TanStack Query hooks wrapping lib/api/client.ts. Views should import these,
// never `api` directly, so query-key/caching/staleness policy lives in one
// place. Swapping mocks -> real backend happens inside client.ts; these hooks
// don't change.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type BrowseParams, type FindingsParams, type GenesBrowseParams } from './client'

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

// `runId` (from the TopBar Scope selector's `useScopeStore`) is threaded
// through as its own param -- not folded into `params` below -- because
// callers (GeneView) need it in the query key even when `params` itself is
// omitted, so switching the active run always refetches rather than
// serving a stale cached gene from the previously-scoped run.
export function useGene(id: string | null, runId?: string | null) {
  return useQuery({
    queryKey: ['gene', id, runId],
    queryFn: () => api.getGene(id!, runId ?? undefined),
    enabled: id !== null,
  })
}

export function useGeneviewData(
  id: string | null,
  params?: { start?: number; end?: number; lod?: number; clusters?: string[]; diff_strategies?: string[]; length_strategies?: string[] },
  runId?: string | null,
) {
  return useQuery({
    queryKey: ['geneviewData', id, params, runId],
    queryFn: () => api.getGeneviewData(id!, { ...params, run_id: runId ?? undefined }),
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

// Real ema geneview (2026-08-14). `retry: false` -- a cache-miss render
// already blocks for up to ~25s server-side (the backend's own
// cross-dataset fallback, see api/geneview.py); TanStack Query's default
// retry-with-backoff on top of that would make a genuine failure (worker
// down, gene truly has no PAS anywhere) take minutes to surface instead of
// seconds. GeneView's own "Retry" button (ErrorState) is the explicit
// re-trigger, not an automatic one.
export function useGeneviewMeta(id: string | null, runId?: string | null, datasetId?: string | null) {
  return useQuery({
    queryKey: ['geneviewMeta', id, runId, datasetId],
    queryFn: () => api.getGeneviewMeta(id!, runId ?? undefined, datasetId ?? undefined),
    enabled: id !== null && runId !== null,
    retry: false,
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

// -----------------------------------------------------------------------
// Browse: gene/PAS/cell browsers (views/browse/**). `placeholderData: prev`
// keeps the previous page's rows on screen while a new search/page loads,
// same UX as `useFindings` above -- avoids a full-table flash to a loading
// state on every keystroke.
// -----------------------------------------------------------------------

export function useGenesBrowse(params: GenesBrowseParams) {
  return useQuery({
    queryKey: ['genesBrowse', params],
    queryFn: () => api.listGenes(params),
    placeholderData: (prev) => prev,
  })
}

export function usePasBrowse(params: BrowseParams) {
  return useQuery({
    queryKey: ['pasBrowse', params],
    queryFn: () => api.listPas(params),
    placeholderData: (prev) => prev,
  })
}

export function useCellsBrowse(params: BrowseParams) {
  return useQuery({
    queryKey: ['cellsBrowse', params],
    queryFn: () => api.listCells(params),
    placeholderData: (prev) => prev,
  })
}

// -----------------------------------------------------------------------
// Sources: the dashboard's multi-directory SOURCES manager. Every mutation
// (add/rescan/delete) invalidates both ['sources'] and ['runs'] -- adding or
// rescanning a source can change which runs exist/which source they're
// attributed to, and the dashboard's run cards + overview totals read
// ['runs'], not just the SOURCES panel itself.
// -----------------------------------------------------------------------

export function useSources() {
  return useQuery({ queryKey: ['sources'], queryFn: api.getSources })
}

export function useAddSource() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ path, label }: { path: string; label?: string }) => api.addSource(path, label),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sources'] })
      queryClient.invalidateQueries({ queryKey: ['runs'] })
    },
  })
}

export function useDeleteSource() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sourceId: string) => api.deleteSource(sourceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sources'] })
      queryClient.invalidateQueries({ queryKey: ['runs'] })
    },
  })
}

export function useRescanSource() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sourceId: string) => api.rescanSource(sourceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sources'] })
      queryClient.invalidateQueries({ queryKey: ['runs'] })
    },
  })
}

export function useRescanAllSources() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.rescanAllSources(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sources'] })
      queryClient.invalidateQueries({ queryKey: ['runs'] })
    },
  })
}
