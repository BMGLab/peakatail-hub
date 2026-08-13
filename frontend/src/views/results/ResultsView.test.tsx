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

  it('lists the run\'s cell types with their 3\'UTR trend and drills into one', async () => {
    useScopeStore.setState({ runId: 'fixture-run-0001', datasetId: 'ds1' })
    renderResults()

    await waitFor(() => expect(screen.getByText('Tumor epithelial')).toBeInTheDocument())
    expect(screen.getByText('T cell')).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByText('Tumor epithelial'))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Tumor epithelial' })).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: /3'UTR length trend across stages/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /switching genes/i })).toBeInTheDocument()
  })
})
