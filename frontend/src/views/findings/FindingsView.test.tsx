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

    // Then the mock data resolves (240 mock rows from src/lib/api/mockData.ts)
    const toolbar = await screen.findByText(/findings \(showing/i, {}, { timeout: 3000 })
    expect(toolbar.textContent).toMatch(/240 findings/)

    // Table headers render
    expect(screen.getByRole('columnheader', { name: 'gene' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'strategy' })).toBeInTheDocument()
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

    // Facet selects are populated from mock facets
    const strategySelect = await screen.findByRole('combobox', { name: /strategy/i })
    expect(within(strategySelect).getByRole('option', { name: 'nb_multi' })).toBeInTheDocument()
  })

  it('filters the table when a facet is changed', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FindingsView />)

    await screen.findByText(/findings \(showing/i, {}, { timeout: 3000 })

    const strategySelect = await screen.findByRole('combobox', { name: /strategy/i })
    await user.selectOptions(strategySelect, 'nb_multi')

    // 240 rows cycle through 3 strategies evenly -> filtering to one strategy
    // should show fewer than the full 240. Wait for the toolbar text to
    // actually change (it already matched the "findings (showing" pattern
    // before the filter was applied, so we must wait for the count itself).
    await waitFor(() => {
      const toolbar = screen.getByText(/findings \(showing/i)
      const match = toolbar.textContent?.match(/(\d+) findings/)
      expect(match).not.toBeNull()
      expect(Number(match![1])).toBeLessThan(240)
      expect(Number(match![1])).toBeGreaterThan(0)
    })
  })
})
