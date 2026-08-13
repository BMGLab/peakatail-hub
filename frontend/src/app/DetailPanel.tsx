import { useNavigate } from 'react-router-dom'
import { useSelectionStore } from '@state/useSelectionStore'
import { usePinStore } from '@state/usePinStore'
import type { CellDetail, GeneSummary, GeneviewPas, GeneviewPasSelection, PasDetail, SelectedEntity } from '@lib/contract/types'
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

function OpenGeneviewButton({ geneId }: { geneId: string }) {
  const navigate = useNavigate()
  return (
    <button type="button" onClick={() => navigate(`/genes/${geneId}`)}>
      Open geneview
    </button>
  )
}

function GeneFields({ gene }: { gene: GeneSummary }) {
  const hasSpan = gene.chrom !== null && gene.start !== null && gene.end !== null && gene.strand !== null
  return (
    <dl className="detail-panel__fields">
      <dt>gene_id</dt>
      <dd>{gene.gene_id}</dd>
      <dt>locus</dt>
      {/* span is null when the gene has zero surviving PAS -- fail loud
          per spec §5 ("missing artifact -> coordinates unavailable, not
          blank"), never render a "null:null-null" locus string. */}
      <dd>{hasSpan ? `${gene.chrom}:${gene.start}-${gene.end} (${gene.strand})` : 'coordinates unavailable'}</dd>
      <dt>n_pas</dt>
      <dd>{gene.n_pas}</dd>
    </dl>
  )
}

/** True for a full `/pas/{id}(+/provenance)` fetch; false for a `GeneviewPas`
 * clicked straight off the geneview canvas, which only carries windowed
 * coordinates/tier/distances (see GeneviewPas's doc comment in types.ts) --
 * `PasFields` renders whichever fields it actually has rather than assuming
 * every selection is a full PasDetail. */
function isFullPasDetail(pas: PasDetail | GeneviewPas): pas is PasDetail {
  return 'last_stage' in pas
}

/** True for a `GeneviewPasSelection` -- a PAS clicked off the geneview
 * canvas's cluster-proportion bars/PAS bands, enriched at click-time with
 * whatever the canvas already had in hand (see that type's doc comment).
 * Purely additive: absent on a plain `GeneviewPas`/`PasDetail`. */
function isGeneviewSelection(pas: PasDetail | GeneviewPas | GeneviewPasSelection): pas is GeneviewPasSelection {
  return 'cluster_proportions' in pas || 'diff_summary' in pas || 'length_summary' in pas
}

function PasFields({ pas }: { pas: PasDetail | GeneviewPas | GeneviewPasSelection }) {
  const full = isFullPasDetail(pas) ? pas : null
  const enriched = isGeneviewSelection(pas) ? pas : null
  return (
    <>
      <dl className="detail-panel__fields">
        <dt>pas_uid</dt>
        <dd>{pas.pas_uid}</dd>
        <dt>gene</dt>
        <dd>
          {(full?.gene_name ?? full?.gene_id) || '—'}
        </dd>
        <dt>coords</dt>
        <dd>
          {pas.chrom}:{pas.start}-{pas.end} ({pas.strand})
        </dd>
        <dt>tier</dt>
        <dd>{pas.tier ?? '—'}</dd>
        <dt>snap_distance_bp</dt>
        <dd>{pas.snap_distance_bp ?? 'N/A (no atlas-snap step, or not snapped)'}</dd>
        <dt>gene_distance_bp</dt>
        <dd>{pas.gene_distance_bp ?? (full?.gene_id ? 'N/A' : 'N/A (intergenic)')}</dd>
        <dt>last_stage</dt>
        <dd>{full?.last_stage ?? '—'}</dd>
        <dt>dropped_at</dt>
        <dd>{full ? full.dropped_at || '(not dropped)' : '—'}</dd>
      </dl>
      <div className="detail-panel__caveat">
        <span className="badge badge--warn">⚠ not UMI-deduplicated</span>
        <span>
          Per-cluster counts below are read counts, molecule-inflated.
          {!full && ' (Not available from the geneview window -- open this PAS’s own detail for real counts.)'}
        </span>
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

      {enriched?.cluster_proportions && Object.keys(enriched.cluster_proportions).length > 0 && (
        <>
          <h4>Within-gene proportion by cluster</h4>
          <table className="detail-panel__table">
            <thead>
              <tr>
                <th>cluster</th>
                <th>proportion</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(enriched.cluster_proportions).map(([cluster, p]) => (
                <tr key={cluster}>
                  <td>{cluster}</td>
                  <td>{p === null ? '—' : `${(p * 100).toFixed(0)}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {enriched?.diff_summary && enriched.diff_summary.length > 0 && (
        <>
          <h4>switch diff (called strategies)</h4>
          <table className="detail-panel__table">
            <thead>
              <tr>
                <th>strategy</th>
                <th>q</th>
                <th>Δ proportion</th>
                <th>direction</th>
              </tr>
            </thead>
            <tbody>
              {enriched.diff_summary.map((d) => (
                <tr key={d.strategy}>
                  <td>{d.strategy}</td>
                  <td>{d.qvalue.toFixed(4)}</td>
                  <td>{d.delta_proportion.toFixed(3)}</td>
                  <td>{d.direction}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {enriched?.length_summary && enriched.length_summary.length > 0 && (
        <>
          <h4>switch length (direction by strategy)</h4>
          <table className="detail-panel__table">
            <thead>
              <tr>
                <th>strategy</th>
                <th>direction</th>
              </tr>
            </thead>
            <tbody>
              {enriched.length_summary.map((l) => (
                <tr key={l.strategy}>
                  <td>{l.strategy}</td>
                  <td>{l.direction ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
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
    // Collapse to a slim rail when empty so views (the geneview especially)
    // get the ~320px back instead of it standing reserved-but-blank. The
    // panel expands automatically the moment something is selected. The hint
    // text stays in the DOM (vertical rail) so it's still discoverable.
    return (
      <aside className="detail-panel detail-panel--collapsed" aria-label="Detail panel">
        <div className="detail-panel__rail-hint">Nothing selected — click a row, PAS, or cell for details</div>
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
        {selected.kind === 'pas' && 'gene_id' in selected.data && selected.data.gene_id && (
          // Narrowing `selected.data` doesn't survive into this onClick
          // closure (TS can't prove it won't change by the time it fires),
          // so capture the already-narrowed gene_id as a plain string here.
          <OpenGeneviewButton geneId={selected.data.gene_id} />
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
