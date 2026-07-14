import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useRuns, useSearch } from '@lib/api/hooks'
import { api } from '@lib/api/client'
import { useScopeStore } from '@state/useScopeStore'
import { useSelectionStore } from '@state/useSelectionStore'
import { usePinStore } from '@state/usePinStore'
import type { SearchResult } from '@lib/contract/types'
import './TopBar.css'

export function TopBar() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const { data: results } = useSearch(query)
  const { data: runs } = useRuns()
  const { runId, datasetId, setScope } = useScopeStore()
  const select = useSelectionStore((s) => s.select)
  const pinned = usePinStore((s) => s.pinned)

  function handleResultClick(r: SearchResult) {
    setOpen(false)
    setQuery('')
    if (r.kind === 'gene') {
      navigate(`/genes/${r.id}`)
    } else if (r.kind === 'pas') {
      api.getPas(r.id).then((pas) => {
        if (pas) select({ kind: 'pas', data: pas })
      })
      navigate('/audit')
    } else {
      api.getCell(r.id).then((cell) => {
        if (cell) select({ kind: 'cell', data: cell })
      })
      navigate('/audit')
    }
  }

  return (
    <header className="topbar" role="banner">
      <div className="topbar__brand">peakatail-hub</div>

      <div className="topbar__search">
        <input
          type="search"
          placeholder="Search gene / pas_uid / barcode…"
          aria-label="Global search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
        />
        {open && query.trim().length > 0 && (
          <ul className="topbar__search-results" role="listbox">
            {(results ?? []).length === 0 && <li className="topbar__search-empty">No matches</li>}
            {(results ?? []).map((r) => (
              <li key={`${r.kind}-${r.id}`}>
                <button type="button" onClick={() => handleResultClick(r)}>
                  <span className="badge badge--neutral">{r.kind}</span>
                  <span>{r.label}</span>
                  {r.sublabel && <span className="topbar__search-sub">{r.sublabel}</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <label className="topbar__scope">
        <span>Scope</span>
        <select
          value={runId ?? ''}
          onChange={(e) => {
            const run = (runs ?? []).find((r) => r.run_id === e.target.value)
            if (run) setScope(run.run_id, run.dataset_id)
          }}
        >
          <option value="" disabled>
            {runs === undefined ? 'Loading runs…' : 'Select a run'}
          </option>
          {(runs ?? []).map((r) => (
            <option key={r.run_id} value={r.run_id}>
              {r.label}
            </option>
          ))}
        </select>
      </label>

      <div className="topbar__pins" title="Pinned entities">
        <span aria-hidden>📌</span>
        <span>{pinned.length}</span>
      </div>

      <button type="button" className="topbar__settings" aria-label="Settings" title="Settings (stub)">
        ⚙
      </button>

      {datasetId && <span className="topbar__dataset-hint">dataset: {datasetId}</span>}
    </header>
  )
}
