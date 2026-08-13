import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { geneviewRenderUrl } from '@lib/api/client'
import { useGene, useGeneviewCheck, useRunSwitch, useRunSwitchTrendGenes } from '@lib/api/hooks'
import { useScopeStore } from '@state/useScopeStore'
import { celltypeLabel } from '@lib/celltypeLabel'
import { trendDirectionLabel } from '@lib/trendDirectionLabel'
import { EmptyState, ErrorState, LoadingState } from '@views/shared/ViewStates'
import './GeneView.css'

// Every gene this run's switch analysis has a length-trend row for, per
// celltype (a few thousand -- see length_trend_by_gene.tsv), not just the
// "top N by |slope|" ResultsCelltypeView shows -- the backend endpoint caps
// at 500 (api/runs.py Query(..., le=500)), the max this headline can ask
// for. A gene outside that cap simply has no headline shown (team-lead's
// own call: "if the gene isn't in the trend list, just omit it").
const TREND_LOOKUP_LIMIT = 500

type Engine = 'plotly' | 'matplotlib'
type ClusterKey = 'stage' | 'leiden'

/**
 * GeneView -- a generator panel for the REAL `ema switch geneview` output
 * (2026-08-14), replacing the previous hand-rolled IGV-style track canvas
 * entirely. No gene track/coverage/isoform rendering happens client-side:
 * every control here (engine, cluster_key, color_key, distance-table
 * on/off) is forwarded as a query param to a separate host-side geneview
 * microservice (geneview_svc.py, reached via a same-origin `/geneview/*`
 * proxy -- see lib/api/client.ts's `geneviewRenderUrl` doc comment), which
 * renders per (run, celltype, gene) on demand and caches. Plotly renders as
 * a full interactive HTML document (all PAS + cell metadata on hover, a
 * switchable per-cluster metric, the PAS-distance-table overlay baked in by
 * ema itself) embedded via <iframe>; matplotlib is the static PNG
 * equivalent via <img>.
 *
 * Cell type is now a REQUIRED part of the geneview's identity (PAS calling
 * and the switch analysis are both per-celltype) -- reached via
 * `?celltype=` (set when arriving from ResultsCelltypeView's gene tables)
 * or picked from this panel's own dropdown, sourced from the run's real
 * `GET /runs/{id}/switch` celltypes.
 */
export function GeneView() {
  const { geneId } = useParams<{ geneId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  // The backend 400s `/genes/{id}` once more than one run is indexed unless
  // `run_id` is passed -- thread the TopBar Scope selector's run through.
  const runId = useScopeStore((s) => s.runId)
  const geneQuery = useGene(geneId ?? null, runId)
  const switchQuery = useRunSwitch(runId)
  const trendGenesQuery = useRunSwitchTrendGenes(runId, searchParams.get('celltype'), TREND_LOOKUP_LIMIT)

  const [engine, setEngine] = useState<Engine>('plotly')
  const [clusterKey, setClusterKey] = useState<ClusterKey>('stage')
  const [colorKey, setColorKey] = useState('')
  const [pasDistanceTable, setPasDistanceTable] = useState(true)
  const [figureLoading, setFigureLoading] = useState(true)

  const celltypes = (switchQuery.data?.celltypes ?? []).map((c) => c.celltype)
  const celltype = searchParams.get('celltype') ?? celltypes[0] ?? null

  // Built from raw hook state (available before geneQuery resolves), not
  // the JSX's own `renderUrl` const below -- same shape, computed once here
  // so the pre-flight check hook (unconditional, called before any early
  // return) and the figure src stay in lockstep.
  const renderUrl =
    runId && celltype && geneId
      ? geneviewRenderUrl({ run: runId, celltype, gene: geneId, engine, cluster_key: clusterKey, color_key: colorKey || undefined, pas_distance_table: pasDistanceTable })
      : null

  // Pre-flight check (2026-08-14): asks the geneview microservice whether
  // this (gene, celltype, ...) combination has anything to render BEFORE
  // pointing the <iframe>/<img> at it -- lets GeneView show a friendly "no
  // PAS expressed here" empty state instead of a broken embed when the
  // renderer's own clean 404 fires (a common, legitimate case: the gene
  // just isn't expressed with APA in this cell type). Also what actually
  // triggers on-demand generation -- the src that follows on success always
  // hits an already-warm cache. See client.ts::checkGeneviewRender.
  const checkQuery = useGeneviewCheck(renderUrl)

  // Default the URL's `celltype` to the run's first available one once the
  // switch results load, if the panel was reached with none set (e.g.
  // directly via search/locus jump rather than from ResultsCelltypeView).
  useEffect(() => {
    if (!searchParams.get('celltype') && celltypes[0]) {
      const next = new URLSearchParams(searchParams)
      next.set('celltype', celltypes[0])
      setSearchParams(next, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [celltypes.join('|')])

  // A new figure request (any control change, or navigating to a different
  // gene) means the <iframe>/<img> below remounts (`key={renderUrl}`) and
  // starts a fresh load -- reset the loading flag so the "generating..."
  // message reappears instead of staying stuck on whatever the PREVIOUS
  // figure's onLoad last set it to.
  useEffect(() => {
    setFigureLoading(true)
  }, [geneId, celltype, engine, clusterKey, colorKey, pasDistanceTable])

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
  const hasSpan = gene.chrom !== null && gene.start !== null && gene.end !== null && gene.strand !== null

  // This gene's own row in the celltype's length-trend-across-stages table
  // (2026-08-14) -- the shorten/lengthen headline shown right where the
  // user is looking at the gene, not only back in the cell-type summary.
  // Omitted entirely (not an error/empty state) when the gene isn't in the
  // trend list -- see TREND_LOOKUP_LIMIT's doc comment.
  const geneTrend = (trendGenesQuery.data ?? []).find((g) => g.gene_id === gene.gene_id) ?? null

  return (
    <div className="gene-view">
      <header className="gene-view__header">
        <h2>{gene.gene_name}</h2>
        <span className="mono">{gene.gene_id}</span>
        <span className="badge badge--neutral">
          {hasSpan ? `${gene.chrom}:${gene.start}-${gene.end} (${gene.strand})` : 'coordinates unavailable'}
        </span>
        {geneTrend && celltype && (
          <span className="badge badge--accent" title={`n_stages=${geneTrend.n_stages ?? '—'}`}>
            {trendDirectionLabel(geneTrend.direction)} in {celltypeLabel(celltype)} (slope {geneTrend.slope?.toFixed(4) ?? '—'}, Spearman{' '}
            {geneTrend.spearman?.toFixed(2) ?? '—'})
          </span>
        )}
      </header>

      <p className="gene-view__description">
        The gene track ema produces from this run's real data: per-cluster PAS coverage and within-gene usage
        proportions, gene isoform structure, and (when enabled) a PAS-distance table. Plotly adds full PAS + cell
        metadata on hover and a switchable metric; matplotlib is the static equivalent. Generated on demand and
        cached per (run, cell type, gene, engine, cluster/color key) — the first open can take up to ~15s, repeat
        opens with the same options are instant.
      </p>

      <div className="panel gene-view__controls">
        <label className="gene-view__control">
          Cell type
          <select value={celltype ?? ''} onChange={(e) => setSearchParams({ celltype: e.target.value })}>
            {celltypes.length === 0 && <option value="">No cell types for this run</option>}
            {celltypes.map((c) => (
              <option key={c} value={c} title={c}>
                {celltypeLabel(c)}
              </option>
            ))}
          </select>
        </label>

        <label className="gene-view__control">
          Cluster key
          <select value={clusterKey} onChange={(e) => setClusterKey(e.target.value as ClusterKey)}>
            <option value="stage">stage (disease stage)</option>
            <option value="leiden">leiden (raw per-dataset cluster)</option>
          </select>
        </label>

        <label className="gene-view__control">
          Color key (optional)
          <input
            type="text"
            placeholder="e.g. sample"
            value={colorKey}
            onChange={(e) => setColorKey(e.target.value)}
          />
        </label>

        <label className="gene-view__control gene-view__control--checkbox">
          <input type="checkbox" checked={pasDistanceTable} onChange={(e) => setPasDistanceTable(e.target.checked)} />
          PAS-distance table overlay
        </label>

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
      </div>

      <div className="gene-view__body">
        {!celltype ? (
          <EmptyState
            reason="no-match"
            detail="This run has no B3_switch cell types to render a geneview for -- pick a gene from a Cell Types > switching-genes table, or select a cell type above once this run has switch results."
          />
        ) : checkQuery.isLoading ? (
          <div className="gene-view__figure">
            <div className="gene-view__figure-loading">Generating geneview — first open can take up to ~15s…</div>
          </div>
        ) : checkQuery.isError ? (
          <ErrorState error={checkQuery.error} onRetry={() => checkQuery.refetch()} />
        ) : checkQuery.data && !checkQuery.data.ok ? (
          // The renderer's own clean 404 ("gene <id> has no PAS expressed in
          // cell type <ct>") -- a common, legitimate case, not a crash/error.
          <EmptyState reason="no-match" detail={checkQuery.data.message} />
        ) : (
          <div className="gene-view__figure">
            {figureLoading && <div className="gene-view__figure-loading">Loading rendered geneview…</div>}
            {engine === 'plotly' ? (
              <iframe
                key={renderUrl}
                title={`${gene.gene_name} geneview (plotly, ${celltypeLabel(celltype)})`}
                className="gene-view__iframe"
                src={renderUrl ?? undefined}
                onLoad={() => setFigureLoading(false)}
              />
            ) : (
              <img
                key={renderUrl}
                alt={`${gene.gene_name} geneview (matplotlib, ${celltypeLabel(celltype)})`}
                className="gene-view__img"
                src={renderUrl ?? undefined}
                onLoad={() => setFigureLoading(false)}
                onError={() => setFigureLoading(false)}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
