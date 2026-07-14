import { useRuns } from '@lib/api/hooks'
import { EmptyState, ErrorState, LoadingState } from '@views/shared/ViewStates'
import { RunCard } from './RunCard'
import { SourcesPanel } from './SourcesPanel'
import './DashboardView.css'

/**
 * The app's landing/overview surface (IGV-style tools open on a clean
 * "what data do I have" screen, not a busy admin panel): an at-a-glance
 * overview across every indexed run, the SOURCES manager (this hub's
 * multi-directory "collect runs from everywhere" feature), and a run card
 * per indexed run that jumps straight into the genome browser scoped to
 * that run.
 */
export function DashboardView() {
  const runsQuery = useRuns()
  const runs = runsQuery.data ?? []

  const totals = runs.reduce(
    (acc, r) => ({
      genes: acc.genes + (r.n_genes ?? 0),
      pas: acc.pas + (r.n_pas ?? 0),
      cells: acc.cells + (r.n_cells ?? 0),
    }),
    { genes: 0, pas: 0, cells: 0 },
  )

  return (
    <div className="dashboard-view">
      <header className="dashboard-view__header">
        <h2>Dashboard</h2>
        <p className="dashboard-view__subtitle">Overview across every indexed PeakATail run, and where they live.</p>
      </header>

      <section className="dashboard-view__overview" aria-label="Overview totals across all sources">
        <div className="dashboard-stat panel">
          <span className="num dashboard-stat__value">{runs.length.toLocaleString()}</span>
          <span className="dashboard-stat__label">runs</span>
        </div>
        <div className="dashboard-stat panel">
          <span className="num dashboard-stat__value">{totals.genes.toLocaleString()}</span>
          <span className="dashboard-stat__label">genes</span>
        </div>
        <div className="dashboard-stat panel">
          <span className="num dashboard-stat__value">{totals.pas.toLocaleString()}</span>
          <span className="dashboard-stat__label">PAS</span>
        </div>
        <div className="dashboard-stat panel">
          <span className="num dashboard-stat__value">{totals.cells.toLocaleString()}</span>
          <span className="dashboard-stat__label">cells</span>
        </div>
      </section>

      <SourcesPanel />

      <section className="dashboard-view__runs">
        <h3>Runs</h3>
        {runsQuery.isLoading && <LoadingState label="Loading runs…" />}
        {runsQuery.isError && <ErrorState error={runsQuery.error} onRetry={() => runsQuery.refetch()} />}
        {!runsQuery.isLoading && !runsQuery.isError && runs.length === 0 && (
          <EmptyState reason="not-indexed" detail="Add a source directory above to collect your first run." />
        )}
        {runs.length > 0 && (
          <div className="dashboard-view__run-grid">
            {runs.map((run) => (
              <RunCard key={run.run_id} run={run} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
