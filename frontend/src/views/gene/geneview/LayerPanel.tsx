import type { FindingRow, LengthRow } from '@lib/contract/types'
import './LayerPanel.css'

export interface GeneviewLayerState {
  pasStems: boolean
  diffStrategies: Set<FindingRow['strategy']>
  lengthStrategies: Set<LengthRow['strategy']>
  coverage: boolean
  significantOnly: boolean
  qMax: number
}

// The base view is the per-cluster proportion tracks (always rendered,
// matching PeakATail's own gene-track figure) -- every overlay below is
// opt-in, so a freshly-opened geneview reads exactly like the reference
// figure rather than being cluttered with every strategy at once.
export const DEFAULT_LAYER_STATE: GeneviewLayerState = {
  pasStems: false,
  diffStrategies: new Set(),
  lengthStrategies: new Set(),
  coverage: false,
  significantOnly: false,
  qMax: 1,
}

interface LayerPanelProps {
  state: GeneviewLayerState
  onChange: (next: GeneviewLayerState) => void
}

const ALL_DIFF_STRATEGIES: FindingRow['strategy'][] = ['fisher', 'nb_pairwise', 'nb_multi']
const ALL_LENGTH_STRATEGIES: LengthRow['strategy'][] = ['classic', 'proportion', 'shannon']

/** Toggle checkboxes for each geneview layer (design §1 layer list). */
export function LayerPanel({ state, onChange }: LayerPanelProps) {
  function toggleDiff(strategy: FindingRow['strategy']) {
    const next = new Set(state.diffStrategies)
    if (next.has(strategy)) next.delete(strategy)
    else next.add(strategy)
    onChange({ ...state, diffStrategies: next })
  }

  function toggleLength(strategy: LengthRow['strategy']) {
    const next = new Set(state.lengthStrategies)
    if (next.has(strategy)) next.delete(strategy)
    else next.add(strategy)
    onChange({ ...state, lengthStrategies: next })
  }

  return (
    <div className="layer-panel panel">
      <h4>Layers</h4>
      <label className="layer-panel__row">
        <input type="checkbox" checked disabled />
        Isoforms + per-cluster proportions (always on)
      </label>
      <label className="layer-panel__row" title="Raw per-PAS read stems (legacy view) -- not UMI-deduplicated">
        <input type="checkbox" checked={state.pasStems} onChange={(e) => onChange({ ...state, pasStems: e.target.checked })} />
        PAS read stems (raw)
      </label>

      <fieldset className="layer-panel__group">
        <legend>Diff overlays</legend>
        {ALL_DIFF_STRATEGIES.map((s) => (
          <label key={s} className="layer-panel__row">
            <input type="checkbox" checked={state.diffStrategies.has(s)} onChange={() => toggleDiff(s)} />
            {s}
          </label>
        ))}
        <label className="layer-panel__row">
          <input
            type="checkbox"
            checked={state.significantOnly}
            onChange={(e) => onChange({ ...state, significantOnly: e.target.checked })}
          />
          significant only (q ≤ 0.05)
        </label>
        <label className="layer-panel__row">
          q ≤ {state.qMax.toFixed(2)}
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={state.qMax}
            onChange={(e) => onChange({ ...state, qMax: Number(e.target.value) })}
          />
        </label>
      </fieldset>

      <fieldset className="layer-panel__group">
        <legend>Length overlays</legend>
        {ALL_LENGTH_STRATEGIES.map((s) => (
          <label key={s} className="layer-panel__row">
            <input type="checkbox" checked={state.lengthStrategies.has(s)} onChange={() => toggleLength(s)} />
            {s}
          </label>
        ))}
      </fieldset>

      <label className="layer-panel__row" title="Coverage lane is roadmap B (true bigWig coverage); hidden by default in v1">
        <input type="checkbox" checked={state.coverage} onChange={(e) => onChange({ ...state, coverage: e.target.checked })} />
        Coverage (roadmap B)
      </label>
    </div>
  )
}
