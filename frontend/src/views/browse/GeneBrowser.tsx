import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createColumnHelper } from '@tanstack/react-table'
import { useGenesBrowse } from '@lib/api/hooks'
import { useScopeStore } from '@state/useScopeStore'
import { useSelectionStore } from '@state/useSelectionStore'
import type { GeneListRow } from '@lib/contract/types'
import { BrowseTable } from './BrowseTable'

const columnHelper = createColumnHelper<GeneListRow>()

const columns = [
  columnHelper.accessor('gene_id', {
    header: 'gene_id',
    cell: (c) => (
      <span className="mono truncate" title={c.getValue()}>
        {c.getValue()}
      </span>
    ),
  }),
  columnHelper.display({
    id: 'locus',
    header: 'locus',
    cell: (c) => {
      const g = c.row.original
      const locus = g.chrom && g.start !== null && g.end !== null ? `${g.chrom}:${g.start.toLocaleString()}-${g.end.toLocaleString()}` : null
      return locus ? (
        <span className="mono truncate" title={locus}>
          {locus}
        </span>
      ) : (
        <span title="No surviving PAS -- span unavailable">—</span>
      )
    },
  }),
  columnHelper.accessor('strand', { header: 'strand', cell: (c) => c.getValue() ?? '—' }),
  columnHelper.accessor('n_pas', { header: '#PAS', cell: (c) => <span className="num">{c.getValue()}</span> }),
  columnHelper.accessor('n_findings', { header: '#findings', cell: (c) => <span className="num">{c.getValue()}</span> }),
]

/**
 * The gene browser: searchable, virtualized list of every gene with at
 * least one surviving PAS. Selecting a row is the same "jump the geneview
 * to this locus" action as the TopBar's location bar -- it opens the
 * geneview at the gene's full span and populates the detail panel from the
 * row data already on hand (no extra round trip; GeneView's own /genes/{id}
 * fetch will supersede this once it loads).
 */
export function GeneBrowser() {
  const [q, setQ] = useState<string | undefined>(undefined)
  const navigate = useNavigate()
  const select = useSelectionStore((s) => s.select)
  const runId = useScopeStore((s) => s.runId)

  const query = useGenesBrowse({ q, run_id: runId ?? undefined, limit: 300 })
  const rows = query.data?.rows ?? []

  function openGene(row: GeneListRow) {
    select({
      kind: 'gene',
      data: {
        gene_id: row.gene_id,
        gene_name: row.gene_id,
        chrom: row.chrom,
        start: row.start,
        end: row.end,
        strand: row.strand,
        n_pas: row.n_pas,
      },
    })
    navigate(`/genes/${row.gene_id}`)
  }

  return (
    <BrowseTable
      title="Genes"
      description="Every gene with at least one poly(A) site surviving filtering in the selected run. Search by gene symbol or Ensembl gene id; click a row to open it in the Browser track view."
      placeholder="Search gene_id (symbol/ENSG)…"
      columns={columns}
      rows={rows}
      total={query.data?.total ?? 0}
      isLoading={query.isLoading}
      isError={query.isError}
      error={query.error}
      onRetry={() => query.refetch()}
      onRowClick={openGene}
      getRowId={(r) => r.gene_id}
      onQueryChange={(text) => setQ(text.trim() || undefined)}
    />
  )
}
