import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createColumnHelper } from '@tanstack/react-table'
import { useCellsBrowse } from '@lib/api/hooks'
import { api } from '@lib/api/client'
import { useScopeStore } from '@state/useScopeStore'
import { useSelectionStore } from '@state/useSelectionStore'
import type { CellLedgerRow } from '@lib/contract/types'
import { BrowseTable } from './BrowseTable'

const columnHelper = createColumnHelper<CellLedgerRow>()

const columns = [
  columnHelper.accessor('barcode', {
    header: 'barcode',
    cell: (c) => (
      <span className="mono truncate" title={c.getValue()}>
        {c.getValue()}
      </span>
    ),
  }),
  columnHelper.accessor('cell_uid', {
    header: 'cell_uid',
    cell: (c) => (
      <span className="mono truncate" title={c.getValue()}>
        {c.getValue()}
      </span>
    ),
  }),
  columnHelper.accessor('cluster', { header: 'cluster', cell: (c) => c.getValue() ?? '—' }),
  columnHelper.accessor('total_reads', { header: 'total_reads', cell: (c) => <span className="num">{c.getValue()}</span> }),
  columnHelper.accessor('n_pas', {
    header: '#PAS',
    cell: (c) => (
      <span className="num" title="PAS-per-cell, not gene count">
        {c.getValue()}
      </span>
    ),
  }),
  columnHelper.accessor('dropped_at', {
    header: 'status',
    cell: (c) => {
      const stage = c.getValue()
      const reason = c.row.original.drop_reason
      return stage ? (
        <span className="badge badge--warn" title={reason ?? undefined}>
          dropped @ {stage}
        </span>
      ) : (
        <span className="badge badge--ok">survived</span>
      )
    },
  }),
]

/**
 * The cell browser: searchable, virtualized list over the full cell ledger
 * (survived + dropped, same rationale as PasBrowser). Row click fetches the
 * full CellDetail via `api.getCell` (same path TopBar's search dropdown
 * uses) and opens Audit, where cell provenance is traced.
 */
export function CellBrowser() {
  const [q, setQ] = useState<string | undefined>(undefined)
  const navigate = useNavigate()
  const select = useSelectionStore((s) => s.select)
  const runId = useScopeStore((s) => s.runId)

  const query = useCellsBrowse({ q, run_id: runId ?? undefined, limit: 300 })
  const rows = query.data?.rows ?? []

  function openCell(row: CellLedgerRow) {
    api.getCell(row.cell_uid).then((cell) => {
      if (cell) select({ kind: 'cell', data: cell })
    })
    navigate('/audit')
  }

  return (
    <BrowseTable
      title="Cells"
      placeholder="Search barcode / cell_uid / cluster…"
      columns={columns}
      rows={rows}
      total={query.data?.total ?? 0}
      isLoading={query.isLoading}
      isError={query.isError}
      error={query.error}
      onRetry={() => query.refetch()}
      onRowClick={openCell}
      getRowId={(r) => r.cell_uid}
      onQueryChange={(text) => setQ(text.trim() || undefined)}
    />
  )
}
