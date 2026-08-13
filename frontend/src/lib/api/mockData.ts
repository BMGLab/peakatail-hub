// In-memory mock fixtures. Field names/shapes match src/lib/contract/types.ts.
// Swap-out point: once the backend + packages/io land, lib/api/client.ts
// functions below get real fetch bodies instead of these fixtures.
import type {
  CellDetail,
  CellLedgerRow,
  FindingRow,
  GeneListRow,
  GeneSummary,
  GeneviewClusterTrack,
  GeneviewIsoform,
  GeneviewLayerData,
  LengthRow,
  PasDetail,
  PasLedgerRow,
  RunQc,
  RunSummary,
  SearchResult,
  Source,
  StubResponse,
  UmapPoint,
} from '@lib/contract/types'

export const mockRuns: RunSummary[] = [
  {
    run_id: 'run-laughney-2024-01',
    root: '/mock/runs/run-laughney-2024-01',
    contract_version: '0.1.0',
    resolved_config: {},
    stratum_to_label: { laughney_lung: 'Laughney lung adenocarcinoma (full cohort)' },
    n_datasets: 12,
    n_cells: 48213,
    n_pas: 18422,
    n_genes: 2100,
    n_findings: 340,
    n_length_rows: 5200,
    indexed_at: '2026-06-01T00:00:00Z',
    source_id: 'src_mock_a',
    source_path: '/mock/sources/cohort_a',
    source_label: 'Cohort A (mock)',
    n_celltypes: 4,
  },
  {
    run_id: 'run-laughney-2024-01-subset',
    root: '/mock/runs/run-laughney-2024-01-subset',
    contract_version: '0.1.0',
    resolved_config: {},
    stratum_to_label: { laughney_lung_subset: 'Laughney lung adenocarcinoma (QC subset)' },
    n_datasets: 3,
    n_cells: 6120,
    n_pas: 9310,
    n_genes: 980,
    n_findings: 88,
    n_length_rows: 1400,
    indexed_at: '2026-05-15T00:00:00Z',
    source_id: 'src_mock_b',
    source_path: '/mock/sources/cohort_b_subset',
    source_label: 'Cohort B subset (mock)',
    n_celltypes: 3,
  },
]

// Seed data for the dashboard's SOURCES panel in mock mode. Loosely mirrors
// mockRuns' source_id/source_path pairing above -- dev-only demo data, not a
// live filesystem (see client.ts's addSource/rescanSource/deleteSource mock
// branches, which mutate a clone of this array rather than actually walking
// a directory).
export const mockSources: Source[] = [
  {
    source_id: 'src_mock_a',
    path: '/mock/sources/cohort_a',
    label: 'Cohort A (mock)',
    added_at: '2026-06-01T00:00:00Z',
    last_scanned_at: '2026-06-01T00:05:00Z',
    last_scan_status: 'ok',
    last_scan_error: null,
    run_count: 1,
  },
  {
    source_id: 'src_mock_b',
    path: '/mock/sources/cohort_b_subset',
    label: 'Cohort B subset (mock)',
    added_at: '2026-05-15T00:00:00Z',
    last_scanned_at: '2026-05-15T00:02:00Z',
    last_scan_status: 'ok',
    last_scan_error: null,
    run_count: 1,
  },
]

const genes: GeneSummary[] = [
  { gene_id: 'ENSG00000141510', gene_name: 'TP53', chrom: 'chr17', start: 7661779, end: 7687550, strand: '-', n_pas: 4 },
  { gene_id: 'ENSG00000133703', gene_name: 'KRAS', chrom: 'chr12', start: 25204789, end: 25250936, strand: '-', n_pas: 3 },
  { gene_id: 'ENSG00000146648', gene_name: 'EGFR', chrom: 'chr7', start: 55019017, end: 55211628, strand: '+', n_pas: 6 },
  { gene_id: 'ENSG00000171862', gene_name: 'PTEN', chrom: 'chr10', start: 87862638, end: 87971930, strand: '+', n_pas: 2 },
]

export const mockGenes: GeneSummary[] = genes

const clusters = ['0', '1', '2', '3']
const celltypes = ['Tumor epithelial', 'T cell', 'Macrophage', 'Fibroblast']
const strategies: FindingRow['strategy'][] = ['fisher', 'nb_pairwise', 'nb_multi']
const directions: FindingRow['direction'][] = ['shorten', 'lengthen', 'flat', 'undetermined']
const lengthDirections: NonNullable<LengthRow['direction']>[] = ['shorten', 'lengthen', 'flat']
const utrClasses = ['canonical', 'extended', 'intronic', null]

function seeded(i: number, salt: number): number {
  const x = Math.sin(i * 12.9898 + salt * 78.233) * 43758.5453
  return x - Math.floor(x)
}

export const mockFindings: FindingRow[] = Array.from({ length: 240 }, (_, i) => {
  const gene = genes[i % genes.length]!
  const strategy = strategies[i % strategies.length]!
  const direction = directions[i % directions.length]!
  const qvalue = seeded(i, 1) * 0.2
  return {
    finding_uid: `finding-${i.toString().padStart(4, '0')}`,
    pas_uid: `${gene.chrom}:${gene.start! + i * 37}:${gene.strand}`,
    gene_id: gene.gene_id,
    canonical_cluster: clusters[i % clusters.length]!,
    celltype: celltypes[i % celltypes.length]!,
    strategy,
    arm: i % 2 === 0 ? 'tumor_vs_normal' : 'early_vs_late',
    direction,
    utr_class: utrClasses[i % utrClasses.length] ?? null,
    qvalue,
    pvalue: qvalue * seeded(i, 2),
    delta_proportion: (seeded(i, 3) - 0.5) * 0.6,
    log2fc: (seeded(i, 4) - 0.5) * 4,
    n_cells: Math.floor(seeded(i, 5) * 500) + 20,
    n_reads: Math.floor(seeded(i, 6) * 5000) + 100,
  }
})

export const mockLengths: LengthRow[] = Array.from({ length: 120 }, (_, i) => {
  const gene = genes[i % genes.length]!
  const strategy: LengthRow['strategy'] = (['classic', 'proportion', 'shannon'] as const)[i % 3]!
  return {
    pas_uid: strategy === 'proportion' ? `${gene.chrom}:${gene.start! + i * 41}:${gene.strand}` : null,
    gene_id: gene.gene_id,
    transcript_id: `${gene.gene_id}-T1`,
    strategy,
    cell_uid: `cell-${(i % 40).toString().padStart(4, '0')}`,
    canonical_cluster: clusters[i % clusters.length]!,
    value: seeded(i, 7) * 2 - 1,
    // direction is populated for ALL strategies (engine 2026-07-14
    // correction); shannon has no polarity axis -> always 'undetermined'.
    direction: strategy === 'shannon' ? 'undetermined' : lengthDirections[i % lengthDirections.length]!,
    direction_basis: 'structural',
    rank: strategy === 'proportion' ? (i % 40) + 1 : null,
  }
})

export function mockPasForGene(geneId: string): PasDetail[] {
  const gene = genes.find((g) => g.gene_id === geneId)
  if (!gene) return []
  const start = gene.start!
  return Array.from({ length: gene.n_pas }, (_, i) => ({
    orig_pas_key: `orig-${geneId}-${i}`,
    chrom: gene.chrom!,
    start: start + i * 400,
    end: start + i * 400 + 20,
    strand: gene.strand!,
    unified_pas_id: `unified-${geneId}-${i}`,
    pas_uid: `${gene.chrom}:${start + i * 400 + 10}:${gene.strand}`,
    snap_distance_bp: i === 0 ? 0 : 12 * i,
    gene_id: gene.gene_id,
    gene_distance_bp: 50 * i,
    tier: i === 0 ? 'primary' : 'alternative',
    last_stage: 'switch_diff',
    dropped_at: '',
    drop_reason: null,
    gene_name: gene.gene_name,
    per_cluster_counts: Object.fromEntries(clusters.map((c, ci) => [c, Math.floor(seeded(i, ci) * 200)])),
    umi_deduplicated: false,
  }))
}

/**
 * Synthesize a plausible isoform/exon structure from a gene's own PAS
 * positions: two upstream exons of fixed width, then one terminal exon per
 * isoform whose 3' end lands progressively further out (mirroring a
 * tandem-3'UTR gene like the PeakATail CLIC2 reference figure, where each
 * shorter isoform's terminal exon ends at a nearer PAS). Mock-only data --
 * the real endpoint sources this from a GTF via `peakatail_hub.gtf`.
 */
function mockIsoformsForGene(gene: GeneSummary, pas: PasDetail[]): GeneviewIsoform[] {
  if (gene.start === null || gene.end === null || pas.length === 0) return []
  const ascending = [...pas].sort((a, b) => a.end - b.end)
  const spanStart = gene.start
  const upstream1: [number, number] = [spanStart, spanStart + 60]
  const upstream2: [number, number] = [spanStart + 140, spanStart + 220]
  // One isoform per distinct terminal PAS, shortest-3'UTR first, so the
  // isoform track shows the same "each isoform ends at a different PAS"
  // story as the reference figure.
  return ascending.map((p, i) => ({
    transcript_id: `${gene.gene_id.replace('ENSG', 'ENST')}${(i + 1).toString().padStart(2, '0')}`,
    exons: [upstream1, upstream2, [Math.max(upstream2[1] + 40, p.start - 20), p.end]] as [number, number][],
  }))
}

/** Derive per-cluster proportion tracks from the same `per_cluster_counts`
 * already used for PAS stems, so mock mode exercises the exact renderer
 * shape the real backend's `cluster_tracks` field carries (see
 * schemas.py GeneviewClusterTrack) without a second parallel fixture. */
function mockClusterTracks(pas: PasDetail[]): GeneviewClusterTrack[] {
  if (pas.length === 0) return []
  return clusters.map((cluster) => {
    const reads = pas.map((p) => p.per_cluster_counts[cluster] ?? 0)
    const total = reads.reduce((a, b) => a + b, 0)
    return {
      cluster,
      n_cells: 20 + clusters.indexOf(cluster) * 7,
      values: pas.map((p, i) => ({
        pas_uid: p.pas_uid,
        reads_per_cell: reads[i]! / 10,
        proportion: total > 0 ? reads[i]! / total : null,
      })),
    }
  })
}

export function mockGeneviewData(geneId: string): GeneviewLayerData | null {
  const gene = genes.find((g) => g.gene_id === geneId)
  if (!gene) return null
  const pas = mockPasForGene(geneId)
  return {
    gene,
    window: { chrom: gene.chrom, start: gene.start, end: gene.end },
    pas,
    diff: mockFindings.filter((f) => f.gene_id === geneId),
    length: mockLengths.filter((l) => l.gene_id === geneId),
    coverage: null,
    gates: [],
    isoforms: mockIsoformsForGene(gene, pas),
    clusterTracks: mockClusterTracks(pas),
  }
}

export const mockCells: CellDetail[] = Array.from({ length: 40 }, (_, i) => ({
  barcode: `AAACCTG${i.toString().padStart(5, '0')}-1`,
  cell_uid: `cell-${i.toString().padStart(4, '0')}`,
  dataset_id: 'laughney_lung',
  total_reads: Math.floor(seeded(i, 8) * 20000) + 500,
  n_pas: Math.floor(seeded(i, 9) * 40) + 2,
  dropped_at: i % 11 === 0 ? 'matrixfilter' : '',
  drop_reason: i % 11 === 0 ? 'below min_pas_per_cell' : null,
  cluster: clusters[i % clusters.length]!,
  celltype: celltypes[i % celltypes.length]!,
}))

export const mockUmap: UmapPoint[] = Array.from({ length: 800 }, (_, i) => {
  const cluster = i % clusters.length
  const angle = seeded(i, 10) * Math.PI * 2
  const r = 2 + cluster * 1.5 + seeded(i, 11) * 1.2
  return {
    cell_uid: `cell-${i.toString().padStart(4, '0')}`,
    x: Math.cos(angle) * r + cluster * 4,
    y: Math.sin(angle) * r + cluster * 2,
    leiden: clusters[cluster]!,
    celltype: celltypes[cluster]!,
    stage: null,
    sample: null,
  }
})

export const mockRunQc: Record<string, RunQc> = {
  'run-laughney-2024-01': {
    run_id: 'run-laughney-2024-01',
    n_pas_total: 42000,
    n_pas_survived: 18422,
    n_cells_total: 52000,
    n_cells_survived: 48213,
    pas_drop_by_stage: [
      { stage: 'atlas_snap', dropped: 6500 },
      { stage: 'coord_merge', dropped: 900 },
      { stage: 'matrix_concat', dropped: 0 },
      { stage: 'cb_filter', dropped: 0 },
      { stage: 'pas_gene_assignment', dropped: 12800 },
      { stage: 'preprocess', dropped: 2600 },
      { stage: 'marker_subset', dropped: 778 },
    ],
    cell_drop_by_stage: [
      { stage: 'atlas_snap', dropped: 0 },
      { stage: 'coord_merge', dropped: 0 },
      { stage: 'matrix_concat', dropped: 0 },
      { stage: 'cb_filter', dropped: 2200 },
      { stage: 'pas_gene_assignment', dropped: 0 },
      { stage: 'preprocess', dropped: 900 },
      { stage: 'marker_subset', dropped: 687 },
    ],
    per_sample_stats_available: false,
    gate_note: 'Per-dataset stage-entry counts require engine B5 (+E3); mock data for the frontend-only dev path.',
  },
}

export const mockConcordance: Record<string, StubResponse> = {
  'run-laughney-2024-01': {
    run_id: 'run-laughney-2024-01',
    available: false,
    note: 'No concordance (ARI/AMI) artifact schema exists in peakatail-contract yet; nothing to read.',
  },
}

export const mockBenchmarks: Record<string, StubResponse> = {
  'run-laughney-2024-01': {
    run_id: 'run-laughney-2024-01',
    available: false,
    note: 'No benchmark artifact schema exists in peakatail-contract yet; nothing to read.',
  },
}

// ---------------------------------------------------------------------------
// Browse: mock-mode GET /genes, /pas, /cells (searchable, paginated lists)
// ---------------------------------------------------------------------------

interface MockPage<T> {
  rows: T[]
  nextCursor: string | null
  total: number
}

function paginate<T>(rows: T[], cursor: string | undefined, limit: number): MockPage<T> {
  const offset = cursor ? Number(cursor) : 0
  const total = rows.length
  const page = rows.slice(offset, offset + limit)
  const nextOffset = offset + limit
  const nextCursor = nextOffset < total ? String(nextOffset) : null
  return { rows: page, nextCursor, total }
}

const mockGeneListRows: GeneListRow[] = genes.map((g) => ({
  gene_id: g.gene_id,
  chrom: g.chrom,
  start: g.start,
  end: g.end,
  strand: g.strand,
  n_pas: g.n_pas,
  n_findings: mockFindings.filter((f) => f.gene_id === g.gene_id).length,
}))

const mockAllPas: PasLedgerRow[] = genes.flatMap((g) => mockPasForGene(g.gene_id))

export interface MockGenesBrowseParams {
  q?: string | undefined
  chrom?: string | undefined
  start?: number | undefined
  end?: number | undefined
  cursor?: string | undefined
  limit?: number | undefined
}

export function mockGenesPage(params: MockGenesBrowseParams): MockPage<GeneListRow> {
  let rows = mockGeneListRows
  if (params.q) {
    const q = params.q.toLowerCase()
    rows = rows.filter((g) => g.gene_id.toLowerCase().includes(q))
  }
  if (params.chrom) rows = rows.filter((g) => g.chrom === params.chrom)
  if (params.start !== undefined) rows = rows.filter((g) => g.end !== null && g.end >= params.start!)
  if (params.end !== undefined) rows = rows.filter((g) => g.start !== null && g.start <= params.end!)
  return paginate(rows, params.cursor, params.limit ?? 50)
}

export interface MockBrowseParams {
  q?: string | undefined
  cursor?: string | undefined
  limit?: number | undefined
}

export function mockPasPage(params: MockBrowseParams): MockPage<PasLedgerRow> {
  let rows = mockAllPas
  if (params.q) {
    const q = params.q.toLowerCase()
    rows = rows.filter(
      (p) => p.pas_uid.toLowerCase().includes(q) || (p.gene_id ?? '').toLowerCase().includes(q) || p.unified_pas_id.toLowerCase().includes(q),
    )
  }
  return paginate(rows, params.cursor, params.limit ?? 50)
}

export function mockCellsPage(params: MockBrowseParams): MockPage<CellLedgerRow> {
  let rows: CellLedgerRow[] = mockCells
  if (params.q) {
    const q = params.q.toLowerCase()
    rows = rows.filter(
      (c) => c.barcode.toLowerCase().includes(q) || c.cell_uid.toLowerCase().includes(q) || (c.cluster ?? '').toLowerCase().includes(q),
    )
  }
  return paginate(rows, params.cursor, params.limit ?? 50)
}

export function mockSearch(q: string): SearchResult[] {
  const query = q.trim().toLowerCase()
  if (!query) return []
  const results: SearchResult[] = []
  for (const g of genes) {
    if (g.gene_name.toLowerCase().includes(query) || g.gene_id.toLowerCase().includes(query)) {
      results.push({ kind: 'gene', id: g.gene_id, label: g.gene_name, sublabel: g.gene_id })
    }
  }
  for (const f of mockFindings) {
    if (f.pas_uid.toLowerCase().includes(query)) {
      results.push({ kind: 'pas', id: f.pas_uid, label: f.pas_uid, sublabel: f.gene_id })
      if (results.length > 20) break
    }
  }
  for (const c of mockCells) {
    if (c.barcode.toLowerCase().includes(query) || c.cell_uid.toLowerCase().includes(query)) {
      results.push({ kind: 'cell', id: c.cell_uid, label: c.barcode, sublabel: c.celltype })
    }
  }
  return results.slice(0, 20)
}
