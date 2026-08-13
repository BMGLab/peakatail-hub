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
    // 2026-08-14: differential test defaults to fisher (its own strategy
    // selector, tested separately below) -- nb_multi's table only mounts
    // once that tab is picked.
    expect(screen.getByRole('heading', { name: /switching genes -- differential test/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /fisher \(pairwise\)/i })).toHaveAttribute('aria-selected', 'true')
  })

  // 2026-08-14: "surface all strategies, let the user select" -- both diff
  // [fisher|nb_multi|nb_pairwise] and length [classic|proportion|shannon]
  // are now explicit tabs on the cell-type view instead of always showing
  // (diff) or only ever showing classic (length).
  it('diff strategy selector toggles between fisher and nb_multi, and greys out nb_pairwise as not run', async () => {
    useScopeStore.setState({ runId: 'fixture-run-0001', datasetId: 'ds1' })
    renderResults('/results/Tumor%20epithelial')

    const heading = await screen.findByRole('heading', { name: /switching genes -- differential test/i })
    const panel = within(heading.closest('.panel') as HTMLElement)

    // fisher selected by default -- its pairwise-contrast table shows.
    await waitFor(() => expect(panel.getByText(/exhaustive within-gene pairwise contrasts/i)).toBeInTheDocument())
    expect(panel.queryByText(/omnibus likelihood-ratio test/i)).not.toBeInTheDocument()

    // nb_pairwise was never run in this sweep -- shown, but disabled/"not run", not omitted or faked.
    const nbPairwiseTab = panel.getByRole('tab', { name: /nb_pairwise/i })
    expect(nbPairwiseTab).toBeDisabled()
    expect(panel.getByText(/not run/i)).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(panel.getByRole('tab', { name: /nb_multi \(omnibus\)/i }))

    // Switching to nb_multi swaps the table entirely -- fisher's is gone.
    await waitFor(() => expect(panel.getByText(/omnibus likelihood-ratio test/i)).toBeInTheDocument())
    expect(panel.queryByText(/exhaustive within-gene pairwise contrasts/i)).not.toBeInTheDocument()
  })

  it('length strategy selector switches the trend headline + browsable table between classic and shannon', async () => {
    useScopeStore.setState({ runId: 'fixture-run-0001', datasetId: 'ds1' })
    renderResults('/results/Tumor%20epithelial')

    const trendHeading = await screen.findByRole('heading', { name: /3'UTR length trend across stages/i })
    const trendPanel = within(trendHeading.closest('.panel') as HTMLElement)

    // Classic's "mean pdui" column header shown by default.
    await waitFor(() => expect(trendPanel.getByRole('columnheader', { name: /mean pdui/i })).toBeInTheDocument())

    const user = userEvent.setup()
    await user.click(trendPanel.getByRole('tab', { name: /shannon entropy/i }))
    // Switching tabs swaps in shannon's own value_col/slope -- classic's is gone.
    await waitFor(() => expect(trendPanel.getByRole('columnheader', { name: /mean entropy/i })).toBeInTheDocument())
    expect(trendPanel.queryByRole('columnheader', { name: /mean pdui/i })).not.toBeInTheDocument()
  })

  // classic/shannon are computed out-of-band per celltype (2026-08-14) --
  // 'Fibroblast' is the mock's deliberately-not-yet-reindexed celltype (only
  // classic has a trend), so it covers the "not computed" disabled-tab path
  // truthfully rather than faking data.
  it('disables shannon without a computed trend, rather than faking or hiding it', async () => {
    useScopeStore.setState({ runId: 'fixture-run-0001', datasetId: 'ds1' })
    renderResults('/results/Fibroblast')

    const trendHeading = await screen.findByRole('heading', { name: /3'UTR length trend across stages/i })
    const trendPanel = within(trendHeading.closest('.panel') as HTMLElement)

    const shannonTab = trendPanel.getByRole('tab', { name: /shannon entropy/i })
    expect(shannonTab).toBeDisabled()
    expect(within(shannonTab).getByText(/not computed/i)).toBeInTheDocument()

    // classic is unaffected -- still selected and showing real data.
    expect(trendPanel.getByRole('tab', { name: /classic/i })).toHaveAttribute('aria-selected', 'true')
    expect(trendPanel.getByRole('tab', { name: /classic/i })).not.toBeDisabled()
  })

  // science-reports finding (2026-08-14): proportion's length trend is an
  // engine defect (uniform-padded, ~98% synthetic, constant across every
  // stage) -- NOT a real "no shortening" biological result. It must never
  // be presented as selectable, on ANY celltype, even one whose mock data
  // technically has a proportion trend row (unlike "not computed", this is
  // not a data-availability problem -- recomputing it changes nothing).
  it('always disables proportion as invalid (engine defect), never as a selectable trend', async () => {
    useScopeStore.setState({ runId: 'fixture-run-0001', datasetId: 'ds1' })
    // 'Tumor epithelial' DOES have a proportion trend row in the mock fixture
    // (see mockData.ts) -- proving the block is unconditional, not a
    // "not computed" gap that happens to coincide here.
    renderResults('/results/Tumor%20epithelial')

    const trendHeading = await screen.findByRole('heading', { name: /3'UTR length trend across stages/i })
    const trendPanel = within(trendHeading.closest('.panel') as HTMLElement)

    const proportionTab = trendPanel.getByRole('tab', { name: /^proportion/i })
    expect(proportionTab).toBeDisabled()
    expect(within(proportionTab).getByText(/invalid/i)).toBeInTheDocument()
    expect(proportionTab).toHaveAttribute('title', expect.stringMatching(/engine defect/i))

    // Clicking it does nothing -- classic stays selected, disabled buttons don't fire onClick.
    const user = userEvent.setup()
    await user.click(proportionTab)
    expect(trendPanel.getByRole('tab', { name: /classic/i })).toHaveAttribute('aria-selected', 'true')
    expect(proportionTab).toHaveAttribute('aria-selected', 'false')
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
