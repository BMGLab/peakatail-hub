import { useNavigate } from 'react-router-dom'
import { useRunSwitch } from '@lib/api/hooks'
import { useScopeStore } from '@state/useScopeStore'
import { celltypeLabel } from '@lib/celltypeLabel'
import { trendDirectionLabel } from '@lib/trendDirectionLabel'
import { EmptyState, ErrorState, LoadingState } from '@views/shared/ViewStates'
import type { SwitchCelltypeResult } from '@lib/contract/types'
import './ResultsView.css'

function formatBytes(n: number | null | undefined): string {
  if (n == null) return '—'
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)} KB`
  return `${n} B`
}

function CelltypeCard({ celltype }: { celltype: SwitchCelltypeResult }) {
  const navigate = useNavigate()
  // Card preview always shows classic's trend (2026-08-14: `trend` is now
  // keyed by length strategy -- classic is the one every celltype with a
  // trend result has, since the pipeline itself always computes it;
  // proportion/shannon are only in the strategy selector on the detail
  // view). `?? null` not `.classic` alone so `trend &&` below stays a clean
  // boolean check.
  const trend = celltype.trend.classic ?? null
  const diffTotal = Object.values(celltype.diff).reduce((a, b) => a + b, 0)
  const lengthStrategies = Object.keys(celltype.length)

  return (
    <button type="button" className="results-view__card" onClick={() => navigate(`/results/${encodeURIComponent(celltype.celltype)}`)}>
      <div className="results-view__card-header">
        <span className="results-view__card-title" title={celltype.celltype}>
          {celltypeLabel(celltype.celltype)}
        </span>
        {trend && (
          <span className={`badge ${trend.direction === 'decreasing' ? 'badge--warn' : 'badge--neutral'}`}>
            {trend.direction ? trendDirectionLabel(trend.direction) : 'trend unavailable'}
          </span>
        )}
      </div>

      {trend ? (
        <>
          <div className="results-view__trend">
            <span>
              slope <strong>{trend.slope?.toFixed(4) ?? '—'}</strong>
            </span>
            <span>
              spearman <strong>{trend.spearman?.toFixed(2) ?? '—'}</strong>
            </span>
          </div>
          <div className="results-view__stages">
            {Object.keys(trend.mean_by_stage).map((stage) => (
              <span key={stage} className="badge badge--neutral">
                {stage}
              </span>
            ))}
          </div>
        </>
      ) : (
        <p className="state-message">No length-trend-across-stages result for this celltype.</p>
      )}

      <div className="results-view__stats">
        <div className="results-view__stat">
          <span className="num">{diffTotal.toLocaleString()}</span>
          <span>fisher findings</span>
        </div>
        <div className="results-view__stat">
          <span className="num">{celltype.nb_multi ? celltype.nb_multi.n_significant.toLocaleString() : '—'}</span>
          <span>nb_multi hits (q&lt;0.05)</span>
        </div>
        <div className="results-view__stat">
          <span className="num">{lengthStrategies.length}</span>
          <span>length strategies</span>
        </div>
      </div>
    </button>
  )
}

/**
 * ResultsView -- "cell types -> stages -> genes", the PRIMARY navigation for
 * the professor's headline finding (3'UTR shortening/lengthening across
 * disease stages, per cell type). Sourced from `GET /runs/{run_id}/switch`
 * (backend queries.switch_summary): per-celltype switch-diff finding counts,
 * length-result availability, and the length-trend-across-stages headline
 * (slope/spearman/direction/mean_by_stage). A run with no B3_switch results
 * at all (grid/reannotate runs) shows an honest empty state, not an error.
 */
export function ResultsView() {
  const runId = useScopeStore((s) => s.runId)
  const query = useRunSwitch(runId)

  if (!runId) {
    return <EmptyState reason="no-match" detail="Select a run from the top bar scope selector first." />
  }
  if (query.isLoading) {
    return <LoadingState label="Loading cell-type results…" />
  }
  if (query.isError) {
    return <ErrorState error={query.error} onRetry={() => query.refetch()} />
  }

  const celltypes = query.data?.celltypes ?? []

  return (
    <div className="results-view">
      <header className="results-view__header">
        <h2>Cell Types</h2>
        <p className="results-view__description">
          The full B3_switch analysis for this run, per cell type: 3'UTR-length trend across disease stages (the
          headline finding), switch-diff hit counts from BOTH strategies (fisher pairwise stage contrasts and
          nb_multi's omnibus test across all stages), and length-result availability. Click a cell type for the
          combined detail view, switching genes, and a real ema geneview.
        </p>
      </header>

      {celltypes.length === 0 ? (
        <EmptyState
          reason="no-match"
          detail="This run has no B3_switch results (only ema-cohort runs with a switch analysis do -- e.g. B1_cohort_full, not grid/reannotate runs)."
        />
      ) : (
        <div className="results-view__grid">
          {celltypes.map((c) => (
            <CelltypeCard key={c.celltype} celltype={c} />
          ))}
        </div>
      )}
    </div>
  )
}

export { formatBytes }
