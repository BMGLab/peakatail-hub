import { useMemo } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useFindings, useRunSwitch, useRunSwitchTrendGenes } from '@lib/api/hooks'
import { useScopeStore } from '@state/useScopeStore'
import { EmptyState, ErrorState, LoadingState } from '@views/shared/ViewStates'
import { formatBytes } from './ResultsView'
import './ResultsView.css'

/**
 * One cell type's B3_switch results: the length-trend-across-stages
 * headline (run-level AND top genes by |slope|), and its switching genes
 * (findings_long filtered to this celltype -- sorted client-side by qvalue
 * ascending since the backend's /findings endpoint orders by finding_uid,
 * not significance; a real ranking is the whole point of this table).
 * Each gene row opens a real ema geneview scoped to this celltype.
 */
export function ResultsCelltypeView() {
  const { celltype } = useParams<{ celltype: string }>()
  const runId = useScopeStore((s) => s.runId)
  const navigate = useNavigate()

  const switchQuery = useRunSwitch(runId)
  const trendGenesQuery = useRunSwitchTrendGenes(runId, celltype ?? null, 25)
  const findingsQuery = useFindings({ run_id: runId ?? undefined, celltype: celltype ?? undefined, limit: 500 })

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
        <h2>{celltype}</h2>
      </header>

      <div className="panel results-view__trend-panel">
        <h4>3'UTR length trend across stages</h4>
        {entry.trend ? (
          <>
            <div className="results-view__trend">
              <span>
                direction <strong>{entry.trend.direction ?? '—'}</strong>
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
        <h4>Top genes by |trend slope|</h4>
        {trendGenesQuery.isLoading ? (
          <LoadingState label="Loading top genes…" />
        ) : (trendGenesQuery.data ?? []).length === 0 ? (
          <p className="state-message">No per-gene trend rows for this celltype.</p>
        ) : (
          <table className="gene-view__table">
            <thead>
              <tr>
                <th>gene_id</th>
                <th>slope</th>
                <th>spearman</th>
                <th>direction</th>
              </tr>
            </thead>
            <tbody>
              {(trendGenesQuery.data ?? []).map((g) => (
                <tr key={g.gene_id} onClick={() => navigate(`/genes/${g.gene_id}?celltype=${encodeURIComponent(celltype)}`)} style={{ cursor: 'pointer' }}>
                  <td className="mono">{g.gene_id}</td>
                  <td>{g.slope?.toFixed(4) ?? '—'}</td>
                  <td>{g.spearman?.toFixed(2) ?? '—'}</td>
                  <td>{g.direction ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel results-view__trend-panel">
        <h4>Switching genes (switch-diff findings, top 100 by q-value)</h4>
        {findingsQuery.isLoading ? (
          <LoadingState label="Loading findings…" />
        ) : sortedFindings.length === 0 ? (
          <p className="state-message">No switch-diff findings for this celltype in this run.</p>
        ) : (
          <table className="gene-view__table">
            <thead>
              <tr>
                <th>gene_id</th>
                <th>arm</th>
                <th>strategy</th>
                <th>direction</th>
                <th>qvalue</th>
                <th>Δ proportion</th>
              </tr>
            </thead>
            <tbody>
              {sortedFindings.map((f) => (
                <tr key={f.finding_uid} onClick={() => navigate(`/genes/${f.gene_id}?celltype=${encodeURIComponent(celltype)}`)} style={{ cursor: 'pointer' }}>
                  <td className="mono">{f.gene_id}</td>
                  <td>{f.arm}</td>
                  <td>{f.strategy}</td>
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
        <h4>Length-result availability (not browsable -- per-cell files, up to 100GB+/run)</h4>
        <div className="results-view__length-avail">
          {Object.entries(entry.length).map(([strategy, avail]) => (
            <span key={strategy} className="badge badge--neutral">
              {strategy}: {formatBytes(avail.file_size_bytes)}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
