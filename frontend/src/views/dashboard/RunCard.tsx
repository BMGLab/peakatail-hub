import { useNavigate } from 'react-router-dom'
import { useScopeStore } from '@state/useScopeStore'
import type { RunSummary } from '@lib/contract/types'
import './RunCard.css'

/** Best-effort display label for a run: prefers the manifest's resolved
 * stratum label (same rule TopBar.tsx uses for its scope selector) so a run
 * reads as "Laughney lung (full cohort)" rather than a bare run_id. */
function runLabel(run: RunSummary): string {
  const labels = Object.values(run.stratum_to_label)
  if (labels.length === 1 && labels[0]) return labels[0]
  return run.run_id
}

export function RunCard({ run }: { run: RunSummary }) {
  const navigate = useNavigate()
  const setScope = useScopeStore((s) => s.setScope)

  function openInBrowser() {
    setScope(run.run_id, run.run_id)
    navigate('/browse/genes')
  }

  return (
    <button type="button" className="run-card" onClick={openInBrowser}>
      <div className="run-card__header">
        <span className="run-card__label" title={runLabel(run)}>
          {runLabel(run)}
        </span>
        <span className="mono run-card__run-id truncate" title={run.run_id}>
          {run.run_id}
        </span>
      </div>

      <div className="run-card__source">
        {run.source_path ? (
          <span className="mono truncate" title={run.source_path}>
            {run.source_label ?? run.source_path}
          </span>
        ) : (
          <span className="run-card__unattributed">unattributed source</span>
        )}
      </div>

      <div className="run-card__stats">
        <div className="run-card__stat">
          <span className="num run-card__stat-value">{(run.n_findings ?? 0).toLocaleString()}</span>
          <span className="run-card__stat-label">findings</span>
        </div>
        <div className="run-card__stat">
          <span className="num run-card__stat-value">{run.n_celltypes ?? '—'}</span>
          <span className="run-card__stat-label">celltypes</span>
        </div>
        <div className="run-card__stat">
          <span className="num run-card__stat-value">{(run.n_genes ?? 0).toLocaleString()}</span>
          <span className="run-card__stat-label">genes</span>
        </div>
        <div className="run-card__stat">
          <span className="num run-card__stat-value">{(run.n_cells ?? 0).toLocaleString()}</span>
          <span className="run-card__stat-label">cells</span>
        </div>
      </div>

      <div className="run-card__footer">
        <span>{run.indexed_at ? `indexed ${new Date(run.indexed_at).toLocaleDateString()}` : 'not yet indexed'}</span>
        <span className="run-card__open-hint">Open in browser →</span>
      </div>
    </button>
  )
}
