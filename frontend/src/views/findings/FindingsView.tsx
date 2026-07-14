import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useFindings, useFindingsFacets } from '@lib/api/hooks'
import type { FindingsParams } from '@lib/api/client'
import { useSelectionStore } from '@state/useSelectionStore'
import { usePinStore } from '@state/usePinStore'
import type { FindingRow } from '@lib/contract/types'
import { caveatFlagsFor } from './caveatFlags'
import { EmptyState, ErrorState, LoadingState } from '@views/shared/ViewStates'
import './FindingsView.css'

const columnHelper = createColumnHelper<FindingRow>()

const columns = [
  columnHelper.accessor('finding_uid', { header: 'finding', cell: (c) => <span className="mono">{c.getValue()}</span> }),
  columnHelper.accessor('gene_id', { header: 'gene' }),
  columnHelper.accessor('arm', { header: 'arm' }),
  columnHelper.accessor('strategy', { header: 'strategy' }),
  columnHelper.accessor('celltype', { header: 'celltype', cell: (c) => c.getValue() ?? '—' }),
  columnHelper.accessor('direction', { header: 'direction' }),
  columnHelper.accessor('utr_class', { header: 'utr_class', cell: (c) => c.getValue() ?? '—' }),
  columnHelper.accessor('qvalue', { header: 'q', cell: (c) => c.getValue().toFixed(4) }),
  columnHelper.accessor('delta_proportion', { header: 'Δ proportion', cell: (c) => c.getValue().toFixed(3) }),
  columnHelper.accessor('n_reads', { header: 'n_reads' }),
  columnHelper.display({
    id: 'caveats',
    header: 'caveats',
    cell: (c) => {
      const flags = caveatFlagsFor(c.row.original)
      if (flags.length === 0) return null
      return (
        <span className="findings-view__flags">
          {flags.map((f) => (
            <span key={f.key} className="badge badge--warn" title={f.tooltip}>
              {f.label}
            </span>
          ))}
        </span>
      )
    },
  }),
]

export function FindingsView() {
  const [filters, setFilters] = useState<FindingsParams>({ limit: 200 })
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const navigate = useNavigate()
  const select = useSelectionStore((s) => s.select)
  const pin = usePinStore((s) => s.pin)

  const facetsQuery = useFindingsFacets(filters)
  const findingsQuery = useFindings(filters)

  const rows = findingsQuery.data?.rows ?? []

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  })

  const parentRef = useRef<HTMLDivElement>(null)
  const { rows: tableRows } = table.getRowModel()
  const virtualizer = useVirtualizer({
    count: tableRows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 32,
    overscan: 12,
  })

  function updateFilter<K extends keyof FindingsParams>(key: K, value: FindingsParams[K]) {
    setFilters((prev) => ({ ...prev, [key]: value, cursor: 0 }))
  }

  function toggleSelected(row: FindingRow) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(row.finding_uid)) next.delete(row.finding_uid)
      else next.add(row.finding_uid)
      return next
    })
  }

  function pinSelected() {
    for (const row of rows) {
      if (selectedIds.has(row.finding_uid)) {
        pin({ kind: 'gene', id: row.gene_id, label: row.gene_id })
      }
    }
  }

  const facets = facetsQuery.data
  const virtualItems = useMemo(() => virtualizer.getVirtualItems(), [virtualizer])

  return (
    <div className="findings-view">
      <aside className="findings-view__facets panel">
        <h3>Facets</h3>
        {facetsQuery.isLoading && <LoadingState label="Loading facets…" />}
        {facetsQuery.isError && <ErrorState error={facetsQuery.error} onRetry={() => facetsQuery.refetch()} />}
        {facets && (
          <>
            <label>
              Arm
              <select value={filters.arm ?? ''} onChange={(e) => updateFilter('arm', e.target.value || undefined)}>
                <option value="">All</option>
                {facets.arm.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Strategy
              <select
                value={filters.strategy ?? ''}
                onChange={(e) => updateFilter('strategy', (e.target.value || undefined) as FindingsParams['strategy'])}
              >
                <option value="">All</option>
                {facets.strategy.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Celltype
              <select value={filters.celltype ?? ''} onChange={(e) => updateFilter('celltype', e.target.value || undefined)}>
                <option value="">All</option>
                {facets.celltype.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Direction
              <select
                value={filters.direction ?? ''}
                onChange={(e) => updateFilter('direction', (e.target.value || undefined) as FindingsParams['direction'])}
              >
                <option value="">All</option>
                {facets.direction.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label>
              UTR class
              <select value={filters.utr_class ?? ''} onChange={(e) => updateFilter('utr_class', e.target.value || undefined)}>
                <option value="">All</option>
                {facets.utr_class.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label>
              q ≤ {filters.q_max?.toFixed(3) ?? '1.000'}
              <input
                type="range"
                min={0}
                max={1}
                step={0.005}
                value={filters.q_max ?? 1}
                onChange={(e) => updateFilter('q_max', Number(e.target.value))}
              />
            </label>
            <label>
              min_reads
              <input
                type="number"
                min={0}
                value={filters.min_reads ?? 0}
                onChange={(e) => updateFilter('min_reads', Number(e.target.value))}
              />
            </label>
          </>
        )}
      </aside>

      <section className="findings-view__table-wrap">
        <div className="findings-view__toolbar">
          <span>
            {findingsQuery.data ? `${findingsQuery.data.total} findings (showing ${rows.length})` : ''}
          </span>
          <button type="button" disabled={selectedIds.size === 0} onClick={pinSelected}>
            Pin selected genes ({selectedIds.size})
          </button>
        </div>

        {findingsQuery.isLoading && <LoadingState label="Loading findings…" />}
        {findingsQuery.isError && <ErrorState error={findingsQuery.error} onRetry={() => findingsQuery.refetch()} />}
        {findingsQuery.isSuccess && rows.length === 0 && <EmptyState reason="no-match" />}

        {findingsQuery.isSuccess && rows.length > 0 && (
          <div ref={parentRef} className="findings-view__scroll">
            <table className="findings-view__table">
              <thead>
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    <th className="findings-view__select-col" />
                    {hg.headers.map((h) => (
                      <th key={h.id}>{flexRender(h.column.columnDef.header, h.getContext())}</th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody style={{ height: virtualizer.getTotalSize(), position: 'relative', display: 'block' }}>
                {virtualItems.map((vi) => {
                  const row = tableRows[vi.index]
                  if (!row) return null
                  const original = row.original
                  return (
                    <tr
                      key={row.id}
                      data-index={vi.index}
                      style={{ position: 'absolute', top: 0, left: 0, right: 0, transform: `translateY(${vi.start}px)`, display: 'table', width: '100%', tableLayout: 'fixed' }}
                      onClick={() => {
                        select({ kind: 'gene', data: { gene_id: original.gene_id, gene_name: original.gene_id, chrom: '', start: 0, end: 0, strand: '+', n_pas: 0 } })
                        navigate(`/genes/${original.gene_id}`)
                      }}
                    >
                      <td className="findings-view__select-col">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(original.finding_uid)}
                          onClick={(e) => e.stopPropagation()}
                          onChange={() => toggleSelected(original)}
                        />
                      </td>
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
