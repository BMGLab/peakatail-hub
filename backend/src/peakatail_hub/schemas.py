"""Hub-owned pydantic response models.

Per the task brief ("reuse contract models directly where the shape
matches ... don't hand-roll parallel response schemas that can drift"):
`FindingRow`, `PasLedgerRow`, `CellLedgerRow`, and `LengthRow` from
`peakatail_contract` are used AS-IS as response models wherever a single row
of that exact shape is returned (see `api/findings.py` `/findings/{id}` ->
`FindingRow`, `api/pas.py` `/pas/{id}` -> `PasLedgerRow`, etc.).

Everything in this module is a genuinely hub-specific shape (aggregates,
pages, provenance trails, gate flags) that has no equivalent contract model
to drift from.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from peakatail_contract import CellLedgerRow, FindingRow, LengthRow, PasLedgerRow


class RunSummary(BaseModel):
    run_id: str
    root: str
    contract_version: str
    resolved_config: dict[str, Any]
    stratum_to_label: dict[str, str]
    n_pas: int | None = None
    n_cells: int | None = None
    n_genes: int | None = None
    n_datasets: int | None = None
    n_findings: int | None = None
    n_length_rows: int | None = None
    indexed_at: str | None = None
    # Which registered SOURCES directory (api/sources.py) this run was last
    # (re)discovered under. NULL for runs indexed before the sources feature
    # existed, or via the bare `hub index <dir>` CLI outside any registered
    # source -- a legitimate "unattributed" state, not an error.
    source_id: str | None = None
    source_path: str | None = None
    source_label: str | None = None
    # Distinct non-null `celltype` values across this run's findings_long
    # rows -- shown on the dashboard's per-run card. None (not 0) when the
    # run has zero findings rows at all vs. genuinely zero celltypes seen.
    n_celltypes: int | None = None
    # Whether this run has ANY atlas-snap provenance (index/indexer.py::
    # _atlas_snap_available) -- False on `reannotate` runs (no snap step of
    # their own), which the PAS browser uses to render an honest
    # "N/A (no atlas-snap step)" for the whole snap_distance_bp column
    # instead of a per-row dash indistinguishable from broken data. None
    # only for a run indexed before this flag existed.
    atlas_snap_available: bool | None = None


class SourceSummary(BaseModel):
    source_id: str
    path: str
    label: str | None = None
    added_at: str
    last_scanned_at: str | None = None
    # 'ok' = scanned, zero failures. 'empty' = scanned, zero run_manifest.json
    # found anywhere under path. 'error' = at least one run under this path
    # failed indexing (see last_scan_error). None = registered but never
    # scanned yet (should not normally happen -- POST /sources scans inline).
    last_scan_status: str | None = None
    last_scan_error: str | None = None
    run_count: int = 0


class SourceScanReport(BaseModel):
    indexed: list[str]
    skipped_unchanged: list[str]
    failed: dict[str, str]


class SourceScanResponse(BaseModel):
    source: SourceSummary
    scan: SourceScanReport


class SourceRescanAllResponse(BaseModel):
    sources: list[SourceScanResponse]


class QcStageStat(BaseModel):
    stage: str
    dropped: int


class QcFunnel(BaseModel):
    run_id: str
    n_pas_total: int
    n_pas_survived: int
    n_cells_total: int
    n_cells_survived: int
    pas_drop_by_stage: list[QcStageStat]
    cell_drop_by_stage: list[QcStageStat]
    per_sample_stats_available: bool
    gate_note: str


class FindingsPage(BaseModel):
    items: list[FindingRow]
    next_cursor: str | None
    total: int


class FacetValue(BaseModel):
    value: str | None
    count: int


class FindingsFacets(BaseModel):
    arm: list[FacetValue]
    strategy: list[FacetValue]
    celltype: list[FacetValue]
    direction: list[FacetValue]
    utr_class: list[FacetValue]
    total: int


class GeneSpan(BaseModel):
    chrom: str
    start: int
    end: int
    strand: str
    n_pas: int


class GeneSummary(BaseModel):
    gene_id: str
    run_id: str
    n_pas: int
    n_findings: int
    n_length_rows: int
    span: GeneSpan | None
    # Human-readable gene symbol resolved from the run's GTF (e.g. "TESTA1"
    # / a real symbol like "CLIC2"), NOT a contract/ledger column -- the
    # ledger only ever carries the Ensembl-style `gene_id`. Empty string
    # when no `gtf_dir` is configured for this run, the GTF is missing/
    # unreadable, or the gene simply isn't in it -- never raises (a GTF is
    # optional context for display, not required for correctness).
    gene_name: str = ""


class GeneListRow(BaseModel):
    """One row of `GET /genes` (the gene browser). Deliberately NOT
    `GeneSummary` -- that's a single-gene detail fetch with `n_length_rows`/
    `run_id` a list row has no use for; this is the lighter aggregate shape
    `queries.list_genes` returns for a page of many genes at once.
    """

    gene_id: str
    chrom: str | None
    start: int | None
    end: int | None
    strand: str | None
    n_pas: int
    n_findings: int


class GenesPage(BaseModel):
    items: list[GeneListRow]
    next_cursor: str | None
    total: int


class PasPage(BaseModel):
    """`GET /pas` (the PAS browser) -- full ledger rows (survived + dropped
    alike, see `queries.list_pas`), paginated the same way `/findings` is.
    """

    items: list[PasLedgerRow]
    next_cursor: str | None
    total: int


class CellsPage(BaseModel):
    """`GET /cells` (the cell browser) -- full ledger rows, same pagination
    shape as `PasPage`/`FindingsPage`.
    """

    items: list[CellLedgerRow]
    next_cursor: str | None
    total: int


class GeneviewPas(BaseModel):
    pas_uid: str
    chrom: str
    start: int
    end: int
    strand: str
    unified_pas_id: str
    gene_distance_bp: int | None
    snap_distance_bp: int | None
    tier: str | None


class GeneviewIsoform(BaseModel):
    """One transcript's exon structure, as parsed from the run's GTF by
    `peakatail_hub.gtf.load_isoforms`. `exons` are BED-style half-open
    `(start, end)` pairs (converted from the GTF's 1-based closed interval
    at parse time -- see that module's docstring), sorted ascending by
    coordinate, NOT necessarily in transcription order (the frontend, which
    already knows the gene's strand from `GeneSpan.strand`, is responsible
    for any 5'->3' reordering it wants for display).
    """

    transcript_id: str
    exons: list[tuple[int, int]]


class GeneviewClusterValue(BaseModel):
    """One PAS's usage within one cluster. Always paired positionally with
    `GeneviewData.pas` (same index, same order) -- see
    `GeneviewClusterTrack.values` docstring for why no `pas_uid` lookup is
    needed on the frontend side even though it's carried here too, for
    self-description / debugging.
    """

    pas_uid: str
    reads_per_cell: float
    # None (not NaN -- NaN isn't valid JSON) when this cluster had zero
    # reads across every PAS of this gene, mirroring the matplotlib
    # reference's `np.where(row_totals > 0, reads / row_totals, np.nan)`
    # (ema/viz/_gene_track_helpers.py::build_gene_panel).
    proportion: float | None


class GeneviewClusterTrack(BaseModel):
    """Per-cluster PAS usage, one track per `canonical_cluster` present in
    this gene's surviving PAS x clusters.h5ad subset. Computed once from a
    single `open_clusters_h5ad()` + subset (never per-PAS-per-cluster
    re-reads -- see `geneview_data()`'s docstring for why that would be
    wasteful).
    """

    cluster: str
    n_cells: int
    # Same length and same order as `GeneviewData.pas` -- callers may zip
    # `pas` and `values` positionally rather than joining on `pas_uid`.
    values: list[GeneviewClusterValue] = Field(default_factory=list)


class GeneviewData(BaseModel):
    gene_id: str
    run_id: str
    span: GeneSpan | None
    window: dict[str, int | None]
    pas: list[GeneviewPas]
    findings: list[FindingRow]
    length_rows: list[LengthRow]
    gates: list[str]
    # See GeneSummary.gene_name docstring -- same GTF-derived, best-effort,
    # never-raises semantics.
    gene_name: str = ""
    # Gene structure (isoforms/exons) for the gene-track panel, from the
    # run's GTF. Empty when no GTF is configured/found/matches -- the
    # frontend degrades to drawing the PAS/coverage tracks without a gene
    # model above them.
    isoforms: list[GeneviewIsoform] = Field(default_factory=list)
    # Per-cluster PAS usage for the coverage/proportion tracks -- see
    # `GeneviewClusterTrack`. Empty when clusters.h5ad is unavailable/
    # unreadable for this run, or the gene has zero surviving PAS -- this
    # endpoint degrades gracefully rather than 500ing (see `geneview_data()`
    # docstring).
    cluster_tracks: list[GeneviewClusterTrack] = Field(default_factory=list)


class PasProvenance(BaseModel):
    pas: PasLedgerRow
    findings: list[FindingRow]
    length_rows: list[dict[str, Any]]
    trail: list[str]


class CellProvenance(BaseModel):
    cell: CellLedgerRow
    length_rows: list[dict[str, Any]]
    trail: list[str]


class UmapPoint(BaseModel):
    cell_uid: str
    dataset_id: str | None
    x: float | None
    y: float | None
    leiden: str | None
    canonical_cluster: str | None
    celltype: str | None
    stage: str | None
    sample: str | None


class UmapResponse(BaseModel):
    run_id: str
    color: str
    n_points: int
    points: list[UmapPoint]


class UmapNotAvailable(BaseModel):
    available: bool = False
    color: str
    gate: str


class SearchResults(BaseModel):
    q: str
    genes: list[dict[str, Any]]
    pas: list[PasLedgerRow]
    cells: list[CellLedgerRow]


class StubResponse(BaseModel):
    run_id: str
    available: bool
    note: str


class RunDataset(BaseModel):
    """One dataset (07_clustering/<dataset_id>/clusters.h5ad) indexed for a
    run -- see `queries.list_run_datasets`. A run's `n_datasets` header stat
    is a single aggregate count; this is the per-dataset identity behind it.
    """

    dataset_id: str
    n_cells: int
    n_clusters: int


class SwitchLengthAvailability(BaseModel):
    file_size_bytes: int | None = None


class SwitchTrend(BaseModel):
    n_stages: int | None = None
    slope: float | None = None
    spearman: float | None = None
    direction: str | None = None
    value_col: str | None = None
    mean_by_stage: dict[str, float] = Field(default_factory=dict)


class SwitchCelltypeResult(BaseModel):
    """One celltype's B3_switch results within a run: diff (finding counts
    per strategy, already queryable in full via `/findings?arm=switch_diff:...`),
    length (availability only -- see `switch_availability` table docstring),
    and trend (the fully-ingested length-across-stages headline).
    """

    celltype: str
    diff: dict[str, int] = Field(default_factory=dict)
    length: dict[str, SwitchLengthAvailability] = Field(default_factory=dict)
    trend: SwitchTrend | None = None


class ClusterMatchAvailability(BaseModel):
    file_path: str | None = None
    file_size_bytes: int | None = None


class SwitchResults(BaseModel):
    """`GET /runs/{run_id}/switch` -- the run's B3_switch results, modeled
    truthfully as "many results per run" (task brief item 4) rather than a
    single findings table. Empty `celltypes` (not an error) for a run with
    no B3_switch directory at all (e.g. a single-dataset `reannotate` run).
    """

    run_id: str
    celltypes: list[SwitchCelltypeResult] = Field(default_factory=list)
    cluster_match: ClusterMatchAvailability | None = None


class SwitchTrendGene(BaseModel):
    gene_id: str
    n_stages: int | None = None
    slope: float | None = None
    spearman: float | None = None
    direction: str | None = None


class GeneviewPasDistanceRow(BaseModel):
    """One row of the PAS-distance table `ema switch geneview
    --pas-distance-table` draws beneath the gene panel (both engines) and
    writes alongside the figure as `gene_<id>_pas_distances.csv` -- see
    `geneview-worker/geneview_worker.py`. Exposed here too (not just baked
    into the image/html) so the hub view can show it as a real, readable
    table rather than relying on the user squinting at a rendered figure.
    """

    rank: int
    pas_id: str
    chrom: str
    strand: str
    start: int
    end: int
    width_bp: int
    summit_pos: int
    gap_to_next_bp: int | None = None
    summit_dist_to_next_bp: int | None = None


class GeneviewRender(BaseModel):
    """`GET /genes/{gene_id}/geneview/meta` -- the real ema-generated
    geneview's metadata + PAS-distance table, alongside the `.html`/`.png`
    figure endpoints. Replaces the old hand-rolled `GeneviewData` (custom
    IGV-style track fields: `pas`/`isoforms`/`cluster_tracks`) entirely --
    see the 2026-08-14 "real ema geneview" fix.
    """

    gene_id: str
    gene_name: str = ""
    run_id: str
    dataset_id: str
    cluster_key: str
    chrom: str | None = None
    start: int | None = None
    end: int | None = None
    strand: str | None = None
    n_pas: int | None = None
    n_clusters_rendered: int | None = None
    n_isoforms: int | None = None
    cached: bool
    duration_sec: float
    pas_distances: list[GeneviewPasDistanceRow] = Field(default_factory=list)
