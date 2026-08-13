import { useState } from 'react'
import { usePasProvenance, useCellProvenance } from '@lib/api/hooks'
import { useSelectionStore } from '@state/useSelectionStore'
import { EmptyState, LoadingState, MissingArtifactNotice } from '@views/shared/ViewStates'
import { PageHeader } from '@views/shared/PageHeader'
import type { CellDetail, PasDetail } from '@lib/contract/types'
import './AuditView.css'

// Pipeline stage order used for the trail stepper. Mirrors the 7-stage funnel
// on the QC view; kept as a local constant here since the contract package
// doesn't yet expose a canonical stage-order enum (see docs §7c "QC 7-stage
// funnel" gate).
const STAGE_ORDER = ['raw_reads', 'ip_filter', 'annot_filter', 'atlas_snap', 'matrixfilter', 'clustering', 'switch_diff']

function StageStepper({ lastStage, droppedAt, dropReason }: { lastStage: string; droppedAt: string; dropReason: string | null }) {
  const lastIndex = STAGE_ORDER.indexOf(lastStage)
  const droppedIndex = droppedAt ? STAGE_ORDER.indexOf(droppedAt) : -1

  return (
    <ol className="audit-view__stepper">
      {STAGE_ORDER.map((stage, i) => {
        let status: 'survived' | 'dropped' | 'pending' = 'pending'
        if (droppedIndex >= 0 && i === droppedIndex) status = 'dropped'
        else if (i <= lastIndex) status = 'survived'
        return (
          <li key={stage} className={`audit-view__step audit-view__step--${status}`}>
            <span className="audit-view__step-dot" />
            <span className="audit-view__step-label">{stage}</span>
            {status === 'dropped' && <span className="badge badge--danger">dropped: {dropReason ?? 'unknown reason'}</span>}
          </li>
        )
      })}
    </ol>
  )
}

function PasTrail({ pas }: { pas: PasDetail }) {
  return (
    <div className="panel audit-view__trail">
      <h4>PAS {pas.pas_uid}</h4>
      <dl className="audit-view__fields">
        <dt>orig_pas_key</dt>
        <dd className="mono">{pas.orig_pas_key}</dd>
        <dt>unified_pas_id</dt>
        <dd className="mono">{pas.unified_pas_id}</dd>
        <dt>gene</dt>
        <dd>
          {pas.gene_name ?? '—'} ({pas.gene_id ?? '—'})
        </dd>
        <dt>tier</dt>
        <dd>{pas.tier ?? '—'}</dd>
        <dt>snap_distance_bp</dt>
        <dd>{pas.snap_distance_bp ?? '—'}</dd>
        <dt>gene_distance_bp</dt>
        <dd>{pas.gene_distance_bp ?? '—'}</dd>
      </dl>
      <StageStepper lastStage={pas.last_stage} droppedAt={pas.dropped_at} dropReason={pas.drop_reason} />
    </div>
  )
}

function CellTrail({ cell }: { cell: CellDetail }) {
  return (
    <div className="panel audit-view__trail">
      <h4>Cell {cell.barcode}</h4>
      <dl className="audit-view__fields">
        <dt>cell_uid</dt>
        <dd className="mono">{cell.cell_uid}</dd>
        <dt>dataset_id</dt>
        <dd>{cell.dataset_id}</dd>
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
      </dl>
      <StageStepper lastStage={cell.dropped_at ? cell.dropped_at : 'switch_diff'} droppedAt={cell.dropped_at} dropReason={cell.drop_reason} />
    </div>
  )
}

export function AuditView() {
  const selected = useSelectionStore((s) => s.selected)
  const [pasId, setPasId] = useState('')
  const [cellId, setCellId] = useState('')
  const [activePas, setActivePas] = useState<string | null>(selected?.kind === 'pas' ? selected.data.pas_uid : null)
  const [activeCell, setActiveCell] = useState<string | null>(selected?.kind === 'cell' ? selected.data.cell_uid : null)

  const pasQuery = usePasProvenance(activePas)
  const cellQuery = useCellProvenance(activeCell)

  return (
    <div className="audit-view">
      <PageHeader
        title="Audit"
        description="Trace a single PAS or cell through the pipeline ledger: which stage it entered at, which filter it survived at each step, and -- if it didn't make it to switch_diff -- exactly where and why it was dropped. Use this to sanity-check a suspicious Findings row or a missing gene/cell against the raw provenance record."
      />
      <div className="audit-view__search panel">
        <div className="audit-view__search-row">
          <label>
            PAS UID
            <input value={pasId} onChange={(e) => setPasId(e.target.value)} placeholder="chr17:7661779:-" />
          </label>
          <button type="button" onClick={() => setActivePas(pasId || null)}>
            Trace PAS
          </button>
        </div>
        <div className="audit-view__search-row">
          <label>
            Cell UID
            <input value={cellId} onChange={(e) => setCellId(e.target.value)} placeholder="cell-0001" />
          </label>
          <button type="button" onClick={() => setActiveCell(cellId || null)}>
            Trace cell
          </button>
        </div>
      </div>


      <div className="audit-view__results">
        {activePas && pasQuery.isLoading && <LoadingState label="Loading PAS ledger…" />}
        {activePas && !pasQuery.isLoading && !pasQuery.data && <MissingArtifactNotice what="PAS ledger" />}
        {pasQuery.data && <PasTrail pas={pasQuery.data} />}

        {activeCell && cellQuery.isLoading && <LoadingState label="Loading cell ledger…" />}
        {activeCell && !cellQuery.isLoading && !cellQuery.data && <MissingArtifactNotice what="Cell ledger" />}
        {cellQuery.data && <CellTrail cell={cellQuery.data} />}

        {!activePas && !activeCell && <EmptyState reason="no-match" detail="Enter a PAS UID or cell UID above, or select one elsewhere in the app." />}
      </div>
    </div>
  )
}
