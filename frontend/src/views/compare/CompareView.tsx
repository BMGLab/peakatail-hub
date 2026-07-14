import { usePinStore } from '@state/usePinStore'
import { useGene } from '@lib/api/hooks'
import { EmptyState, LoadingState } from '@views/shared/ViewStates'
import type { PinnedEntity } from '@lib/contract/types'
import './CompareView.css'

function ComparePanel({ entity }: { entity: PinnedEntity }) {
  const geneQuery = useGene(entity.kind === 'gene' ? entity.id : null)

  return (
    <div className="panel compare-view__panel">
      <header className="compare-view__panel-header">
        <span className="badge badge--neutral">{entity.kind}</span>
        <h4>{entity.label}</h4>
      </header>
      {entity.kind === 'gene' ? (
        geneQuery.isLoading ? (
          <LoadingState label="Loading gene…" />
        ) : geneQuery.data ? (
          <dl className="compare-view__fields">
            <dt>locus</dt>
            {/* span is null when the gene has zero surviving PAS -- same
                nullable-coordinates rule as GeneView/DetailPanel (spec §5). */}
            <dd>
              {geneQuery.data.chrom !== null && geneQuery.data.start !== null && geneQuery.data.end !== null
                ? `${geneQuery.data.chrom}:${geneQuery.data.start}-${geneQuery.data.end}`
                : 'coordinates unavailable'}
            </dd>
            <dt>n_pas</dt>
            <dd>{geneQuery.data.n_pas}</dd>
          </dl>
        ) : (
          <p className="state-message">Gene not found.</p>
        )
      ) : (
        <p className="state-message">
          Stub -- {entity.kind} comparison panels (geneview/funnel side-by-side, "findings in X not Y") land once cross-sample
          canonical_cluster join (B6) is available, per docs §7c.
        </p>
      )}
    </div>
  )
}

export function CompareView() {
  const pinned = usePinStore((s) => s.pinned)

  if (pinned.length === 0) {
    return <EmptyState reason="no-match" detail="Pin genes/PAS/cells from the detail panel to compare them here." />
  }

  return (
    <div className="compare-view">
      <div className="compare-view__grid">
        {pinned.map((entity) => (
          <ComparePanel key={`${entity.kind}-${entity.id}`} entity={entity} />
        ))}
      </div>
    </div>
  )
}
