import { describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/testUtils'
import { CellBrowser } from './CellBrowser'

describe('CellBrowser', () => {
  it('renders the full mock cell ledger, including dropped rows', async () => {
    renderWithProviders(<CellBrowser />)

    // 40 mock cells (see mockData.ts), every 11th dropped at matrixfilter
    await waitFor(() => expect(screen.getByText(/40 cells/i)).toBeInTheDocument())
    expect(screen.getAllByText(/dropped @ matrixfilter/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText('survived').length).toBeGreaterThan(0)
  })

  it('filters by barcode substring', async () => {
    const user = userEvent.setup()
    renderWithProviders(<CellBrowser />)
    await waitFor(() => expect(screen.getByText(/40 cells/i)).toBeInTheDocument())

    await user.type(screen.getByRole('searchbox', { name: /search cells/i }), 'AAACCTG00003')
    await waitFor(() => expect(screen.getByText(/1 cells/i)).toBeInTheDocument(), { timeout: 2000 })
  })
})
