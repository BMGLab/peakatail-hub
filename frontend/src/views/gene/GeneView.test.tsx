import { describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { renderWithProviders } from '../../test/testUtils'
import { GeneView } from './GeneView'
import { useScopeStore } from '@state/useScopeStore'

// GeneView embeds the REAL ema geneview output (an <iframe>/<img> pointed at
// backend file-serving endpoints, see geneviewHtmlUrl/geneviewPngUrl in
// lib/api/client.ts) -- there is no client-side track rendering left to unit
// test (that's the whole point of the 2026-08-14 fix, replacing the old
// hand-rolled canvas). These tests cover what IS still real frontend logic:
// the gene header, the plotly/matplotlib toggle, the metadata + PAS-distance
// table (from mockGeneviewMeta), and the "no run selected" guard.

function renderGeneView(geneId: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/genes/:geneId" element={<GeneView />} />
    </Routes>,
    { initialEntries: [`/genes/${geneId}`] },
  )
}

describe('GeneView', () => {
  it('shows a scope-selection prompt when no run is picked yet', () => {
    useScopeStore.setState({ runId: null, datasetId: null })
    renderGeneView('ENSG00000141510')
    expect(screen.getByText(/select a run from the top bar scope selector first/i)).toBeInTheDocument()
  })

  it('renders the gene header, engine toggle, and PAS-distance table once a run is scoped', async () => {
    useScopeStore.setState({ runId: 'fixture-run-0001', datasetId: 'ds1' })
    renderGeneView('ENSG00000141510')

    await waitFor(() => expect(screen.getByRole('heading', { name: 'TP53' })).toBeInTheDocument())
    expect(screen.getByText('ENSG00000141510')).toBeInTheDocument()

    // Plotly is the default engine; the toggle offers both.
    expect(screen.getByRole('button', { name: /plotly \(interactive\)/i })).toHaveClass('gene-view__engine-btn--active')
    expect(screen.getByRole('button', { name: /matplotlib \(static\)/i })).not.toHaveClass('gene-view__engine-btn--active')

    await waitFor(() => expect(screen.getByTitle(/TP53 geneview \(plotly\)/i)).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: /PAS-distance table/i })).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /matplotlib \(static\)/i }))
    expect(screen.getByRole('button', { name: /matplotlib \(static\)/i })).toHaveClass('gene-view__engine-btn--active')
    expect(screen.getByAltText(/TP53 geneview \(matplotlib\)/i)).toBeInTheDocument()
  })

  it('shows a not-indexed empty state for an unknown gene', async () => {
    useScopeStore.setState({ runId: 'fixture-run-0001', datasetId: 'ds1' })
    renderGeneView('ENSG99999999999')
    await waitFor(() => expect(screen.getByText(/was not found in the index/i)).toBeInTheDocument())
  })
})
