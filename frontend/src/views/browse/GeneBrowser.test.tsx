import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/testUtils'
import { GeneBrowser } from './GeneBrowser'
import { useSelectionStore } from '@state/useSelectionStore'

const navigateSpy = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigateSpy }
})

describe('GeneBrowser', () => {
  it('renders mock genes and jumps the browser + selects the row on click', async () => {
    const user = userEvent.setup()
    renderWithProviders(<GeneBrowser />)

    await waitFor(() => expect(screen.getByText(/4 genes/i)).toBeInTheDocument())
    expect(screen.getByText('ENSG00000141510')).toBeInTheDocument()

    await user.click(screen.getByText('ENSG00000141510'))

    expect(navigateSpy).toHaveBeenCalledWith('/genes/ENSG00000141510')
    expect(useSelectionStore.getState().selected).toEqual(
      expect.objectContaining({
        kind: 'gene',
        data: expect.objectContaining({ gene_id: 'ENSG00000141510' }),
      }),
    )
  })

  it('filters rows by debounced search text (substring match on gene_id)', async () => {
    const user = userEvent.setup()
    renderWithProviders(<GeneBrowser />)
    await waitFor(() => expect(screen.getByText(/4 genes/i)).toBeInTheDocument())

    // KRAS's gene_id is ENSG00000133703 -- the real backend (and this mock)
    // only searches gene_id, no symbol table exists yet (see GeneListRow's
    // doc comment) -- assert against that real contract, not a symbol match.
    await user.type(screen.getByRole('searchbox', { name: /search genes/i }), '0133703')

    await waitFor(() => expect(screen.getByText(/1 genes/i)).toBeInTheDocument(), { timeout: 2000 })
    expect(screen.getByText('ENSG00000133703')).toBeInTheDocument()
    expect(screen.queryByText('ENSG00000141510')).not.toBeInTheDocument()
  })
})
