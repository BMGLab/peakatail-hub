import { useBenchmarks, useConcordance, useRunQc } from '@lib/api/hooks'
import { useScopeStore } from '@state/useScopeStore'
import { PlotlyChart } from '@charts/PlotlyChart'
import { EmptyState, ErrorState, LoadingState } from '@views/shared/ViewStates'
import './QcView.css'

export function QcView() {
  const { runId } = useScopeStore()
  const qcQuery = useRunQc(runId)
  const concordanceQuery = useConcordance(runId)
  const benchmarksQuery = useBenchmarks(runId)

  if (!runId) {
    return <EmptyState reason="no-match" detail="Select a run from the top bar scope selector first." />
  }

  if (qcQuery.isLoading) return <LoadingState label="Loading QC…" />
  if (qcQuery.isError) return <ErrorState error={qcQuery.error} onRetry={() => qcQuery.refetch()} />
  if (!qcQuery.data) return <EmptyState reason="not-indexed" detail={`Run ${runId} has no QC stats indexed yet.`} />

  const qc = qcQuery.data
  // Merge the two per-stage drop arrays into one row set for the table/chart
  // -- QC_STAGES order comes from the backend already (store/queries.py),
  // both arrays share the same stage list in the same order.
  const stageRows = qc.pas_drop_by_stage.map((s, i) => ({
    stage: s.stage,
    pas_dropped: s.dropped,
    cell_dropped: qc.cell_drop_by_stage[i]?.dropped ?? 0,
  }))

  return (
    <div className="qc-view">
      <section className="panel qc-view__section">
        <h3>Survival funnel</h3>
        <p className="state-message">
          PAS: {qc.n_pas_survived.toLocaleString()} / {qc.n_pas_total.toLocaleString()} survived · Cells:{' '}
          {qc.n_cells_survived.toLocaleString()} / {qc.n_cells_total.toLocaleString()} survived
        </p>
      </section>

      <section className="panel qc-view__section">
        <h3>Drop-by-stage (7 drop points)</h3>
        {!qc.per_sample_stats_available && <p className="state-message">{qc.gate_note}</p>}
        <div className="qc-view__funnel-chart">
          <PlotlyChart
            data={[
              {
                x: stageRows.map((s) => s.stage),
                y: stageRows.map((s) => s.pas_dropped),
                type: 'bar',
                name: 'PAS dropped',
                marker: { color: '#5b9dff' },
              },
              {
                x: stageRows.map((s) => s.stage),
                y: stageRows.map((s) => s.cell_dropped),
                type: 'bar',
                name: 'cells dropped',
                marker: { color: '#4cc38a' },
                yaxis: 'y2',
              },
            ]}
            layout={{
              barmode: 'group',
              xaxis: { title: { text: 'stage' } },
              yaxis: { title: { text: 'PAS dropped' } },
              yaxis2: { title: { text: 'cells dropped' }, overlaying: 'y', side: 'right' },
            }}
          />
        </div>
        <table className="qc-view__table">
          <thead>
            <tr>
              <th>stage</th>
              <th>PAS dropped</th>
              <th>cells dropped</th>
            </tr>
          </thead>
          <tbody>
            {stageRows.map((s) => (
              <tr key={s.stage}>
                <td>{s.stage}</td>
                <td>{s.pas_dropped.toLocaleString()}</td>
                <td>{s.cell_dropped.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="panel qc-view__section">
        <h3>Config diff (resolved vs default)</h3>
        <p className="state-message">
          Stub -- config diff reads the resolved config from the E2 manifest (docs §7d), not run_config.json. Not yet wired.
        </p>
      </section>

      <section className="panel qc-view__section">
        <h3>Concordance (ARI/AMI across strategies)</h3>
        {concordanceQuery.isLoading && <LoadingState />}
        {concordanceQuery.isError && <ErrorState error={concordanceQuery.error} />}
        {concordanceQuery.data && <p className="state-message">{concordanceQuery.data.note}</p>}
      </section>

      <section className="panel qc-view__section">
        <h3>Benchmarks</h3>
        {benchmarksQuery.isLoading && <LoadingState />}
        {benchmarksQuery.isError && <ErrorState error={benchmarksQuery.error} />}
        {benchmarksQuery.data && <p className="state-message">{benchmarksQuery.data.note}</p>}
      </section>
    </div>
  )
}
