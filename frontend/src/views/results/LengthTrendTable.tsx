import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useRunSwitchTrendGenes } from '@lib/api/hooks'
import { trendDirectionLabel } from '@lib/trendDirectionLabel'
import { EmptyState, ErrorState, LoadingState } from '@views/shared/ViewStates'
import './ResultsView.css'

const PAGE_SIZE = 50
// The backend caps at le=20000 (api/runs.py) -- a real celltype's
// length_trend_by_gene.tsv is a few thousand rows (~300KB), so this single
// request fetches effectively "all genes" for search/sort/pagination to
// work against client-side, no backend-side query params needed for those.
const FETCH_LIMIT = 20000

type SortKey = 'gene' | 'slope' | 'spearman' | 'n_stages'

/**
 * Makes the length results BROWSABLE (2026-08-14) -- the per-CELL classic/
 * proportion/shannon files are huge (up to 100GB+/run, see
 * switch_availability, deliberately never loaded), but the per-GENE
 * length-trend-across-stages summary (length_trend_by_gene.tsv, ~300KB,
 * already fully ingested at index time) is small and was previously only
 * shown as a capped "top 25" preview. This fetches the celltype's whole
 * trend-gene set once and does search/sort/pagination client-side --
 * search by gene symbol or ENSG id, sort by gene/|slope|/spearman/n_stages,
 * 50 rows/page. Each row opens a real geneview scoped to this gene x
 * celltype, same as every other gene table in this view.
 */
export function LengthTrendTable({ runId, celltype }: { runId: string; celltype: string }) {
  const query = useRunSwitchTrendGenes(runId, celltype, FETCH_LIMIT)
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('slope')
  const [sortDesc, setSortDesc] = useState(true)
  const [page, setPage] = useState(0)

  const filteredAndSorted = useMemo(() => {
    const rows = query.data ?? []
    const q = search.trim().toLowerCase()
    const matched = q
      ? rows.filter((r) => r.gene_id.toLowerCase().includes(q) || (r.gene_symbol ?? '').toLowerCase().includes(q))
      : rows
    return [...matched].sort((a, b) => {
      let cmp: number
      switch (sortKey) {
        case 'gene':
          cmp = (a.gene_symbol ?? a.gene_id).localeCompare(b.gene_symbol ?? b.gene_id)
          break
        case 'spearman':
          cmp = (a.spearman ?? 0) - (b.spearman ?? 0)
          break
        case 'n_stages':
          cmp = (a.n_stages ?? 0) - (b.n_stages ?? 0)
          break
        case 'slope':
        default:
          cmp = Math.abs(a.slope ?? 0) - Math.abs(b.slope ?? 0)
          break
      }
      return sortDesc ? -cmp : cmp
    })
  }, [query.data, search, sortKey, sortDesc])

  // Any change to what's being shown resets back to page 1 -- otherwise a
  // narrowed search can land on a now out-of-range page showing nothing,
  // reading as "no results" when there really are matches on page 1.
  useEffect(() => {
    setPage(0)
  }, [search, sortKey, sortDesc])

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDesc((d) => !d)
    } else {
      setSortKey(key)
      setSortDesc(true)
    }
  }

  function sortIndicator(key: SortKey) {
    if (sortKey !== key) return null
    return sortDesc ? ' ▼' : ' ▲'
  }

  if (query.isLoading) {
    return <LoadingState label="Loading length results…" />
  }
  if (query.isError) {
    return <ErrorState error={query.error} onRetry={() => query.refetch()} />
  }
  if ((query.data ?? []).length === 0) {
    return <EmptyState reason="no-match" detail="No per-gene length-trend results for this celltype." />
  }

  const totalPages = Math.max(1, Math.ceil(filteredAndSorted.length / PAGE_SIZE))
  const pageRows = filteredAndSorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  return (
    <>
      <div className="results-view__table-toolbar">
        <input
          type="search"
          aria-label="Search length results"
          placeholder="Search gene symbol or ENSG id…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <span className="state-message">
          {filteredAndSorted.length.toLocaleString()} of {(query.data ?? []).length.toLocaleString()} genes
          {search ? ` matching "${search}"` : ''}
        </span>
      </div>
      {pageRows.length === 0 ? (
        <p className="state-message">No genes match "{search}".</p>
      ) : (
        <>
          <table className="gene-view__table">
            <thead>
              <tr>
                <th onClick={() => toggleSort('gene')} className="results-view__sortable">
                  Gene{sortIndicator('gene')}
                </th>
                <th>gene_id</th>
                <th>3'UTR trend</th>
                <th onClick={() => toggleSort('slope')} className="results-view__sortable">
                  |slope|{sortIndicator('slope')}
                </th>
                <th onClick={() => toggleSort('spearman')} className="results-view__sortable">
                  spearman{sortIndicator('spearman')}
                </th>
                <th onClick={() => toggleSort('n_stages')} className="results-view__sortable">
                  n_stages{sortIndicator('n_stages')}
                </th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((g) => (
                <tr
                  key={g.gene_id}
                  onClick={() => navigate(`/genes/${g.gene_id}?celltype=${encodeURIComponent(celltype)}`)}
                  style={{ cursor: 'pointer' }}
                >
                  <td>{g.gene_symbol ?? <span className="state-message">—</span>}</td>
                  <td className="mono">{g.gene_id}</td>
                  <td>{trendDirectionLabel(g.direction)}</td>
                  <td>{g.slope?.toFixed(4) ?? '—'}</td>
                  <td>{g.spearman?.toFixed(2) ?? '—'}</td>
                  <td>{g.n_stages ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="results-view__pagination">
            <button type="button" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
              ◀ Prev
            </button>
            <span>
              Page {page + 1} / {totalPages}
            </span>
            <button type="button" disabled={page >= totalPages - 1} onClick={() => setPage((p) => p + 1)}>
              Next ▶
            </button>
          </div>
        </>
      )}
    </>
  )
}
