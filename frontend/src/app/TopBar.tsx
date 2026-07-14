import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useRuns, useSearch } from '@lib/api/hooks'
import { api } from '@lib/api/client'
import { useScopeStore } from '@state/useScopeStore'
import { useSelectionStore } from '@state/useSelectionStore'
import { usePinStore } from '@state/usePinStore'
import { useDrawerStore } from '@state/useDrawerStore'
import type { RunSummary, SearchResult } from '@lib/contract/types'
import './TopBar.css'

/**
 * There is no flat `RunSummary.label` on the real backend response --
 * derive a readable option string instead of assuming one exists. Prefers
 * the manifest's resolved stratum labels (D10-safe, not a truncated
 * directory name) when there's exactly one; otherwise falls back to the
 * bare run_id plus a cell count for orientation.
 */
function runLabel(run: RunSummary): string {
  const labels = Object.values(run.stratum_to_label)
  if (labels.length === 1 && labels[0]) return labels[0]
  const cells = run.n_cells != null ? `${run.n_cells.toLocaleString()} cells` : null
  return cells ? `${run.run_id} (${cells})` : run.run_id
}

/** `chrN:start` or `chrN:start-end`, optionally comma-grouped
 * (`chrX:155,277,212-155,287,685`, matching how coordinates are usually
 * copy-pasted out of a genome browser or the package's own figures). Not
 * anchored to a strict `chr` prefix -- accepts any contig name the ledger
 * uses (`chrom` is a free-text VARCHAR in the store, see store/schema.py). */
const LOCUS_RE = /^([A-Za-z0-9_.]+):([\d,]+)(?:-([\d,]+))?$/

export function TopBar() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [locusNotFound, setLocusNotFound] = useState(false)
  const { data: results } = useSearch(query)
  const { data: runs } = useRuns()
  const { runId, datasetId, setScope } = useScopeStore()
  const select = useSelectionStore((s) => s.select)
  const pinned = usePinStore((s) => s.pinned)
  const findingsOpen = useDrawerStore((s) => s.findingsOpen)
  const toggleFindings = useDrawerStore((s) => s.toggleFindings)

  function handleResultClick(r: SearchResult) {
    setOpen(false)
    setQuery('')
    setLocusNotFound(false)
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

  /**
   * The primary action: accept a gene symbol, ENSG id, pas_uid, or raw
   * `chr:start-end` locus and jump the genome browser straight to it (IGV's
   * "location box" behavior), on Enter -- no need to open the dropdown and
   * click a specific suggestion first.
   */
  async function jumpToLocation() {
    const trimmed = query.trim()
    if (!trimmed) return

    const m = LOCUS_RE.exec(trimmed)
    if (m) {
      const chrom = m[1]!
      const start = Number(m[2]!.replace(/,/g, ''))
      const end = m[3] ? Number(m[3].replace(/,/g, '')) : start
      const page = await api.listGenes({ chrom, start, end, limit: 1, run_id: runId ?? undefined })
      const gene = page.rows[0]
      if (gene) {
        setLocusNotFound(false)
        setOpen(false)
        setQuery('')
        navigate(`/genes/${gene.gene_id}`)
      } else {
        // Leave the query visible so the user sees exactly what didn't
        // resolve, rather than silently clearing a locus that found nothing.
        setLocusNotFound(true)
      }
      return
    }

    // Not a locus -- resolve like the dropdown, but jump straight to the
    // top match instead of requiring a click.
    const matches = await api.search(trimmed)
    if (matches[0]) {
      handleResultClick(matches[0])
    } else {
      setLocusNotFound(true)
    }
  }

  return (
    <header className="topbar" role="banner">
      <div className="topbar__brand">
        peakatail<span className="topbar__brand-accent">-hub</span>
      </div>

      <form
        className="topbar__location"
        role="search"
        onSubmit={(e) => {
          e.preventDefault()
          void jumpToLocation()
        }}
      >
        <span className="topbar__location-icon" aria-hidden>
          ⌖
        </span>
        <input
          type="search"
          className="topbar__location-input"
          placeholder="Jump to gene, ENSG, pas_uid, or chr:start-end…"
          aria-label="Genome location search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
            setLocusNotFound(false)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
        />
        {open && query.trim().length > 0 && (
          <ul className="topbar__location-results" role="listbox">
            {LOCUS_RE.test(query.trim()) ? (
              <li className="topbar__location-hint">Press Enter to jump to this locus</li>
            ) : (
              <>
                {(results ?? []).length === 0 && <li className="topbar__location-empty">No matches</li>}
                {(results ?? []).map((r) => (
                  <li key={`${r.kind}-${r.id}`}>
                    <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => handleResultClick(r)}>
                      <span className="badge badge--neutral">{r.kind}</span>
                      <span>{r.label}</span>
                      {r.sublabel && <span className="topbar__location-sub">{r.sublabel}</span>}
                    </button>
                  </li>
                ))}
              </>
            )}
          </ul>
        )}
        {locusNotFound && <span className="topbar__location-notfound">No gene found there.</span>}
      </form>

      <label className="topbar__scope">
        <span>Scope</span>
        <select
          value={runId ?? ''}
          onChange={(e) => {
            const run = (runs ?? []).find((r) => r.run_id === e.target.value)
            // The backend's RunSummary has no single flat `dataset_id`/
            // `label` (a run can span n_datasets > 1 -- see
            // `stratum_to_label`). The scope's "datasetId" is really "which
            // run" as far as the UMAP/QC endpoints are concerned (spec: GET
            // /datasets/{run_id}/umap takes the RUN id in that path slot,
            // an optional `?dataset_id=` narrows further within it, no UI
            // for that yet) -- run_id in both slots, not `run.dataset_id`
            // (that field never existed on the real response; every view
            // gated on scope silently 404'd on `/datasets/undefined/...`).
            if (run) setScope(run.run_id, run.run_id)
          }}
        >
          <option value="" disabled>
            {runs === undefined ? 'Loading runs…' : 'Select a run'}
          </option>
          {(runs ?? []).map((r) => (
            <option key={r.run_id} value={r.run_id}>
              {runLabel(r)}
            </option>
          ))}
        </select>
      </label>

      <button
        type="button"
        className={findingsOpen ? 'topbar__findings topbar__findings--active' : 'topbar__findings'}
        onClick={toggleFindings}
        aria-pressed={findingsOpen}
        title="Findings table (secondary panel)"
      >
        Findings
      </button>

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
