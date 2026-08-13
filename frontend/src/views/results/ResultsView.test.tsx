import { describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { renderWithProviders } from '../../test/testUtils'
import { ResultsView } from './ResultsView'
import { ResultsCelltypeView } from './ResultsCelltypeView'
import { useScopeStore } from '@state/useScopeStore'

function renderResults(initialEntry = '/results') {
  return renderWithProviders(
    <Routes>
      <Route path="/results" element={<ResultsView />} />
      <Route path="/results/:celltype" element={<ResultsCelltypeView />} />
    </Routes>,
    { initialEntries: [initialEntry] },
  )
}

describe('ResultsView (Cell Types)', () => {
  it('shows a scope-selection prompt when no run is picked yet', () => {
    useScopeStore.setState({ runId: null, datasetId: null })
    renderResults()
    expect(screen.getByText(/select a run from the top bar scope selector first/i)).toBeInTheDocument()
  })

  it('lists the run\'s cell types with a clean display label (celltypeLabel) and drills into one', async () => {
    useScopeStore.setState({ runId: 'fixture-run-0001', datasetId: 'ds1' })
    renderResults()

    // mock celltypes are already-clean strings ('Tumor epithelial', 'T cell', ...)
    // -- celltypeLabel title-cases them (no known raw-id prefix to strip),
    // so the DISPLAYED text is "Tumor Epithelial"/"T Cell" while the full
    // original string stays the card's title tooltip + the actual query key.
    await waitFor(() => expect(screen.getByText('Tumor Epithelial')).toBeInTheDocument())
    expect(screen.getByText('T Cell')).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByText('Tumor Epithelial'))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Tumor Epithelial' })).toBeInTheDocument())
    expect(screen.getByText('Tumor epithelial')).toBeInTheDocument() // full id kept, shown below the header
    expect(screen.getByRole('heading', { name: /3'UTR length trend across stages/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /switching genes/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /nb_multi omnibus hits/i })).toBeInTheDocument()
  })
})
