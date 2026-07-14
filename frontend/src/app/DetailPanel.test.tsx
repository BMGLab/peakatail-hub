import { afterEach, describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../test/testUtils'
import { DetailPanel } from './DetailPanel'
import { useSelectionStore } from '@state/useSelectionStore'

afterEach(() => {
  useSelectionStore.getState().clear()
})

describe('DetailPanel', () => {
  it('shows the empty state when nothing is selected', () => {
    renderWithProviders(<DetailPanel />)
    expect(screen.getByText(/nothing selected/i)).toBeInTheDocument()
  })

  it('shows gene fields + actions when a gene is selected', () => {
    useSelectionStore.getState().select({
      kind: 'gene',
      data: { gene_id: 'ENSG00000141510', gene_name: 'TP53', chrom: 'chr17', start: 1, end: 2, strand: '-', n_pas: 4 },
    })

    renderWithProviders(<DetailPanel />)

    expect(screen.getByText('TP53')).toBeInTheDocument()
    expect(screen.getByText('ENSG00000141510')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /open geneview/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /trace provenance/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^pin$/i })).toBeInTheDocument()
  })
})
