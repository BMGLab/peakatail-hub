import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { renderWithProviders } from '../../test/testUtils'

/**
 * Regression test for a real bug found via a real headless-Chromium smoke
 * pass (not jsdom): GeneView fully crashed on every real gene because
 * `geneviewData?.length.map(...)` read a property the backend calls
 * `length_rows`, not `length` -- `?.` only guarded `geneviewData` itself,
 * so `.length` (a plain property read, not the array) was `undefined` and
 * `.map` threw, unmounting the whole view via React's error boundary.
 *
 * The existing FindingsView tests all run against `mockData.ts`, which is
 * hand-shaped to already match the frontend's internal types -- exactly
 * the layer that was wrong. This test instead stubs `fetch` with the REAL
 * backend wire shapes (schemas.py GeneSummary/GeneviewData field names,
 * copied from an actual `curl` against the running backend) and forces
 * `VITE_USE_MOCKS=false` so client.ts's real-fetch translation path runs,
 * the same path that broke in the browser. Asserts real DOM content
 * (ruler/PAS-list rows), not just "did it not throw" -- a toolbar-text-only
 * assertion is exactly what let the analogous findings-table bug hide.
 */
describe('GeneView against real backend wire shapes', () => {
  const GENE_ID = 'ENSG00000000001'

  const backendGeneSummary = {
    gene_id: GENE_ID,
    run_id: 'fixture-run-0001',
    n_pas: 2,
    n_findings: 2,
    n_length_rows: 4,
    span: { chrom: 'chr1', start: 999, end: 1500, strand: '+', n_pas: 2 },
  }

  const backendGeneviewData = {
    gene_id: GENE_ID,
    run_id: 'fixture-run-0001',
    span: backendGeneSummary.span,
    window: { start: 999, end: 1500 },
    pas: [
      {
        pas_uid: 'chr1:999:+',
        chrom: 'chr1',
        start: 999,
        end: 1000,
        strand: '+',
        unified_pas_id: 'unified_1',
        gene_distance_bp: 50,
        snap_distance_bp: 12,
        tier: 'TIER_1',
      },
      {
        pas_uid: 'chr1:1499:+',
        chrom: 'chr1',
        start: 1499,
        end: 1500,
        strand: '+',
        unified_pas_id: 'unified_2',
        gene_distance_bp: 550,
        snap_distance_bp: 8,
        tier: 'TIER_2',
      },
    ],
    // The exact field name (`length_rows`, not `length`) that crashed GeneView.
    findings: [],
    length_rows: [
      { strategy: 'classic', gene_id: GENE_ID, transcript_id: null, cell_uid: 'ds1:AAACCCAAGT', canonical_cluster: 'cl_A', value: 0.62, pas_uid: null, rank: null, direction: null },
    ],
    gates: [],
  }

  let GeneView: typeof import('./GeneView').GeneView

  beforeEach(async () => {
    vi.resetModules()
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL) => {
        const s = url.toString()
        if (s.includes('/geneview-data')) {
          return new Response(JSON.stringify(backendGeneviewData), { status: 200 })
        }
        if (s.includes(`/genes/${GENE_ID}`)) {
          return new Response(JSON.stringify(backendGeneSummary), { status: 200 })
        }
        return new Response('not found', { status: 404 })
      }),
    )
    ;({ GeneView } = await import('./GeneView'))
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it('renders real coordinates, ruler, and the PAS list -- does not crash on the real wire shape', async () => {
    renderWithProviders(
      <Routes>
        <Route path="/genes/:geneId" element={<GeneView />} />
      </Routes>,
      { initialEntries: [`/genes/${GENE_ID}`] },
    )

    // Real coordinates from `span`, not a "gene_name" field that doesn't
    // exist on the wire -- proves the span-flattening translation ran.
    await waitFor(() => expect(screen.getByText('chr1:999-1500 (+)')).toBeInTheDocument(), { timeout: 3000 })

    // The PAS list table (fed by `geneviewData.pas`) has real rows -- proves
    // the view rendered past the point that used to crash on `.length`.
    expect(screen.getByText('chr1:999:+')).toBeInTheDocument()
    expect(screen.getByText('chr1:1499:+')).toBeInTheDocument()
    expect(screen.getByText('TIER_1')).toBeInTheDocument()
  })

  it('shows "coordinates unavailable" instead of crashing when span is null (gene has zero surviving PAS)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL) => {
        const s = url.toString()
        if (s.includes('/geneview-data')) {
          return new Response(JSON.stringify({ ...backendGeneviewData, span: null, pas: [] }), { status: 200 })
        }
        if (s.includes(`/genes/${GENE_ID}`)) {
          return new Response(JSON.stringify({ ...backendGeneSummary, span: null }), { status: 200 })
        }
        return new Response('not found', { status: 404 })
      }),
    )
    const { GeneView: FreshGeneView } = await import('./GeneView')
    renderWithProviders(
      <Routes>
        <Route path="/genes/:geneId" element={<FreshGeneView />} />
      </Routes>,
      { initialEntries: [`/genes/${GENE_ID}`] },
    )

    await waitFor(() => expect(screen.getByText('coordinates unavailable')).toBeInTheDocument(), { timeout: 3000 })
  })
})
