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

from pydantic import BaseModel

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


class GeneviewData(BaseModel):
    gene_id: str
    run_id: str
    span: GeneSpan | None
    window: dict[str, int | None]
    pas: list[GeneviewPas]
    findings: list[FindingRow]
    length_rows: list[LengthRow]
    gates: list[str]


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
