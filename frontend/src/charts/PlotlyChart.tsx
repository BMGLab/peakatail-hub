// react-plotly.js's default export hardcodes a dependency on the full
// `plotly.js` package (`plotly.js/dist/plotly`). To keep the bundle lean we
// use its `factory` entry point bound to `plotly.js-dist-min` instead (same
// public API, no geo/mapbox trace types) -- this is the "or plotly.js-dist-min"
// option from the design spec §0.
import createPlotlyComponent from 'react-plotly.js/factory'
import Plotly from 'plotly.js-dist-min'
import type { Data, Layout, Config, PlotMouseEvent } from 'plotly.js'

const Plot = createPlotlyComponent(Plotly)

interface PlotlyChartProps {
  data: Data[]
  layout?: Partial<Layout>
  config?: Partial<Config>
  style?: React.CSSProperties
  className?: string
  onClick?: (event: Readonly<PlotMouseEvent>) => void
}

/**
 * Shared Plotly wrapper with consistent dark theming for all charts
 * surrounding the custom geneview renderer (PDUI-by-stage line, UMAP,
 * QC funnel, etc). Keep per-view Plotly config additions minimal; put
 * shared defaults here so all charts look/behave consistently.
 */
export function PlotlyChart({ data, layout, config, style, className, onClick = () => {} }: PlotlyChartProps) {
  return (
    <Plot
      data={data}
      onClick={onClick}
      layout={{
        autosize: true,
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        font: { color: '#d7dae0', size: 11 },
        margin: { l: 48, r: 16, t: 24, b: 36 },
        legend: { orientation: 'h', y: -0.2 },
        ...layout,
      }}
      config={{
        displaylogo: false,
        responsive: true,
        toImageButtonOptions: { format: 'png', scale: 3 },
        ...config,
      }}
      style={{ width: '100%', height: '100%', ...style }}
      {...(className !== undefined ? { className } : {})}
      useResizeHandler
    />
  )
}
