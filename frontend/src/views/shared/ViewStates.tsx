import type { ReactNode } from 'react'
import './ViewStates.css'

/**
 * Shared state components so every view handles the same five states
 * consistently (design doc §5): loading, empty-for-filter (distinct from
 * not-indexed), error, streaming, stale.
 */

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="view-state view-state--loading" role="status">
      {label}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error)
  return (
    <div className="view-state view-state--error" role="alert">
      <p>Failed to load: {message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}

/**
 * `reason="no-match"` = the query ran fine but nothing matched the current
 * filters (loosen facets to see results). `reason="not-indexed"` = the
 * underlying artifact/run hasn't been indexed yet -- a materially different
 * situation that must never be presented the same way as "no results".
 */
export function EmptyState({ reason, detail }: { reason: 'no-match' | 'not-indexed'; detail?: string }) {
  return (
    <div className="view-state view-state--empty" data-reason={reason}>
      {reason === 'no-match' ? (
        <p>No rows match the current filters. Try loosening facets or the q-threshold.</p>
      ) : (
        <p>This run/dataset has not been indexed yet. {detail ?? 'Run the hub indexer against the run directory first.'}</p>
      )}
    </div>
  )
}

export function StaleBanner({ children }: { children?: ReactNode }) {
  return (
    <div className="view-state view-state--stale" role="status">
      {children ?? 'Showing stale data while refreshing…'}
    </div>
  )
}

export function ContractMismatchBanner({ expected, actual }: { expected: string; actual: string }) {
  return (
    <div className="view-state view-state--contract-mismatch" role="alert">
      Contract version mismatch: frontend built against <code>{expected}</code>, backend reports <code>{actual}</code>. Data may be
      misinterpreted -- fail loud rather than silently rendering.
    </div>
  )
}

export function MissingArtifactNotice({ what }: { what: string }) {
  return <div className="view-state view-state--missing-artifact">{what} coordinates unavailable (artifact missing or not yet rendered).</div>
}
