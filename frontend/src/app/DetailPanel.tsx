import { useNavigate } from 'react-router-dom'
import { useSelectionStore } from '@state/useSelectionStore'
import { usePinStore } from '@state/usePinStore'
import type { CellDetail, GeneSummary, PasDetail, SelectedEntity } from '@lib/contract/types'
import './DetailPanel.css'

function labelFor(entity: SelectedEntity): string {
  if (entity.kind === 'gene') return entity.data.gene_name
  if (entity.kind === 'pas') return entity.data.pas_uid
  return entity.data.barcode
}

function idFor(entity: SelectedEntity): string {
  if (entity.kind === 'gene') return entity.data.gene_id
  if (entity.kind === 'pas') return entity.data.pas_uid
  return entity.data.cell_uid
}

function GeneFields({ gene }: { gene: GeneSummary }) {
  return (
    <dl className="detail-panel__fields">
      <dt>gene_id</dt>
      <dd>{gene.gene_id}</dd>
      <dt>locus</dt>
      <dd>
        {gene.chrom}:{gene.start}-{gene.end} ({gene.strand})
      </dd>
      <dt>n_pas</dt>
      <dd>{gene.n_pas}</dd>
    </dl>
  )
}

function PasFields({ pas }: { pas: PasDetail }) {
  return (
    <>
      <dl className="detail-panel__fields">
        <dt>pas_uid</dt>
        <dd>{pas.pas_uid}</dd>
        <dt>gene</dt>
        <dd>
          {pas.gene_name ?? '—'} ({pas.gene_id ?? '—'})
        </dd>
        <dt>coords</dt>
        <dd>
          {pas.chrom}:{pas.start}-{pas.end} ({pas.strand})
        </dd>
        <dt>tier</dt>
        <dd>{pas.tier ?? '—'}</dd>
        <dt>snap_distance_bp</dt>
        <dd>{pas.snap_distance_bp ?? '—'}</dd>
        <dt>gene_distance_bp</dt>
        <dd>{pas.gene_distance_bp ?? '—'}</dd>
        <dt>last_stage</dt>
        <dd>{pas.last_stage}</dd>
        <dt>dropped_at</dt>
        <dd>{pas.dropped_at || '(not dropped)'}</dd>
      </dl>
      <div className="detail-panel__caveat">
        <span className="badge badge--warn">⚠ not UMI-deduplicated</span>
        <span>Per-cluster counts below are read counts, molecule-inflated.</span>
      </div>
      <table className="detail-panel__table">
        <thead>
          <tr>
            <th>cluster</th>
            <th>reads</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(pas.per_cluster_counts).map(([cluster, n]) => (
            <tr key={cluster}>
              <td>{cluster}</td>
              <td>{n}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

function CellFields({ cell }: { cell: CellDetail }) {
  return (
    <dl className="detail-panel__fields">
      <dt>barcode</dt>
      <dd>{cell.barcode}</dd>
      <dt>cluster</dt>
      <dd>{cell.cluster ?? '—'}</dd>
      <dt>celltype</dt>
      <dd>{cell.celltype ?? '—'}</dd>
      <dt>total_reads</dt>
      <dd>{cell.total_reads}</dd>
      <dt>
        n_pas <span className="badge badge--neutral" title="obs['n_genes'] is PAS-per-cell, never genes">PAS, not genes</span>
      </dt>
      <dd>{cell.n_pas}</dd>
      <dt>dropped_at</dt>
      <dd>{cell.dropped_at || '(not dropped)'}</dd>
    </dl>
  )
}

export function DetailPanel() {
  const selected = useSelectionStore((s) => s.selected)
  const clear = useSelectionStore((s) => s.clear)
  const pin = usePinStore((s) => s.pin)
  const isPinned = usePinStore((s) => s.isPinned)
  const navigate = useNavigate()

  if (!selected) {
    return (
      <aside className="detail-panel" aria-label="Detail panel">
        <div className="state-message">Nothing selected. Click a row, PAS, or cell to see details here.</div>
      </aside>
    )
  }

  const label = labelFor(selected)
  const id = idFor(selected)
  const pinned = isPinned(selected.kind, id)

  return (
    <aside className="detail-panel" aria-label="Detail panel">
      <div className="detail-panel__header">
        <span className="badge badge--neutral">{selected.kind}</span>
        <h3>{label}</h3>
        <button type="button" className="detail-panel__close" onClick={clear} aria-label="Close detail panel">
          ×
        </button>
      </div>

      <div className="detail-panel__body">
        {selected.kind === 'gene' && <GeneFields gene={selected.data} />}
        {selected.kind === 'pas' && <PasFields pas={selected.data} />}
        {selected.kind === 'cell' && <CellFields cell={selected.data} />}
      </div>

      <div className="detail-panel__actions">
        {selected.kind === 'pas' && selected.data.gene_id && (
          <button type="button" onClick={() => navigate(`/genes/${selected.data.gene_id}`)}>
            Open geneview
          </button>
        )}
        {selected.kind === 'gene' && (
          <button type="button" onClick={() => navigate(`/genes/${selected.data.gene_id}`)}>
            Open geneview
          </button>
        )}
        <button type="button" onClick={() => navigate('/audit')}>
          Trace provenance
        </button>
        <button
          type="button"
          disabled={pinned}
          onClick={() => pin({ kind: selected.kind, id, label })}
        >
          {pinned ? 'Pinned' : 'Pin'}
        </button>
      </div>
    </aside>
  )
}
