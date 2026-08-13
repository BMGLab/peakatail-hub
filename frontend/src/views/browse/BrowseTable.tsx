import { useEffect, useRef, useState } from 'react'
import { type ColumnDef, flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { EmptyState, ErrorState, LoadingState } from '@views/shared/ViewStates'
import { PageHeader } from '@views/shared/PageHeader'
import './BrowseTable.css'

export interface BrowseTableProps<T> {
  /** Shown as the panel heading, e.g. "Genes". */
  title: string
  /** 1-3 sentence explanation of what this browser lists and how to read it. */
  description: string
  placeholder: string
  columns: ColumnDef<T, any>[] // eslint-disable-line @typescript-eslint/no-explicit-any
  rows: T[]
  total: number
  isLoading: boolean
  isError: boolean
  error: unknown
  onRetry: () => void
  onRowClick: (row: T) => void
  getRowId: (row: T) => string
  /** Called with the debounced search text (300ms after the user stops typing). */
  onQueryChange: (q: string) => void
}

/**
 * Shared virtualized, searchable, selectable table for the gene/PAS/cell
 * browsers (views/browse/**). Mirrors FindingsView's proven virtualizer
 * setup exactly -- same `initialRect` + always-mounted-scroll-container +
 * non-memoized `getVirtualItems()` fixes for the "showing N but zero <tr>s
 * render" bug documented there, since this is the same virtualization
 * library used the same way.
 */
export function BrowseTable<T>({
  title,
  description,
  placeholder,
  columns,
  rows,
  total,
  isLoading,
  isError,
  error,
  onRetry,
  onRowClick,
  getRowId,
  onQueryChange,
}: BrowseTableProps<T>) {
  const [text, setText] = useState('')

  // Debounce the search box -> query invalidation so typing doesn't fire a
  // request per keystroke.
  useEffect(() => {
    const id = setTimeout(() => onQueryChange(text), 300)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text])

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId,
  })

  const parentRef = useRef<HTMLDivElement>(null)
  const { rows: tableRows } = table.getRowModel()
  const virtualizer = useVirtualizer({
    count: tableRows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 32,
    overscan: 12,
    initialRect: { width: 0, height: 600 },
  })
  const virtualItems = virtualizer.getVirtualItems()

  return (
    <div className="browse-table">
      <PageHeader title={title} description={description} />
      <div className="browse-table__toolbar">
        <input
          type="search"
          className="browse-table__search"
          placeholder={placeholder}
          aria-label={`Search ${title.toLowerCase()}`}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <span className="browse-table__count">
          {isLoading && rows.length === 0 ? 'Loading…' : `${total.toLocaleString()} ${title.toLowerCase()}`}
        </span>
      </div>

      <div ref={parentRef} className="browse-table__scroll">
        {isLoading && rows.length === 0 && <LoadingState label={`Loading ${title.toLowerCase()}…`} />}
        {isError && <ErrorState error={error} onRetry={onRetry} />}
        {!isLoading && !isError && rows.length === 0 && <EmptyState reason="no-match" />}

        {rows.length > 0 && (
          <table className="data-table browse-table__table">
            <thead>
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
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
                return (
                  <tr
                    key={row.id}
                    data-index={vi.index}
                    style={{ position: 'absolute', top: 0, left: 0, right: 0, transform: `translateY(${vi.start}px)`, width: '100%' }}
                    onClick={() => onRowClick(row.original)}
                    className="browse-table__row"
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
