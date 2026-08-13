import { describe, expect, it } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
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

  // 2026-08-14: makes the length results BROWSABLE -- LengthTrendTable
  // fetches the celltype's whole trend-gene set (mockSwitchTrendGenes: 4
  // real fixture genes + 120 synthetic rows = 124) in one call and does
  // search/sort/pagination client-side. Covers the "Length-result
  // availability (not browsable...)" panel it replaced.
  it('shows a browsable, searchable, paginated per-gene length table (LengthTrendTable)', async () => {
    useScopeStore.setState({ runId: 'fixture-run-0001', datasetId: 'ds1' })
    renderResults('/results/Tumor%20epithelial')

    const heading = await screen.findByRole('heading', { name: /length results by gene/i })
    // Scoped to this panel -- "TP53"/its gene_id also appear in the fisher
    // findings table below, which would otherwise make queries ambiguous.
    const panel = within(heading.closest('.panel') as HTMLElement)

    // All 124 mock rows load and paginate 50/page.
    await waitFor(() => expect(panel.getByText(/124 of 124 genes/i)).toBeInTheDocument())
    expect(panel.getByText(/page 1 \/ 3/i)).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(panel.getByText(/next/i))
    await waitFor(() => expect(panel.getByText(/page 2 \/ 3/i)).toBeInTheDocument())

    // Search narrows the set and resets back to page 1 (even from page 2).
    const search = panel.getByRole('searchbox', { name: /search length results/i })
    await user.type(search, 'TP53')
    await waitFor(() => expect(panel.getByText(/1 of 124 genes matching "TP53"/i)).toBeInTheDocument())
    expect(panel.getByText('TP53')).toBeInTheDocument()
    expect(panel.getByText(/page 1 \/ 1/i)).toBeInTheDocument()

    // The 100GB-per-run raw-file note survives, now demoted to a small secondary line.
    expect(screen.getByText(/not loaded into the hub -- up to 100gb\+\/run/i)).toBeInTheDocument()
  })
})
