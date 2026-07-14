import { useState } from 'react'
import {
  useAddSource,
  useDeleteSource,
  useRescanAllSources,
  useRescanSource,
  useSources,
} from '@lib/api/hooks'
import type { Source, SourceScanResult } from '@lib/contract/types'
import { LoadingState } from '@views/shared/ViewStates'
import './SourcesPanel.css'

/** One-line human summary of an add/rescan pass, shown right under the row
 * it applies to -- e.g. "indexed 2, 1 unchanged" or "no runs found here yet". */
function scanSummary(result: SourceScanResult): string {
  const { scan, source } = result
  if (source.last_scan_status === 'empty') {
    return 'No run_manifest.json found under this path yet.'
  }
  if (source.last_scan_status === 'error') {
    return source.last_scan_error ?? 'One or more runs under this path failed to index.'
  }
  const parts: string[] = []
  if (scan.indexed.length > 0) parts.push(`indexed ${scan.indexed.length}`)
  if (scan.skipped_unchanged.length > 0) parts.push(`${scan.skipped_unchanged.length} unchanged`)
  return parts.length > 0 ? parts.join(', ') : 'up to date'
}

function statusBadge(source: Source) {
  if (source.last_scan_status === 'error') return <span className="badge badge--danger">error</span>
  if (source.last_scan_status === 'empty') return <span className="badge badge--warn">empty</span>
  if (source.last_scan_status === 'ok') return <span className="badge badge--ok">ok</span>
  return <span className="badge badge--neutral">not scanned</span>
}

/**
 * The SOURCES panel: register/rescan/remove PeakATail run-output
 * directories. This is the dashboard's key feature (task brief) -- a user
 * with run outputs scattered across multiple directories registers each one
 * here, and every run any of them contains merges into the one hub index.
 */
export function SourcesPanel() {
  const sourcesQuery = useSources()
  const addSource = useAddSource()
  const deleteSource = useDeleteSource()
  const rescanSource = useRescanSource()
  const rescanAll = useRescanAllSources()

  const [path, setPath] = useState('')
  const [addError, setAddError] = useState<string | null>(null)
  // Per-source_id last scan-result summary line, shown until the next action
  // touches that row (or the whole list refetches from an unrelated cause).
  const [lastResults, setLastResults] = useState<Record<string, SourceScanResult>>({})

  function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = path.trim()
    if (!trimmed) return
    setAddError(null)
    addSource.mutate(
      { path: trimmed },
      {
        onSuccess: (result) => {
          setPath('')
          setLastResults((prev) => ({ ...prev, [result.source.source_id]: result }))
        },
        onError: (err) => setAddError(err instanceof Error ? err.message : String(err)),
      },
    )
  }

  function handleRescan(sourceId: string) {
    rescanSource.mutate(sourceId, {
      onSuccess: (result) => setLastResults((prev) => ({ ...prev, [sourceId]: result })),
    })
  }

  function handleRescanAll() {
    rescanAll.mutate(undefined, {
      onSuccess: (results) => {
        setLastResults((prev) => {
          const next = { ...prev }
          for (const r of results) next[r.source.source_id] = r
          return next
        })
      },
    })
  }

  function handleRemove(sourceId: string, sourcePath: string) {
    if (!window.confirm(`Remove source "${sourcePath}"? This also removes every run indexed from it.`)) return
    deleteSource.mutate(sourceId, {
      onSuccess: () =>
        setLastResults((prev) => {
          const { [sourceId]: _removed, ...rest } = prev
          return rest
        }),
    })
  }

  const sources = sourcesQuery.data ?? []

  return (
    <section className="panel sources-panel">
      <div className="sources-panel__header">
        <h3>Sources</h3>
        <button
          type="button"
          className="sources-panel__rescan-all"
          onClick={handleRescanAll}
          disabled={rescanAll.isPending || sources.length === 0}
        >
          {rescanAll.isPending ? 'Rescanning all…' : 'Rescan all'}
        </button>
      </div>
      <p className="sources-panel__hint">
        Register every directory holding PeakATail run outputs — each is walked for runs at any depth and merged into
        this hub.
      </p>

      <form className="sources-panel__add" onSubmit={handleAdd}>
        <input
          type="text"
          placeholder="/path/to/peakatail_runs (paste a server path)"
          value={path}
          onChange={(e) => {
            setPath(e.target.value)
            if (addError) setAddError(null)
          }}
          aria-label="Directory path to add as a source"
        />
        <button type="submit" disabled={addSource.isPending || path.trim().length === 0}>
          {addSource.isPending ? 'Adding…' : '+ Add directory'}
        </button>
      </form>
      {addError && (
        <p className="sources-panel__error" role="alert">
          {addError}
        </p>
      )}

      {sourcesQuery.isLoading && <LoadingState label="Loading sources…" />}
      {sourcesQuery.isError && (
        <p className="sources-panel__error" role="alert">
          Failed to load sources: {sourcesQuery.error instanceof Error ? sourcesQuery.error.message : String(sourcesQuery.error)}
        </p>
      )}

      {!sourcesQuery.isLoading && sources.length === 0 && (
        <p className="sources-panel__empty">
          No sources registered yet. Add a directory above to start collecting runs.
        </p>
      )}

      {sources.length > 0 && (
        <ul className="sources-panel__list">
          {sources.map((s) => (
            <li key={s.source_id} className="sources-panel__row">
              <div className="sources-panel__row-main">
                <span className="mono truncate sources-panel__path" title={s.path}>
                  {s.path}
                </span>
                {s.label && <span className="sources-panel__label">{s.label}</span>}
                {statusBadge(s)}
              </div>
              <div className="sources-panel__row-meta">
                <span className="num">{s.run_count.toLocaleString()}</span> run{s.run_count === 1 ? '' : 's'}
                {s.last_scanned_at && (
                  <span className="sources-panel__scanned-at"> · last scanned {new Date(s.last_scanned_at).toLocaleString()}</span>
                )}
              </div>
              {lastResults[s.source_id] && <p className="sources-panel__scan-note">{scanSummary(lastResults[s.source_id]!)}</p>}
              <div className="sources-panel__row-actions">
                <button type="button" onClick={() => handleRescan(s.source_id)} disabled={rescanSource.isPending}>
                  Rescan
                </button>
                <button
                  type="button"
                  className="sources-panel__remove"
                  onClick={() => handleRemove(s.source_id, s.path)}
                  disabled={deleteSource.isPending}
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
