import { useBenchmarks, useConcordance, useRunQc } from '@lib/api/hooks'
import { useScopeStore } from '@state/useScopeStore'
import { PlotlyChart } from '@charts/PlotlyChart'
import { EmptyState, ErrorState, LoadingState } from '@views/shared/ViewStates'
import './QcView.css'

export function QcView() {
  const { runId } = useScopeStore()
  const qcQuery = useRunQc(runId)
  const concordanceQuery = useConcordance()
  const benchmarksQuery = useBenchmarks()

  if (!runId) {
    return <EmptyState reason="no-match" detail="Select a run from the top bar scope selector first." />
  }

  if (qcQuery.isLoading) return <LoadingState label="Loading QC…" />
  if (qcQuery.isError) return <ErrorState error={qcQuery.error} onRetry={() => qcQuery.refetch()} />
  if (!qcQuery.data) return <EmptyState reason="not-indexed" detail={`Run ${runId} has no QC stats indexed yet.`} />

  const qc = qcQuery.data

  return (
    <div className="qc-view">
      <section className="panel qc-view__section">
        <h3>7-stage drop funnel</h3>
        <div className="qc-view__funnel-chart">
          <PlotlyChart
            data={[
              {
                x: qc.stages.map((s) => s.stage),
                y: qc.stages.map((s) => s.n_pas),
                type: 'bar',
                name: 'n_pas',
                marker: { color: '#5b9dff' },
              },
              {
                x: qc.stages.map((s) => s.stage),
                y: qc.stages.map((s) => s.n_cells),
                type: 'bar',
                name: 'n_cells',
                marker: { color: '#4cc38a' },
                yaxis: 'y2',
              },
            ]}
            layout={{
              barmode: 'group',
              xaxis: { title: { text: 'stage' } },
              yaxis: { title: { text: 'n_pas' } },
              yaxis2: { title: { text: 'n_cells' }, overlaying: 'y', side: 'right' },
            }}
          />
        </div>
        <table className="qc-view__table">
          <thead>
            <tr>
              <th>stage</th>
              <th>n_pas</th>
              <th>n_cells</th>
              <th>Δ n_pas</th>
            </tr>
          </thead>
          <tbody>
            {qc.stages.map((s, i) => (
              <tr key={s.stage}>
                <td>{s.stage}</td>
                <td>{s.n_pas.toLocaleString()}</td>
                <td>{s.n_cells.toLocaleString()}</td>
                <td>{i > 0 ? (s.n_pas - qc.stages[i - 1]!.n_pas).toLocaleString() : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="panel qc-view__section">
        <h3>Config diff (resolved vs default)</h3>
        {qc.config_diff ? (
          <table className="qc-view__table">
            <thead>
              <tr>
                <th>key</th>
                <th>resolved</th>
                <th>default</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(qc.config_diff).map(([key, v]) => (
                <tr key={key}>
                  <td className="mono">{key}</td>
                  <td>{String(v.resolved)}</td>
                  <td>{String(v.default)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="state-message">
            Stub -- config diff reads the resolved config from the E2 manifest (docs §7d), not run_config.json. Not yet wired.
          </p>
        )}
      </section>

      <section className="panel qc-view__section">
        <h3>Concordance (ARI/AMI across strategies)</h3>
        {concordanceQuery.isLoading && <LoadingState />}
        {concordanceQuery.isError && <ErrorState error={concordanceQuery.error} />}
        {concordanceQuery.data && (
          <table className="qc-view__table">
            <thead>
              <tr>
                <th>pair</th>
                <th>ARI</th>
                <th>AMI</th>
              </tr>
            </thead>
            <tbody>
              {concordanceQuery.data.map((c) => (
                <tr key={c.pair}>
                  <td>{c.pair}</td>
                  <td>{c.ari.toFixed(2)}</td>
                  <td>{c.ami.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel qc-view__section">
        <h3>Benchmarks</h3>
        {benchmarksQuery.isLoading && <LoadingState />}
        {benchmarksQuery.isError && <ErrorState error={benchmarksQuery.error} />}
        {benchmarksQuery.data && (
          <table className="qc-view__table">
            <thead>
              <tr>
                <th>name</th>
                <th>metric</th>
                <th>value</th>
                <th>note</th>
              </tr>
            </thead>
            <tbody>
              {benchmarksQuery.data.map((b) => (
                <tr key={b.name}>
                  <td>{b.name}</td>
                  <td>{b.metric}</td>
                  <td>{b.value.toFixed(2)}</td>
                  <td className="qc-view__note">{b.note ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
