import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../test/testUtils'
import { AppShell } from './AppShell'

describe('AppShell', () => {
  it('renders the nav rail links and the detail panel empty state', async () => {
    renderWithProviders(<AppShell />)

    // Nav rail links (findings/gene omitted since it's not in navRoutes/umap/qc/audit/compare)
    expect(screen.getByRole('navigation', { name: /primary/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /findings/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /umap/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /run \/ qc/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /audit/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /compare/i })).toBeInTheDocument()

    // Shared detail panel starts empty
    expect(screen.getByLabelText(/detail panel/i)).toBeInTheDocument()
    expect(screen.getByText(/nothing selected/i)).toBeInTheDocument()

    // Top bar search input present
    expect(screen.getByLabelText(/global search/i)).toBeInTheDocument()
  })
})
