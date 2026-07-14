import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useGene, useGeneviewData } from '@lib/api/hooks'
import { useSelectionStore } from '@state/useSelectionStore'
import { useGeneviewWindow } from './geneview/useGeneviewWindow'
import { GeneviewCanvas } from './geneview/GeneviewCanvas'
import { LayerPanel, DEFAULT_LAYER_STATE, type GeneviewLayerState } from './geneview/LayerPanel'
import { PlotlyChart } from '@charts/PlotlyChart'
import { EmptyState, ErrorState, LoadingState, MissingArtifactNotice } from '@views/shared/ViewStates'
import './GeneView.css'

export function GeneView() {
  const { geneId } = useParams<{ geneId: string }>()
  const geneQuery = useGene(geneId ?? null)
  const dataQuery = useGeneviewData(geneId ?? null)
  const [layers, setLayers] = useState<GeneviewLayerState>(DEFAULT_LAYER_STATE)
  const select = useSelectionStore((s) => s.select)

  const geneviewWindow = useGeneviewWindow(geneQuery.data)

  if (!geneId) {
    return <EmptyState reason="no-match" detail="No gene selected." />
  }

  if (geneQuery.isLoading || dataQuery.isLoading) {
    return <LoadingState label={`Loading ${geneId}…`} />
  }

  if (geneQuery.isError) {
    return <ErrorState error={geneQuery.error} onRetry={() => geneQuery.refetch()} />
  }

  if (dataQuery.isError) {
    return <ErrorState error={dataQuery.error} onRetry={() => dataQuery.refetch()} />
  }

  if (!geneQuery.data) {
    return <EmptyState reason="not-indexed" detail={`Gene ${geneId} was not found in the index.`} />
  }

  const gene = geneQuery.data
  const geneviewData = dataQuery.data
  const hasSpan = gene.chrom !== null && gene.start !== null && gene.end !== null && gene.strand !== null

  const pduiTrace = {
    x: geneviewData?.length.map((l) => l.canonical_cluster) ?? [],
    y: geneviewData?.length.map((l) => l.value) ?? [],
    type: 'scatter' as const,
    mode: 'markers' as const,
    name: 'PDUI by stage',
  }

  return (
    <div className="gene-view">
      <header className="gene-view__header">
        <h2>{gene.gene_name}</h2>
        <span className="mono">{gene.gene_id}</span>
        <span className="badge badge--neutral">
          {hasSpan ? `${gene.chrom}:${gene.start}-${gene.end} (${gene.strand})` : 'coordinates unavailable'}
        </span>
      </header>

      <div className="gene-view__body">
        <LayerPanel state={layers} onChange={setLayers} />

        <div className="gene-view__main">
          {/* span is null when the gene has zero surviving PAS -- the
              canvas needs real start/end/strand to lay out its coordinate
              scale, so fail loud (spec §5) rather than feed it nulls. */}
          {geneviewData && hasSpan ? (
            <GeneviewCanvas
              data={geneviewData}
              window={geneviewWindow.window}
              layers={layers}
              onZoomIn={geneviewWindow.zoomIn}
              onZoomOut={geneviewWindow.zoomOut}
              onPan={geneviewWindow.pan}
              onResetToGeneSpan={geneviewWindow.resetToGeneSpan}
              onSelectPas={(pas) => select({ kind: 'pas', data: pas })}
            />
          ) : (
            <MissingArtifactNotice what="Geneview" />
          )}

          <div className="gene-view__companions">
            <div className="panel gene-view__companion">
              <h4>PDUI by stage</h4>
              <div className="gene-view__chart">
                <PlotlyChart data={[pduiTrace]} layout={{ xaxis: { title: { text: 'cluster' } }, yaxis: { title: { text: 'value' } } }} />
              </div>
            </div>

            <div className="panel gene-view__companion">
              <h4>PAS list (with provenance)</h4>
              <table className="gene-view__table">
                <thead>
                  <tr>
                    <th>pas_uid</th>
                    <th>tier</th>
                    <th>snap_distance_bp</th>
                    <th>gene_distance_bp</th>
                  </tr>
                </thead>
                <tbody>
                  {(geneviewData?.pas ?? []).map((p) => (
                    <tr
                      key={p.pas_uid}
                      onClick={() => select({ kind: 'pas', data: p })}
                      style={{ cursor: 'pointer' }}
                    >
                      <td className="mono">{p.pas_uid}</td>
                      <td>{p.tier ?? '—'}</td>
                      <td>{p.snap_distance_bp ?? '—'}</td>
                      <td>{p.gene_distance_bp ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="panel gene-view__companion">
              <h4>Isoform table (cross-arm aggregate)</h4>
              <p className="state-message">Stub -- isoform-level aggregation is not yet exposed by the contract package.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
