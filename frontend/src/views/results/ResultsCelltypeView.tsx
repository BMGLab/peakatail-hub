import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useFindings, useRunSwitch, useRunSwitchNbMulti } from '@lib/api/hooks'
import { useScopeStore } from '@state/useScopeStore'
import { celltypeLabel } from '@lib/celltypeLabel'
import { trendDirectionLabel } from '@lib/trendDirectionLabel'
import { EmptyState, ErrorState, LoadingState } from '@views/shared/ViewStates'
import { formatBytes } from './ResultsView'
import { LengthTrendTable } from './LengthTrendTable'
import './ResultsView.css'

type LengthStrategy = 'classic' | 'proportion' | 'shannon'
type DiffStrategy = 'fisher' | 'nb_multi'

// 2026-08-14: "surface all strategies, let the user select per step" -- the
// three length/3'UTR strategies the pipeline actually ran per celltype (see
// main.nf's SWITCH_CELLTYPE process: `for S in classic proportion shannon`).
// Every celltype has FILE availability for all three (switch_availability),
// but only celltypes reindexed after the 2026-08-14 out-of-band compute (see
// index/indexer.py::_switch_trend_dfs) have a computed TREND for
// proportion/shannon -- classic's trend was always computed by the pipeline
// itself. A strategy tab is disabled, not hidden, when its trend is absent:
// truthful ("not computed"), not silently missing.
const LENGTH_STRATEGIES: { key: LengthStrategy; label: string }[] = [
  { key: 'classic', label: 'Classic (PDUI)' },
  { key: 'proportion', label: 'Proportion' },
  { key: 'shannon', label: 'Shannon entropy' },
]

export function ResultsCelltypeView() {
  const { celltype } = useParams<{ celltype: string }>()
  const runId = useScopeStore((s) => s.runId)
  const navigate = useNavigate()
  const [lengthStrategy, setLengthStrategy] = useState<LengthStrategy>('classic')
  const [diffStrategy, setDiffStrategy] = useState<DiffStrategy>('fisher')

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

  const trend = entry.trend[lengthStrategy] ?? null
  const fisherCount = entry.diff.fisher
  const fisherAvailable = fisherCount !== undefined
  const nbMultiAvailable = entry.nb_multi !== null

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
        <div className="results-view__strategy-tabs" role="tablist" aria-label="Length strategy">
          {LENGTH_STRATEGIES.map((s) => {
            const available = entry.trend[s.key] !== undefined
            return (
              <button
                key={s.key}
                type="button"
                role="tab"
                aria-selected={lengthStrategy === s.key}
                disabled={!available}
                title={available ? undefined : 'Not computed for this run/celltype'}
                className={`results-view__strategy-tab${lengthStrategy === s.key ? ' is-active' : ''}${!available ? ' is-unavailable' : ''}`}
                onClick={() => setLengthStrategy(s.key)}
              >
                {s.label}
                {!available && <span className="results-view__strategy-tab-note">not computed</span>}
              </button>
            )
          })}
        </div>
        {trend ? (
          <>
            <div className="results-view__trend">
              <span>
                <strong>{trendDirectionLabel(trend.direction)}</strong>
              </span>
              <span>
                slope <strong>{trend.slope?.toFixed(4) ?? '—'}</strong>
              </span>
              <span>
                spearman <strong>{trend.spearman?.toFixed(2) ?? '—'}</strong>
              </span>
              <span>{trend.n_stages ?? '—'} stages</span>
            </div>
            <table className="gene-view__table">
              <thead>
                <tr>
                  <th>stage</th>
                  <th>mean {trend.value_col ?? 'value'}</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(trend.mean_by_stage).map(([stage, mean]) => (
                  <tr key={stage}>
                    <td>{stage}</td>
                    <td>{mean.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <p className="state-message">
            No {LENGTH_STRATEGIES.find((s) => s.key === lengthStrategy)?.label} length-trend result for this celltype.
          </p>
        )}
      </div>

      <div className="panel results-view__trend-panel">
        <h4>Length results by gene</h4>
        {trend ? (
          <LengthTrendTable key={lengthStrategy} runId={runId} celltype={celltype} strategy={lengthStrategy} />
        ) : (
          <p className="state-message">
            No per-gene {LENGTH_STRATEGIES.find((s) => s.key === lengthStrategy)?.label} results for this celltype.
          </p>
        )}
      </div>

      <div className="panel results-view__trend-panel">
        <h4>Switching genes -- differential test</h4>
        <div className="results-view__strategy-tabs" role="tablist" aria-label="Differential test strategy">
          <button
            type="button"
            role="tab"
            aria-selected={diffStrategy === 'fisher'}
            disabled={!fisherAvailable}
            title={fisherAvailable ? undefined : 'Not computed for this run/celltype'}
            className={`results-view__strategy-tab${diffStrategy === 'fisher' ? ' is-active' : ''}${!fisherAvailable ? ' is-unavailable' : ''}`}
            onClick={() => setDiffStrategy('fisher')}
          >
            Fisher (pairwise)
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={diffStrategy === 'nb_multi'}
            disabled={!nbMultiAvailable}
            title={nbMultiAvailable ? undefined : 'Not computed for this run/celltype'}
            className={`results-view__strategy-tab${diffStrategy === 'nb_multi' ? ' is-active' : ''}${!nbMultiAvailable ? ' is-unavailable' : ''}`}
            onClick={() => setDiffStrategy('nb_multi')}
          >
            nb_multi (omnibus)
          </button>
          {/* nb_pairwise was NOT run in this sweep (see main.nf's
              SWITCH_CELLTYPE process -- only fisher/nb_multi are invoked) --
              shown disabled/"not run" rather than omitted or faked, same
              "don't fake it" principle as an uncomputed length strategy. */}
          <button
            type="button"
            role="tab"
            aria-selected={false}
            disabled
            title="nb_pairwise was not run in this sweep"
            className="results-view__strategy-tab is-unavailable"
          >
            nb_pairwise
            <span className="results-view__strategy-tab-note">not run</span>
          </button>
        </div>

        {diffStrategy === 'fisher' && (
          <>
            <p className="state-message">
              Exhaustive within-gene pairwise contrasts between stages (top 100 by q-value).{' '}
              {fisherCount !== undefined && <span className="badge badge--neutral">{fisherCount.toLocaleString()} total</span>}
            </p>
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
                    <tr
                      key={f.finding_uid}
                      onClick={() => navigate(`/genes/${f.gene_id}?celltype=${encodeURIComponent(celltype)}`)}
                      style={{ cursor: 'pointer' }}
                    >
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
          </>
        )}

        {diffStrategy === 'nb_multi' && (
          <>
            <p className="state-message">
              A different result grain than fisher: one omnibus likelihood-ratio test per PAS across ALL stages at
              once, not a pairwise contrast -- no canonical_cluster/direction columns exist for it (top 25 by
              q-value).{' '}
              {entry.nb_multi && (
                <span className="badge badge--neutral">
                  {entry.nb_multi.n_significant.toLocaleString()} / {entry.nb_multi.n.toLocaleString()} significant (q&lt;0.05)
                </span>
              )}
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
          </>
        )}
      </div>

      <p className="results-view__length-avail-note state-message">
        Raw per-cell length files (classic/proportion/shannon) are not loaded into the hub -- up to 100GB+/run.{' '}
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
