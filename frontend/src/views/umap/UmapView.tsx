import { useMemo, useState } from 'react'
import { useUmap } from '@lib/api/hooks'
import { useScopeStore } from '@state/useScopeStore'
import { PlotlyChart } from '@charts/PlotlyChart'
import { EmptyState, ErrorState, LoadingState } from '@views/shared/ViewStates'
import { PageHeader } from '@views/shared/PageHeader'
import type { UmapPoint } from '@lib/contract/types'
import './UmapView.css'

type ColorField = 'leiden' | 'celltype' | 'stage' | 'sample'

// design doc §7c: recolor by celltype/stage/sample is gated on engine changes
// (A1/A2/B2/B7) that haven't landed. Only `leiden` is "immediately real-run-
// capable" per §7c. Keep the other options visible but disabled + explained,
// rather than silently omitting them (fail loud, not blank).
const COLOR_OPTIONS: { value: ColorField; label: string; disabled: boolean; reason?: string }[] = [
  { value: 'leiden', label: 'leiden cluster', disabled: false },
  { value: 'celltype', label: 'celltype', disabled: true, reason: 'blocked on A1 + A2/B2 label resolution' },
  { value: 'stage', label: 'stage', disabled: true, reason: 'blocked on A1 + A2/B2 label resolution' },
  { value: 'sample', label: 'sample', disabled: true, reason: 'blocked on B7 var_names join fix' },
]

const PALETTE = ['#5b9dff', '#f0a63d', '#4cc38a', '#e5484d', '#c084fc', '#3dd6f0']

function colorMap(points: UmapPoint[], field: ColorField): Record<string, string> {
  const values = Array.from(new Set(points.map((p) => (p[field] ?? 'unknown') as string)))
  return Object.fromEntries(values.map((v, i) => [v, PALETTE[i % PALETTE.length]!]))
}

export function UmapView() {
  const { datasetId } = useScopeStore()
  const [colorField, setColorField] = useState<ColorField>('leiden')
  const umapQuery = useUmap(datasetId)

  const points = useMemo(() => umapQuery.data ?? [], [umapQuery.data])
  const colors = useMemo(() => colorMap(points, colorField), [points, colorField])

  const header = (
    <PageHeader
      title="UMAP"
      description="A 2D embedding of every cell in the selected run, one point per cell. Proximity approximates similarity in PAS-usage space -- clustered points were grouped together by the pipeline's clustering stage, not necessarily by gene expression. Recolor by cluster (celltype/stage/sample land once cross-run label resolution ships)."
    />
  )

  if (!datasetId) {
    return (
      <div className="umap-view">
        {header}
        <EmptyState reason="no-match" detail="Select a run/dataset scope from the top bar first." />
      </div>
    )
  }

  if (umapQuery.isLoading) {
    return (
      <div className="umap-view">
        {header}
        <LoadingState label="Loading UMAP…" />
      </div>
    )
  }
  if (umapQuery.isError) {
    return (
      <div className="umap-view">
        {header}
        <ErrorState error={umapQuery.error} onRetry={() => umapQuery.refetch()} />
      </div>
    )
  }
  if (points.length === 0) {
    return (
      <div className="umap-view">
        {header}
        <EmptyState reason="no-match" />
      </div>
    )
  }

  const groups = Array.from(new Set(points.map((p) => (p[colorField] ?? 'unknown') as string)))

  const traces = groups.map((g) => {
    const groupPoints = points.filter((p) => (p[colorField] ?? 'unknown') === g)
    return {
      x: groupPoints.map((p) => p.x),
      y: groupPoints.map((p) => p.y),
      text: groupPoints.map((p) => p.cell_uid),
      type: 'scattergl' as const,
      mode: 'markers' as const,
      name: g,
      marker: { size: 4, color: colors[g] },
    }
  })

  return (
    <div className="umap-view">
      {header}
      <div className="umap-view__toolbar">
        <label>
          Color by
          <select value={colorField} onChange={(e) => setColorField(e.target.value as ColorField)}>
            {COLOR_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value} disabled={opt.disabled} title={opt.reason}>
                {opt.label}
                {opt.disabled ? ' (locked)' : ''}
              </option>
            ))}
          </select>
        </label>
        {COLOR_OPTIONS.find((o) => o.value === colorField)?.disabled && (
          <span className="badge badge--warn">gated -- see §7c dependency table</span>
        )}
        <span className="umap-view__count">{points.length.toLocaleString()} cells (full set, no point-dropping per §7f)</span>
      </div>
      <div className="umap-view__plot panel">
        <PlotlyChart data={traces} layout={{ xaxis: { title: { text: 'UMAP1' } }, yaxis: { title: { text: 'UMAP2' } }, hovermode: 'closest' }} />
      </div>
    </div>
  )
}
