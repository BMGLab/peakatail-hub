import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createColumnHelper } from '@tanstack/react-table'
import { usePasBrowse } from '@lib/api/hooks'
import { api } from '@lib/api/client'
import { useScopeStore } from '@state/useScopeStore'
import { useSelectionStore } from '@state/useSelectionStore'
import type { PasLedgerRow } from '@lib/contract/types'
import { BrowseTable } from './BrowseTable'

const columnHelper = createColumnHelper<PasLedgerRow>()

const columns = [
  columnHelper.accessor('pas_uid', {
    header: 'pas_uid',
    cell: (c) => (
      <span className="mono truncate" title={c.getValue()}>
        {c.getValue()}
      </span>
    ),
  }),
  // "Gene" = the human-readable symbol (2026-08-14); gene_id stays its own
  // column right after it (the stable id, never dropped).
  columnHelper.accessor('gene_symbol', {
    header: 'Gene',
    cell: (c) => {
      const v = c.getValue()
      if (v) return v
      return c.row.original.gene_id ? (
        <span className="state-message">—</span>
      ) : (
        <span className="badge badge--neutral" title="No gene within max_gene_distance">
          intergenic
        </span>
      )
    },
  }),
  columnHelper.accessor('gene_id', {
    header: 'gene_id',
    cell: (c) => {
      const v = c.getValue()
      return v ? (
        <span className="mono truncate" title={v}>
          {v}
        </span>
      ) : (
        '—'
      )
    },
  }),
  columnHelper.display({
    id: 'locus',
    header: 'locus',
    cell: (c) => {
      const p = c.row.original
      const locus = `${p.chrom}:${p.start.toLocaleString()}-${p.end.toLocaleString()} (${p.strand})`
      return (
        <span className="mono truncate" title={locus}>
          {locus}
        </span>
      )
    },
  }),
  columnHelper.accessor('tier', { header: 'tier', cell: (c) => c.getValue() ?? '—' }),
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
 * The PAS browser: searchable, virtualized list over the FULL ledger
 * (survived + dropped alike -- a provenance browser, same as AuditView's
 * single-PAS trace, not a render feed). Row click fetches the full
 * PasDetail via the shared `api.getPas` path (same normalization TopBar's
 * search dropdown already uses) rather than synthesizing a partial detail
 * object, then jumps the geneview if the PAS has a gene, else opens Audit.
 */
export function PasBrowser() {
  const [q, setQ] = useState<string | undefined>(undefined)
  const navigate = useNavigate()
  const select = useSelectionStore((s) => s.select)
  const runId = useScopeStore((s) => s.runId)

  const query = usePasBrowse({ q, run_id: runId ?? undefined, limit: 300 })
  const rows = query.data?.rows ?? []

  function openPas(row: PasLedgerRow) {
    api.getPas(row.pas_uid).then((pas) => {
      if (pas) select({ kind: 'pas', data: pas })
    })
    if (row.gene_id) {
      navigate(`/genes/${row.gene_id}`)
    } else {
      navigate('/audit')
    }
  }

  return (
    <BrowseTable
      title="PAS"
      placeholder="Search pas_uid / gene_id…"
      columns={columns}
      rows={rows}
      total={query.data?.total ?? 0}
      isLoading={query.isLoading}
      isError={query.isError}
      error={query.error}
      onRetry={() => query.refetch()}
      onRowClick={openPas}
      getRowId={(r) => r.pas_uid}
      onQueryChange={(text) => setQ(text.trim() || undefined)}
    />
  )
}
