import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../test/testUtils'
import { AppShell } from './AppShell'

describe('AppShell', () => {
  it('renders every tab as a first-class nav link, Dashboard landing by default', async () => {
    renderWithProviders(<AppShell />)

    // Every route is one click away via the nav rail -- Dashboard (landing),
    // Browser (the one IGV-style tab), then the readable tables (Findings +
    // entity browsers), then the secondary analysis views. Tables are NOT
    // demoted behind a drawer/toggle here -- Findings is a normal nav link.
    expect(screen.getByRole('navigation', { name: /primary/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^dashboard$/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^browser$/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^findings$/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^genes$/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^pas$/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^cells$/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /umap/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /run \/ qc/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /audit/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /compare/i })).toBeInTheDocument()

    // No lingering drawer-toggle affordance -- Findings has no button role.
    expect(screen.queryByRole('button', { name: /^findings$/i })).not.toBeInTheDocument()

    // Shared detail panel starts empty regardless of which route is mounted
    expect(screen.getByLabelText(/detail panel/i)).toBeInTheDocument()
    expect(screen.getByText(/nothing selected/i)).toBeInTheDocument()

    // TopBar's location bar is the primary action -- present and NOT the
    // old generic "global search" label (it now also accepts chr:coords).
    expect(screen.getByLabelText(/genome location search/i)).toBeInTheDocument()

    // "/" is Dashboard (the landing view), not the genome browser.
    expect(await screen.findByRole('heading', { name: /dashboard/i })).toBeInTheDocument()
  })

  it('navigates to a normal Findings route (not a drawer) from the nav rail', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AppShell />)

    await user.click(screen.getByRole('link', { name: /^findings$/i }))

    // FindingsView mounted as the main route content -- its facets panel
    // heading is a reliable signal, and there's no dialog/backdrop wrapper.
    expect(await screen.findByRole('heading', { name: 'Facets' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
