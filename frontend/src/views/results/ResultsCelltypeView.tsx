import { useMemo } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useFindings, useRunSwitch, useRunSwitchNbMulti } from '@lib/api/hooks'
import { useScopeStore } from '@state/useScopeStore'
import { celltypeLabel } from '@lib/celltypeLabel'
import { trendDirectionLabel } from '@lib/trendDirectionLabel'
import { EmptyState, ErrorState, LoadingState } from '@views/shared/ViewStates'
import { formatBytes } from './ResultsView'
import { LengthTrendTable } from './LengthTrendTable'
import './ResultsView.css'

/**
 * One cell type's B3_switch results, ALL of them combined in one view
 * (2026-08-14 fix -- this used to only show fisher; nb_multi, a genuinely
 * different switch-diff strategy/result grain, was invisible): the
 * length-trend-across-stages headline (run-level), fisher's switching genes
 * (findings_long filtered to this celltype -- sorted client-side by qvalue
 * ascending since the backend's /findings endpoint orders by finding_uid,
 * not significance), nb_multi's omnibus hits (a separate table/endpoint --
 * nb_multi_omnibus.tsv has no canonical_cluster/direction, so it can't live
 * in findings_long, see backend schema.py's switch_nb_multi table
 * docstring), and the full browsable per-gene LENGTH results (see
 * LengthTrendTable -- 2026-08-14, supersedes the old capped "top 25 by
 * |slope|" preview panel, which is now this same table's default sort).
 * Each gene row opens a real ema geneview scoped to this celltype.
 */
export function ResultsCelltypeView() {
  const { celltype } = useParams<{ celltype: string }>()
  const runId = useScopeStore((s) => s.runId)
  const navigate = useNavigate()

  const switchQuery = useRunSwitch(runId)
  const findingsQuery = useFindings({ run_id: runId ?? undefined, celltype: celltype ?? undefined, limit: 500 })
  const nbMultiQuery = useRunSwitchNbMulti(runId, celltype ?? null, 25)

  const sortedFindings = useMemo(() => {
    const rows = findingsQuery.data?.rows ?? []
    return [...rows].sort((a, b) => a.qvalue - b.qvalue).slice(0, 100)
  }, [findingsQuery.data])

  if (!celltype) {
    return <EmptyState reason="no-match" detail="No cell type selected." />
  }
  if (!runId) {
    return <EmptyState reason="no-match" detail="Select a run from the top bar scope selector first." />
  }
  if (switchQuery.isLoading) {
    return <LoadingState label={`Loading ${celltype}…`} />
  }
  if (switchQuery.isError) {
    return <ErrorState error={switchQuery.error} onRetry={() => switchQuery.refetch()} />
  }

  const entry = switchQuery.data?.celltypes.find((c) => c.celltype === celltype)
  if (!entry) {
    return <EmptyState reason="not-indexed" detail={`No B3_switch results for celltype ${celltype} in this run.`} />
  }

  return (
    <div className="results-view">
      <header className="results-view__header">
        <Link to="/results" className="results-view__back">
          ◀ Cell Types
        </Link>
        <h2 title={celltype}>{celltypeLabel(celltype)}</h2>
        <span className="mono results-view__full-id">{celltype}</span>
      </header>

      <div className="panel results-view__trend-panel">
        <h4>3'UTR length trend across stages</h4>
        {entry.trend ? (
          <>
            <div className="results-view__trend">
              <span>
                <strong>{trendDirectionLabel(entry.trend.direction)}</strong>
              </span>
              <span>
                slope <strong>{entry.trend.slope?.toFixed(4) ?? '—'}</strong>
              </span>
              <span>
                spearman <strong>{entry.trend.spearman?.toFixed(2) ?? '—'}</strong>
              </span>
              <span>{entry.trend.n_stages ?? '—'} stages</span>
            </div>
            <table className="gene-view__table">
              <thead>
                <tr>
                  <th>stage</th>
                  <th>mean {entry.trend.value_col ?? 'value'}</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(entry.trend.mean_by_stage).map(([stage, mean]) => (
                  <tr key={stage}>
                    <td>{stage}</td>
                    <td>{mean.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <p className="state-message">No length-trend result for this celltype.</p>
        )}
      </div>

      <div className="panel results-view__trend-panel">
        <h4>Length results by gene</h4>
        <LengthTrendTable runId={runId} celltype={celltype} />
      </div>

      <div className="panel results-view__trend-panel">
        <h4>
          Switching genes -- fisher pairwise contrasts (top 100 by q-value){' '}
          {entry.diff.fisher !== undefined && <span className="badge badge--neutral">{entry.diff.fisher.toLocaleString()} total</span>}
        </h4>
        {findingsQuery.isLoading ? (
          <LoadingState label="Loading findings…" />
        ) : sortedFindings.length === 0 ? (
          <p className="state-message">No fisher switch-diff findings for this celltype in this run.</p>
        ) : (
          <table className="gene-view__table">
            <thead>
              <tr>
                <th>Gene</th>
                <th>gene_id</th>
                <th>arm</th>
                <th>direction</th>
                <th>qvalue</th>
                <th>Δ proportion</th>
              </tr>
            </thead>
            <tbody>
              {sortedFindings.map((f) => (
                <tr key={f.finding_uid} onClick={() => navigate(`/genes/${f.gene_id}?celltype=${encodeURIComponent(celltype)}`)} style={{ cursor: 'pointer' }}>
                  <td>{f.gene_symbol ?? '—'}</td>
                  <td className="mono">{f.gene_id}</td>
                  <td>{f.arm}</td>
                  <td>{f.direction}</td>
                  <td>{f.qvalue.toFixed(4)}</td>
                  <td>{f.delta_proportion.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel results-view__trend-panel">
        <h4>
          nb_multi omnibus hits (top 25 by q-value){' '}
          {entry.nb_multi && (
            <span className="badge badge--neutral">
              {entry.nb_multi.n_significant.toLocaleString()} / {entry.nb_multi.n.toLocaleString()} significant (q&lt;0.05)
            </span>
          )}
        </h4>
        <p className="state-message">
          A different result grain than fisher: one omnibus likelihood-ratio test per PAS across ALL stages at
          once, not a pairwise contrast -- no canonical_cluster/direction columns exist for it.
        </p>
        {nbMultiQuery.isLoading ? (
          <LoadingState label="Loading nb_multi hits…" />
        ) : (nbMultiQuery.data ?? []).length === 0 ? (
          <p className="state-message">No nb_multi results for this celltype in this run.</p>
        ) : (
          <table className="gene-view__table">
            <thead>
              <tr>
                <th>gene_id</th>
                <th>pas_id</th>
                <th>qvalue</th>
                <th>test_stat</th>
                <th>n_cells</th>
              </tr>
            </thead>
            <tbody>
              {(nbMultiQuery.data ?? []).map((row) => (
                <tr
                  key={row.pas_id}
                  onClick={() => row.gene_id && navigate(`/genes/${row.gene_id}?celltype=${encodeURIComponent(celltype)}`)}
                  style={{ cursor: row.gene_id ? 'pointer' : undefined }}
                >
                  <td className="mono">{row.gene_id ?? '—'}</td>
                  <td className="mono">{row.pas_id}</td>
                  <td>{row.qvalue?.toFixed(4) ?? '—'}</td>
                  <td>{row.test_stat?.toFixed(1) ?? '—'}</td>
                  <td>{row.n_cells ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <p className="results-view__length-avail-note state-message">
        Raw per-cell length files (classic/proportion/shannon) are not loaded into the hub -- up to 100GB+/run.
        {' '}
        <span className="results-view__length-avail">
          {Object.entries(entry.length).map(([strategy, avail]) => (
            <span key={strategy} className="badge badge--neutral">
              {strategy}: {formatBytes(avail.file_size_bytes)}
            </span>
          ))}
        </span>
      </p>
    </div>
  )
}
