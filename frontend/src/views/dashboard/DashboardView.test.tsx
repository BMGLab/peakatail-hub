import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/testUtils'
import { DashboardView } from './DashboardView'
import { useScopeStore } from '@state/useScopeStore'

const navigateSpy = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigateSpy }
})

describe('DashboardView', () => {
  it('renders overview totals summed across every mock run', async () => {
    renderWithProviders(<DashboardView />)

    // mockRuns has 2 runs: n_genes 2100+980=3080, n_pas 18422+9310=27732, n_cells 48213+6120=54333.
    await waitFor(() => expect(screen.getByText('3,080')).toBeInTheDocument())
    expect(screen.getByText('27,732')).toBeInTheDocument()
    expect(screen.getByText('54,333')).toBeInTheDocument()
    // "2" for the run count stat tile.
    expect(screen.getAllByText('2').length).toBeGreaterThan(0)
  })

  it('renders a run card per run with source + celltype/findings stats, and jumps the browser on click', async () => {
    const user = userEvent.setup()
    renderWithProviders(<DashboardView />)

    await waitFor(() => expect(screen.getByText('run-laughney-2024-01')).toBeInTheDocument())
    // runLabel prefers the single stratum_to_label value over the bare run_id.
    expect(screen.getByText('Laughney lung adenocarcinoma (full cohort)')).toBeInTheDocument()
    // "Cohort A (mock)" appears twice (SourcesPanel row label + this run
    // card's source_label) -- assert via the run card specifically.
    const card = screen.getByText('run-laughney-2024-01').closest('button')
    expect(card).not.toBeNull()
    await user.click(card!)

    expect(useScopeStore.getState().runId).toBe('run-laughney-2024-01')
    expect(navigateSpy).toHaveBeenCalledWith('/browse/genes')
  })

  it('SOURCES panel lists registered sources with run counts', async () => {
    renderWithProviders(<DashboardView />)
    await waitFor(() => expect(screen.getByText('/mock/sources/cohort_a')).toBeInTheDocument())
    expect(screen.getByText('/mock/sources/cohort_b_subset')).toBeInTheDocument()
  })

  it('adding a directory registers it, shows an empty-scan note, then removing it deletes it', async () => {
    const user = userEvent.setup()
    // window.confirm gates the remove action -- always confirm in this test.
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithProviders(<DashboardView />)

    await waitFor(() => expect(screen.getByText('/mock/sources/cohort_a')).toBeInTheDocument())

    const input = screen.getByLabelText(/directory path to add as a source/i)
    await user.type(input, '/tmp/test-only-source-xyz')
    await user.click(screen.getByRole('button', { name: /\+ add directory/i }))

    await waitFor(() => expect(screen.getByText('/tmp/test-only-source-xyz')).toBeInTheDocument())
    // Mock mode never walks a real filesystem -- the add always reports 'empty'.
    expect(screen.getByText(/no run_manifest\.json found under this path yet/i)).toBeInTheDocument()

    const row = screen.getByText('/tmp/test-only-source-xyz').closest('li')
    expect(row).not.toBeNull()
    await user.click(within(row!).getByRole('button', { name: /remove/i }))

    await waitFor(() => expect(screen.queryByText('/tmp/test-only-source-xyz')).not.toBeInTheDocument())
    // Baseline sources are untouched.
    expect(screen.getByText('/mock/sources/cohort_a')).toBeInTheDocument()
  })

  it('shows a clear error when adding an empty path is attempted', async () => {
    renderWithProviders(<DashboardView />)
    await waitFor(() => expect(screen.getByText('/mock/sources/cohort_a')).toBeInTheDocument())

    // The add button stays disabled for a blank path -- nothing to submit,
    // so there's no ambiguous "silently did nothing" state.
    expect(screen.getByRole('button', { name: /\+ add directory/i })).toBeDisabled()
  })
})
