import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../test/testUtils'
import { AppShell } from './AppShell'

describe('AppShell', () => {
  it('renders the nav rail links and the detail panel empty state', async () => {
    renderWithProviders(<AppShell />)

    // Nav rail: IGV-style reframe -- "Browser" (GeneView, the landing route)
    // leads, then the searchable entity browsers, then the secondary
    // analysis views. Findings is intentionally NOT a nav link here (see
    // below) -- it's a drawer toggled from the TopBar, not a route.
    expect(screen.getByRole('navigation', { name: /primary/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^browser$/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^genes$/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^pas$/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^cells$/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /umap/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /run \/ qc/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /audit/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /compare/i })).toBeInTheDocument()

    // Shared detail panel starts empty
    expect(screen.getByLabelText(/detail panel/i)).toBeInTheDocument()
    expect(screen.getByText(/nothing selected/i)).toBeInTheDocument()

    // TopBar's location bar is the primary action -- present and NOT the
    // old generic "global search" label (it now also accepts chr:coords).
    expect(screen.getByLabelText(/genome location search/i)).toBeInTheDocument()

    // Findings is reachable via a TopBar toggle (opens a secondary drawer),
    // not a nav-rail route link.
    expect(screen.queryByRole('link', { name: /findings/i })).not.toBeInTheDocument()
    const findingsToggle = screen.getByRole('button', { name: /findings/i })
    expect(findingsToggle).toBeInTheDocument()
    expect(findingsToggle).toHaveAttribute('aria-pressed', 'false')
  })

  it('opens the findings drawer from the TopBar toggle', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AppShell />)

    expect(screen.queryByRole('dialog', { name: /findings/i })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /findings/i }))

    expect(screen.getByRole('dialog', { name: /findings/i })).toBeInTheDocument()
    // The drawer mounts the real FindingsView -- its facets panel heading is
    // a reliable signal it rendered, not just an empty shell.
    expect(await screen.findByRole('heading', { name: 'Facets' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /close findings drawer/i }))
    expect(screen.queryByRole('dialog', { name: /findings/i })).not.toBeInTheDocument()
  })
})
