import { describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/testUtils'
import { PasBrowser } from './PasBrowser'

describe('PasBrowser', () => {
  it('renders the full mock PAS ledger (all genes, not just one)', async () => {
    renderWithProviders(<PasBrowser />)

    // mockPasForGene(gene) returns gene.n_pas rows per gene (4+3+6+2=15 mock genes)
    await waitFor(() => expect(screen.getByText(/15 pas/i)).toBeInTheDocument())
  })

  it('filters by gene_id substring', async () => {
    const user = userEvent.setup()
    renderWithProviders(<PasBrowser />)
    await waitFor(() => expect(screen.getByText(/15 pas/i)).toBeInTheDocument())

    await user.type(screen.getByRole('searchbox', { name: /search pas/i }), 'ENSG00000171862') // PTEN, n_pas=2
    await waitFor(() => expect(screen.getByText(/2 pas/i)).toBeInTheDocument(), { timeout: 2000 })
  })
})
