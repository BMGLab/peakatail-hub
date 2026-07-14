// In-memory mock fixtures. Field names/shapes match src/lib/contract/types.ts.
// Swap-out point: once the backend + packages/io land, lib/api/client.ts
// functions below get real fetch bodies instead of these fixtures.
import type {
  BenchmarkSummary,
  CellDetail,
  ConcordanceSummary,
  FindingRow,
  GeneSummary,
  GeneviewLayerData,
  LengthRow,
  PasDetail,
  RunQc,
  RunSummary,
  SearchResult,
  UmapPoint,
} from '@lib/contract/types'

export const mockRuns: RunSummary[] = [
  {
    run_id: 'run-laughney-2024-01',
    dataset_id: 'laughney_lung',
    label: 'Laughney lung adenocarcinoma (full cohort)',
    contract_version: '0.0.0-interim',
    created_at: '2026-06-01T00:00:00Z',
    n_samples: 12,
    n_cells: 48213,
    n_pas: 18422,
  },
  {
    run_id: 'run-laughney-2024-01-subset',
    dataset_id: 'laughney_lung_subset',
    label: 'Laughney lung adenocarcinoma (QC subset)',
    contract_version: '0.0.0-interim',
    created_at: '2026-05-15T00:00:00Z',
    n_samples: 3,
    n_cells: 6120,
    n_pas: 9310,
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
    pas_uid: `${gene.chrom}:${gene.start + i * 37}:${gene.strand}`,
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
    pas_uid: strategy === 'proportion' ? `${gene.chrom}:${gene.start + i * 41}:${gene.strand}` : null,
    gene_id: gene.gene_id,
    transcript_id: `${gene.gene_id}-T1`,
    strategy,
    cell_uid: `cell-${(i % 40).toString().padStart(4, '0')}`,
    canonical_cluster: clusters[i % clusters.length]!,
    value: seeded(i, 7) * 2 - 1,
    direction: strategy === 'proportion' ? lengthDirections[i % lengthDirections.length]! : null,
    rank: strategy === 'proportion' ? (i % 40) + 1 : null,
  }
})

export function mockPasForGene(geneId: string): PasDetail[] {
  const gene = genes.find((g) => g.gene_id === geneId)
  if (!gene) return []
  return Array.from({ length: gene.n_pas }, (_, i) => ({
    orig_pas_key: `orig-${geneId}-${i}`,
    chrom: gene.chrom,
    start: gene.start + i * 400,
    end: gene.start + i * 400 + 20,
    strand: gene.strand,
    unified_pas_id: `unified-${geneId}-${i}`,
    pas_uid: `${gene.chrom}:${gene.start + i * 400 + 10}:${gene.strand}`,
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
    stages: [
      { stage: 'raw_reads', n_pas: 42000, n_cells: 52000 },
      { stage: 'ip_filter', n_pas: 35100, n_cells: 52000 },
      { stage: 'annot_filter', n_pas: 28900, n_cells: 52000 },
      { stage: 'atlas_snap', n_pas: 22400, n_cells: 52000 },
      { stage: 'matrixfilter', n_pas: 20100, n_cells: 49800 },
      { stage: 'clustering', n_pas: 19300, n_cells: 48900 },
      { stage: 'switch_diff', n_pas: 18422, n_cells: 48213 },
    ],
    config_diff: {
      min_reads_per_pas: { resolved: 5, default: 3 },
      max_distance_bp: { resolved: 200, default: 100 },
    },
  },
}

export const mockConcordance: ConcordanceSummary[] = [
  { pair: 'fisher vs nb_pairwise', ari: 0.71, ami: 0.68 },
  { pair: 'fisher vs nb_multi', ari: 0.54, ami: 0.5 },
  { pair: 'nb_pairwise vs nb_multi', ari: 0.62, ami: 0.59 },
]

export const mockBenchmarks: BenchmarkSummary[] = [
  { name: 'atlas precision (raw)', metric: 'precision', value: 1.0, note: 'circular — see research_noatlas_findings' },
  { name: 'atlas precision (honest)', metric: 'precision', value: 0.25, note: 'de-duplicated against held-out atlas' },
  { name: 'peak-width confound', metric: 'spearman', value: 1.0, note: 'strategy ranking confounded by peak width' },
]

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
