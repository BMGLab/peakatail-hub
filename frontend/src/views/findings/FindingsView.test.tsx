import { describe, expect, it } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/testUtils'
import { FindingsView } from './FindingsView'

describe('FindingsView', () => {
  it('loads mock findings and renders the table + facets', async () => {
    renderWithProviders(<FindingsView />)

    // Loading state first
    expect(screen.getByText(/loading findings/i)).toBeInTheDocument()

    // Then the mock data resolves (300 mock rows from src/lib/api/mockData.ts:
    // 240 diff findings (fisher/nb_pairwise/nb_multi) + 60 length-strategy
    // pseudo-findings (classic/proportion/shannon, 2026-08-14 -- "Findings
    // shows ALL strategies", not just fisher).
    const toolbar = await screen.findByText(/findings \(showing/i, {}, { timeout: 3000 })
    expect(toolbar.textContent).toMatch(/300 findings/)

    // Table headers render -- "Gene" (symbol, 2026-08-14) alongside gene_id,
    // and slope/spearman (2026-08-14, the length-strategy counterpart to q/Δ
    // proportion, populated only for classic/proportion/shannon rows).
    expect(screen.getByRole('columnheader', { name: 'Gene' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'gene_id' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'strategy' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'slope' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'spearman' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'caveats' })).toBeInTheDocument()

    // Regression guard: the virtualized body must actually render <tr>s,
    // not just report a correct "showing N" count in the toolbar. Two real
    // bugs both produced "showing 240" with zero visible rows: (1)
    // `useMemo(() => virtualizer.getVirtualItems(), [virtualizer])` never
    // recomputed because `virtualizer` is the same mutated-in-place
    // instance every render, so it froze at the empty result from before
    // data loaded; (2) absolutely-positioned <tr>s styled `display: table`
    // computed zero-width columns. Neither is visible from the toolbar text
    // alone -- assert real row content is on screen too.
    await waitFor(() => {
      expect(document.querySelectorAll('.findings-view__table tbody tr').length).toBeGreaterThan(0)
    })

    // Facet selects are populated from mock facets -- ALL FIVE strategies
    // (2026-08-14: diff's fisher/nb_pairwise/nb_multi AND length's
    // classic/proportion/shannon), the exact facet team-lead flagged as
    // fisher-only on the live API before this fix.
    const strategySelect = await screen.findByRole('combobox', { name: /strategy/i })
    expect(within(strategySelect).getByRole('option', { name: 'nb_multi' })).toBeInTheDocument()
    expect(within(strategySelect).getByRole('option', { name: 'classic' })).toBeInTheDocument()
    expect(within(strategySelect).getByRole('option', { name: 'proportion' })).toBeInTheDocument()
    expect(within(strategySelect).getByRole('option', { name: 'shannon' })).toBeInTheDocument()
  })

  it('filters the table when a facet is changed', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FindingsView />)

    await screen.findByText(/findings \(showing/i, {}, { timeout: 3000 })

    const strategySelect = await screen.findByRole('combobox', { name: /strategy/i })
    await user.selectOptions(strategySelect, 'nb_multi')

    // 300 rows split across 6 buckets (3 diff strategies x 240 evenly, plus
    // 60 length rows) -> filtering to one strategy should show fewer than
    // the full 300. Wait for the toolbar text to actually change (it
    // already matched the "findings (showing" pattern before the filter
    // was applied, so we must wait for the count itself).
    await waitFor(() => {
      const toolbar = screen.getByText(/findings \(showing/i)
      const match = toolbar.textContent?.match(/(\d+) findings/)
      expect(match).not.toBeNull()
      expect(Number(match![1])).toBeLessThan(300)
      expect(Number(match![1])).toBeGreaterThan(0)
    })
  })

  // 2026-08-14: the core "Findings shows ALL strategies" behavior --
  // selecting a REAL length strategy (classic) filters to real rows and
  // shows real slope/spearman numbers, no engine-defect warning. Own
  // render + a single facet interaction (not chained with the proportion
  // case below) -- react-select controlled-value updates in jsdom are
  // flaky across a SECOND selectOptions call on the same element within
  // one test; isolating each facet change to its own render sidesteps it
  // and is better test hygiene regardless.
  it('selecting the classic length strategy shows real slope/spearman rows, no warning', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FindingsView />)

    await screen.findByText(/findings \(showing/i, {}, { timeout: 3000 })
    const strategySelect = await screen.findByRole('combobox', { name: /strategy/i })
    await user.selectOptions(strategySelect, 'classic')

    await waitFor(() => {
      const toolbar = screen.getByText(/findings \(showing/i)
      expect(toolbar.textContent).toMatch(/20 findings/) // 60 mock length rows / 3 strategies
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument() // classic is real, no warning
    // qvalue/Δ proportion don't exist at this grain -- '—', not a crash.
    await waitFor(() => {
      const rows = document.querySelectorAll('.findings-view__table tbody tr')
      expect(rows.length).toBeGreaterThan(0)
    })
  })

  // science-reports finding (2026-08-14, same day): proportion's engine
  // padding defect was fixed and reconfirmed with real varying data --
  // selecting it in Findings' strategy facet now shows real rows, no
  // warning, same as classic/shannon. Replaces the earlier
  // "shows the invalid-engine-defect warning" test.
  it('selecting the proportion strategy shows real rows, no warning', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FindingsView />)

    await screen.findByText(/findings \(showing/i, {}, { timeout: 3000 })
    const strategySelect = await screen.findByRole('combobox', { name: /strategy/i })
    await user.selectOptions(strategySelect, 'proportion')

    await waitFor(() => {
      const toolbar = screen.getByText(/findings \(showing/i)
      expect(toolbar.textContent).toMatch(/20 findings/) // 60 mock length rows / 3 strategies
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
