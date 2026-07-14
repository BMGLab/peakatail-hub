import { useRef, useState } from 'react'
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

// Per-column display width (px), read via `column.columnDef.meta.width` in
// the header/cell render below. FIX: every column previously rendered with
// a uniform `flex: 1 1 0` (see FindingsView.css's docstring for why rows
// are flex boxes, not a real <table> layout) -- that gives every column an
// EQUAL share of the available width regardless of content, which is what
// squeezed `finding_uid`/`gene_id`/`arm`/`utr_class` down to unreadable
// "cl_A…/ENS…/tand…" truncation. Real per-column widths (id-shaped columns
// get more room, short enums get less) fix that; `.truncate` + a `title`
// attribute keeps the still-truncated long values inspectable on hover.
declare module '@tanstack/react-table' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData, TValue> {
    /** Column width in px -- rendered as `flex: 0 0 <width>px` (no grow/shrink competing with neighbors). */
    width: number
    /** Right-align + tabular-nums styling for numeric columns. */
    numeric?: boolean
  }
}

const columnHelper = createColumnHelper<FindingRow>()

const columns = [
  columnHelper.accessor('finding_uid', {
    header: 'finding',
    meta: { width: 340 },
    cell: (c) => (
      <span className="mono truncate" title={c.getValue()}>
        {c.getValue()}
      </span>
    ),
  }),
  columnHelper.accessor('gene_id', {
    header: 'gene',
    meta: { width: 150 },
    cell: (c) => (
      <span className="mono truncate" title={c.getValue()}>
        {c.getValue()}
      </span>
    ),
  }),
  columnHelper.accessor('arm', {
    header: 'arm',
    meta: { width: 150 },
    cell: (c) => (
      <span className="truncate" title={c.getValue()}>
        {c.getValue()}
      </span>
    ),
  }),
  columnHelper.accessor('strategy', { header: 'strategy', meta: { width: 110 } }),
  columnHelper.accessor('celltype', {
    header: 'celltype',
    meta: { width: 150 },
    cell: (c) => {
      const v = c.getValue()
      return v ? (
        <span className="truncate" title={v}>
          {v}
        </span>
      ) : (
        '—'
      )
    },
  }),
  columnHelper.accessor('direction', { header: 'direction', meta: { width: 110 } }),
  columnHelper.accessor('utr_class', { header: 'utr_class', meta: { width: 120 }, cell: (c) => c.getValue() ?? '—' }),
  columnHelper.accessor('qvalue', { header: 'q', meta: { width: 80, numeric: true }, cell: (c) => c.getValue().toFixed(4) }),
  columnHelper.accessor('delta_proportion', {
    header: 'Δ proportion',
    meta: { width: 120, numeric: true },
    cell: (c) => c.getValue().toFixed(3),
  }),
  columnHelper.accessor('n_reads', { header: 'n_reads', meta: { width: 90, numeric: true } }),
  columnHelper.display({
    id: 'caveats',
    header: 'caveats',
    meta: { width: 180 },
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
    // Root cause of the "totalSize is right but getVirtualItems() is always
    // []" bug: virtual-core's calculateRange() bails to `null` whenever
    // outerSize===0, and outerSize falls back to `options.initialRect`
    // (default {width:0,height:0}) until the ResizeObserver set up by
    // observeElementRect fires at least once. In this environment that
    // observer callback was never firing (headless/sandboxed rendering
    // quirk), so the range stayed permanently null. A non-zero
    // initialRect makes the very first render usable; a real
    // ResizeObserver tick (if it ever comes) still overwrites it later.
    initialRect: { width: 0, height: 600 },
  })

  function updateFilter<K extends keyof FindingsParams>(key: K, value: FindingsParams[K]) {
    setFilters((prev) => {
      // exactOptionalPropertyTypes: reset to "first page" by omitting
      // `cursor` entirely, never `cursor: undefined` (the backend's opaque
      // cursor type has no "explicitly present but empty" state).
      const { cursor: _cursor, ...rest } = prev
      return { ...rest, [key]: value }
    })
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
  // NOT `useMemo(..., [virtualizer])` -- `virtualizer` is the SAME mutated-
  // in-place instance across renders (react-virtual doesn't hand back a new
  // object each render), so a memo keyed on its reference computes
  // getVirtualItems() exactly once (on mount, before any row was measured
  // or the scroll element had a size) and then NEVER recomputes as data
  // loads -- this was the actual cause of "totalSize is right but zero
  // <tr>s render": virtual-core already does its own correctly-keyed
  // internal memoization, so this just needs to be called fresh every
  // render, not re-wrapped in an outer memo with the wrong deps.
  const virtualItems = virtualizer.getVirtualItems()

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
          <span>{findingsQuery.data ? `${findingsQuery.data.total} findings (showing ${rows.length})` : ''}</span>
          <button type="button" disabled={selectedIds.size === 0} onClick={pinSelected}>
            Pin selected genes ({selectedIds.size})
          </button>
        </div>

        {/*
          The scroll container is ALWAYS mounted (never gated behind
          findingsQuery.isSuccess) so `parentRef` is attached to a real DOM
          node from first render. useVirtualizer's ResizeObserver attaches
          to whatever `getScrollElement()` returns at mount time; if this
          div only appeared once data loaded, the observer would never see
          it and getVirtualItems() would stay stuck at [] forever even
          though getTotalSize() (which only needs `count`, not a live
          measurement) looked correct -- exactly the "showing N" but zero
          rendered <tr>s bug this fixes.
        */}
        <div ref={parentRef} className="findings-view__scroll">
          {findingsQuery.isLoading && <LoadingState label="Loading findings…" />}
          {findingsQuery.isError && <ErrorState error={findingsQuery.error} onRetry={() => findingsQuery.refetch()} />}
          {findingsQuery.isSuccess && rows.length === 0 && <EmptyState reason="no-match" />}

          {findingsQuery.isSuccess && rows.length > 0 && (
            <table className="findings-view__table">
              <thead>
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    <th className="findings-view__select-col" />
                    {hg.headers.map((h) => {
                      const meta = h.column.columnDef.meta
                      return (
                        <th
                          key={h.id}
                          style={meta ? { flex: `0 0 ${meta.width}px`, width: meta.width } : undefined}
                          className={meta?.numeric ? 'num' : undefined}
                        >
                          {flexRender(h.column.columnDef.header, h.getContext())}
                        </th>
                      )
                    })}
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
                      style={{ position: 'absolute', top: 0, left: 0, right: 0, transform: `translateY(${vi.start}px)`, width: '100%' }}
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
                      {row.getVisibleCells().map((cell) => {
                        const meta = cell.column.columnDef.meta
                        return (
                          <td
                            key={cell.id}
                            style={meta ? { flex: `0 0 ${meta.width}px`, width: meta.width } : undefined}
                            className={meta?.numeric ? 'num' : undefined}
                          >
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  )
}
