import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { geneviewHtmlUrl, geneviewPngUrl } from '@lib/api/client'
import { useGene, useGeneviewMeta } from '@lib/api/hooks'
import { useScopeStore } from '@state/useScopeStore'
import { EmptyState, ErrorState, LoadingState } from '@views/shared/ViewStates'
import './GeneView.css'

type Engine = 'plotly' | 'matplotlib'

/**
 * GeneView -- the REAL `ema switch geneview` output (2026-08-14), replacing
 * the previous hand-rolled IGV-style track canvas entirely. No part of the
 * gene track/coverage/isoform rendering happens client-side anymore: this
 * component asks the backend for the figure (generated on demand by a
 * host-side worker if not already cached, see backend/src/peakatail_hub/
 * geneview/ + geneview-worker/), then embeds whichever engine the user
 * picked -- an <iframe> for the interactive plotly figure (full PAS + cell
 * metadata on hover, a switchable per-cluster metric, the PAS-distance-table
 * overlay -- all baked in by ema itself), or an <img> for the static
 * matplotlib figure.
 */
export function GeneView() {
  const { geneId } = useParams<{ geneId: string }>()
  // The backend 400s `/genes/{id}`/`/genes/{id}/geneview/*` once more than
  // one run is indexed unless `run_id` is passed -- thread the TopBar Scope
  // selector's run through rather than assume there's exactly one run.
  const runId = useScopeStore((s) => s.runId)
  const geneQuery = useGene(geneId ?? null, runId)
  const [engine, setEngine] = useState<Engine>('plotly')

  // Triggers on-demand generation (blocks up to ~25s server-side on a cold
  // cache; see useGeneviewMeta's doc comment) and gives us the metadata +
  // distance table alongside confirmation the figure is ready. The iframe/
  // img below are only rendered once this resolves, so they always hit an
  // already-warm cache instead of racing a cold render with a blank/broken
  // embed and no loading indicator.
  const metaQuery = useGeneviewMeta(geneId ?? null, runId)

  if (!geneId) {
    return <EmptyState reason="no-match" detail="No gene selected." />
  }

  // Mirrors QcView's own guard: the backend refuses to guess `run_id` once
  // more than one run is indexed, so a gene reached before any Scope is
  // picked would otherwise surface as a raw "run_id query param is
  // required" 400 rather than a normal empty state.
  if (!runId) {
    return <EmptyState reason="no-match" detail="Select a run from the top bar scope selector first." />
  }

  if (geneQuery.isLoading) {
    return <LoadingState label={`Loading ${geneId}…`} />
  }
  if (geneQuery.isError) {
    return <ErrorState error={geneQuery.error} onRetry={() => geneQuery.refetch()} />
  }
  if (!geneQuery.data) {
    return <EmptyState reason="not-indexed" detail={`Gene ${geneId} was not found in the index.`} />
  }

  const gene = geneQuery.data
  const meta = metaQuery.data

  return (
    <div className="gene-view">
      <header className="gene-view__header">
        <h2>{gene.gene_name}</h2>
        <span className="mono">{gene.gene_id}</span>
        {meta ? (
          <>
            <span className="badge badge--neutral">
              {meta.chrom ? `${meta.chrom}:${meta.start}-${meta.end} (${meta.strand})` : 'coordinates unavailable'}
            </span>
            <span className="badge badge--neutral">dataset: {meta.dataset_id}</span>
            <span className="badge badge--neutral">{meta.n_pas ?? 0} PAS</span>
            <span className="badge badge--neutral">{meta.n_isoforms ?? 0} isoforms</span>
          </>
        ) : null}

        <div className="gene-view__engine-toggle" role="group" aria-label="Figure engine">
          <button
            type="button"
            className={engine === 'plotly' ? 'gene-view__engine-btn gene-view__engine-btn--active' : 'gene-view__engine-btn'}
            onClick={() => setEngine('plotly')}
          >
            Plotly (interactive)
          </button>
          <button
            type="button"
            className={engine === 'matplotlib' ? 'gene-view__engine-btn gene-view__engine-btn--active' : 'gene-view__engine-btn'}
            onClick={() => setEngine('matplotlib')}
          >
            Matplotlib (static)
          </button>
        </div>
      </header>

      <p className="gene-view__description">
        The gene track ema produces from this run's real data: per-cluster PAS coverage and within-gene usage
        proportions, gene isoform structure, and a PAS-distance table (rank, coordinates, gap to the next PAS).
        Plotly adds full PAS + cell metadata on hover and a switchable metric; matplotlib is the static equivalent.
        Generated on demand and cached — the first open for a gene can take up to ~25s, repeat opens are instant.
      </p>

      <div className="gene-view__body">
        {metaQuery.isLoading ? (
          <LoadingState label={`Generating geneview for ${gene.gene_name} — first open can take up to ~25s…`} />
        ) : metaQuery.isError ? (
          <ErrorState error={metaQuery.error} onRetry={() => metaQuery.refetch()} />
        ) : meta ? (
          <>
            <div className="gene-view__figure">
              {engine === 'plotly' ? (
                <iframe
                  key={`plotly-${gene.gene_id}-${meta.dataset_id}`}
                  title={`${gene.gene_name} geneview (plotly)`}
                  className="gene-view__iframe"
                  src={geneviewHtmlUrl(gene.gene_id, runId, meta.dataset_id)}
                />
              ) : (
                <img
                  key={`matplotlib-${gene.gene_id}-${meta.dataset_id}`}
                  alt={`${gene.gene_name} geneview (matplotlib)`}
                  className="gene-view__img"
                  src={geneviewPngUrl(gene.gene_id, runId, meta.dataset_id)}
                />
              )}
            </div>

            <div className="panel gene-view__distances">
              <h4>PAS-distance table ({meta.pas_distances.length} PAS, dataset {meta.dataset_id}, cluster_key {meta.cluster_key})</h4>
              {meta.pas_distances.length === 0 ? (
                <p className="state-message">No surviving PAS for this gene in this dataset.</p>
              ) : (
                <table className="gene-view__table">
                  <thead>
                    <tr>
                      <th>rank</th>
                      <th>pas_id</th>
                      <th>coords</th>
                      <th>width_bp</th>
                      <th>summit_pos</th>
                      <th>gap_to_next_bp</th>
                      <th>summit_dist_to_next_bp</th>
                    </tr>
                  </thead>
                  <tbody>
                    {meta.pas_distances.map((row) => (
                      <tr key={row.pas_id}>
                        <td>{row.rank}</td>
                        <td className="mono">{row.pas_id}</td>
                        <td className="mono">
                          {row.chrom}:{row.start}-{row.end} ({row.strand})
                        </td>
                        <td>{row.width_bp}</td>
                        <td>{row.summit_pos}</td>
                        <td>{row.gap_to_next_bp ?? '—'}</td>
                        <td>{row.summit_dist_to_next_bp ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        ) : null}
      </div>
    </div>
  )
}
