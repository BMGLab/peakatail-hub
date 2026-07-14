"""Pydantic v2 models for the peakatail-contract schema.

These models are the ONLY thing the PeakATail engine and peakatail-hub agree
on (spec §7a "coupling ONLY by peakatail-contract"). Every field below is
grounded in one of:

* `PeakATail_Pipeline_IO_Reference.md` -- the real on-disk artifact columns.
* `PeakATail_Data_Controller_Design.md` -- the entity model, ledger spec,
  and bug list (B0-B7 / D1-D7) this contract must accommodate.
* `docs/2026-07-12-peakatail-hub-frontend-design.md` §7 -- the binding
  review resolutions that supersede the two docs above where they conflict.

Docstrings on individual fields cite the specific bug/section motivating
that field's existence, type, or nullability -- read them before changing a
field, the reasoning is load-bearing.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, computed_field

from peakatail_contract.ids import cell_uid as _mint_cell_uid
from peakatail_contract.ids import pas_uid as _mint_pas_uid


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


class Format(str, Enum):
    """Artifact serialization format (`PeakATail_Pipeline_IO_Reference.md` §1-4)."""

    BED = "bed"
    MTX = "mtx"
    TSV = "tsv"
    H5AD = "h5ad"
    PARQUET = "parquet"
    JSON = "json"


class Strategy(str, Enum):
    """`switch diff` differential-usage strategies (IO reference §3 "switch diff")."""

    FISHER = "fisher"
    NB_PAIRWISE = "nb_pairwise"
    NB_MULTI = "nb_multi"


class LengthStrategy(str, Enum):
    """`switch length` 3'UTR-shortening strategies (IO reference §3 "switch length").

    Each strategy has distinct *native* columns in the real TSVs
    (`pdui_classic.tsv`, `pdui_proportion.tsv`, `entropy_shannon.tsv`);
    :class:`LengthRow` normalizes all three into one row schema with this
    field as the discriminator.
    """

    CLASSIC = "classic"
    PROPORTION = "proportion"
    SHANNON = "shannon"


class Direction(str, Enum):
    """3'UTR usage-shift direction.

    Data Controller Design §5 (E5) is explicit that this must be an
    **exhaustive, non-nullable-in-spirit** enum -- ``undetermined`` is a
    first-class value, not a missing/None field -- because today's
    hand-built `switches_annotated.csv` computed direction ad hoc and
    silently dropped rows it couldn't classify (bug context: D8
    "direction/omnibus" correctness fix). Every :class:`FindingRow` MUST
    set one of these four values; never leave it absent.
    """

    SHORTEN = "shorten"
    LENGTHEN = "lengthen"
    FLAT = "flat"
    UNDETERMINED = "undetermined"


class Tier(str, Enum):
    """PAS-to-gene assignment confidence tier.

    Mirrors the exact string constants in `ema/annotate/find_close.py`
    (``TIER_1``/``TIER_2``/``TIER_3``/``INTERGENIC``) so ledger-writers can
    pass the engine's own values through unchanged. Per Data Controller
    Design §1/§2, this value is *computed then discarded* today (never
    written) -- the pas_ledger is what finally persists it.
    """

    TIER_1 = "TIER_1"  # within the known 3'UTR
    TIER_2 = "TIER_2"  # within UTR-length x utr_multiplier (possible extension)
    TIER_3 = "TIER_3"  # within max_gene_distance (possible novel distant PAS)
    INTERGENIC = "INTERGENIC"  # beyond max_gene_distance -- no gene assignment


# --------------------------------------------------------------------------
# Run manifest
# --------------------------------------------------------------------------


class DatasetRef(BaseModel):
    """One dataset (sample/replicate-group) registered in a run.

    ``label`` is the raw, human-authored stratum/sample label (e.g. as it
    appears in the config or an un-resolved output directory name). It is
    kept here for display/traceability ONLY. Callers minting IDs or joining
    across strata MUST resolve through ``RunManifest.stratum_to_label``
    instead -- ``label`` may be exactly the 48-char-truncated directory name
    the D10 bug produces, and is therefore unsafe as a join key.
    """

    dataset_id: str = Field(description="Stable dataset identifier (e.g. GSM/sample id).")
    bam_paths: list[str] = Field(
        default_factory=list,
        description="Absolute or run-relative paths to the (pooled, if merge_strategy=before) BAM(s).",
    )
    label: str | None = Field(
        default=None,
        description="Raw human-authored label; NOT safe for ID minting or joins (see stratum_to_label).",
    )


class Artifact(BaseModel):
    """One output artifact registered in the run manifest.

    Existence per Data Controller Design §5 (E2): "``run_manifest.json``:
    ``OutputManager.register_artifact()`` ... lists every artifact (path,
    stage, format, schema@version, entity counts)". This is what lets the
    hub indexer discover artifacts without hardcoding paths, and lets
    ``validate()`` check that required artifacts are present.
    """

    path: str = Field(description="Path to the artifact, relative to RunManifest.root unless absolute.")
    stage: str = Field(
        description=(
            "Producing pipeline stage, e.g. '01_peak_calling', '09_clustering', "
            "'switch_diff', 'switch_length'. Free-form (not an enum) because the "
            "engine's stage set is open-ended (IO reference §1/§4 NN_<stage> dirs)."
        )
    )
    format: Format
    schema_name: str = Field(
        description="Which contract schema this artifact conforms to, e.g. 'PasLedgerRow', 'clusters.h5ad'."
    )
    schema_version: str = Field(
        default="0.1.0",
        description="Schema version this artifact was written against (checked by validate()).",
    )
    entity_counts: dict[str, int] = Field(
        default_factory=dict,
        description="e.g. {'n_pas': 812, 'n_cells': 4213}. Used for the QC drop-funnel and validate() invariants.",
    )


class RunManifest(BaseModel):
    """The top-level, engine-written manifest for one pipeline run.

    This is THE artifact that lets the hub index a run dir without
    hardcoding paths (Data Controller Design §5 E2) and is the only source
    the hub may read the resolved config from (spec §7d: "Config-diff reads
    the resolved config from the E2 manifest, not run_config.json, which
    records argparse defaults -- B0").
    """

    run_id: str = Field(description="Unique identifier for this pipeline run.")
    root: str = Field(description="Absolute path to the run's output root directory.")
    contract_version: str = Field(
        default="0.1.0",
        description=(
            "Semver of peakatail-contract this manifest was written against. "
            "validate() rejects manifests whose major version differs from the "
            "installed peakatail_contract.CONTRACT_VERSION."
        ),
    )
    datasets: list[DatasetRef] = Field(default_factory=list)
    resolved_config: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "The FULLY RESOLVED RunConfig object (main.py:172), NOT argparse "
            "defaults (bug B0: run_config.json today serializes vars(args), so "
            "e.g. atlas=null even on snapped runs). This is the only config "
            "surface the hub's config-diff view may read."
        ),
    )
    stratum_to_label: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Maps an internal stratum/dataset key -> its full, untruncated "
            "label (celltype/stage/sample name). Fixes bug D10: output "
            "directory names are truncated to 48 chars by the filesystem, "
            "which silently merges distinct strata if used directly as a join "
            "key. finding_uid minting (ids.finding_uid) requires the resolved "
            "label from THIS map, never a raw directory name."
        ),
    )
    artifacts: list[Artifact] = Field(default_factory=list)
    entity_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Run-level totals, e.g. {'n_pas': 812, 'n_cells': 4213, 'n_genes': 1890, 'n_datasets': 2}.",
    )


# --------------------------------------------------------------------------
# Ledgers (Data Controller Design §2)
# --------------------------------------------------------------------------


class PasLedgerRow(BaseModel):
    """One row of the append-only PAS provenance ledger.

    Columns per Data Controller Design §2 exactly:
    ``orig_pas_key, chrom, start, end, strand, unified_pas_id,
    snap_distance_bp, gene_id, gene_distance_bp, tier, last_stage,
    dropped_at, drop_reason``.

    Buys the invariant (§2 + spec §5 testing): ``rows(pas_ledger where
    dropped_at == "") == n_vars(clusters.h5ad)`` -- see validate.py.
    """

    orig_pas_key: str = Field(
        description="Pre-unify, run-local PAS key as first minted by peak-calling, e.g. '<dataset_id>:<strand>:<raw_pas_id>'."
    )
    chrom: str
    start: int
    end: int
    strand: str = Field(description="'+' or '-'.")
    unified_pas_id: str = Field(
        description="Post-unify (atlas-snap or coordinate-merge) run-local id, e.g. the merged BED col4 value."
    )
    snap_distance_bp: int | None = Field(
        default=None,
        description=(
            "Distance (bp) to the atlas PAS this was snapped to, if the run used "
            "atlas snapping (D1). None when merge_strategy has no atlas, or when "
            "this PAS never got a hit in range (in which case dropped_at must be set)."
        ),
    )
    gene_id: str = Field(
        default="",
        description="Ensembl gene id assigned by PAS->gene distance join. Empty string if INTERGENIC (tier).",
    )
    gene_distance_bp: int | None = Field(
        default=None, description="Distance (bp) from this PAS to gene_id's 3' end, if assigned."
    )
    tier: Tier | None = Field(
        default=None,
        description="Confidence tier from PAS->gene assignment (D5); None only if not yet annotated.",
    )
    last_stage: str = Field(
        description="The last pipeline stage in which this PAS entity was observed alive."
    )
    dropped_at: str = Field(
        default="",
        description=(
            "Empty string if this PAS survived to clusters.h5ad. Otherwise the "
            "stage name where it was dropped (one of the 7 drop points D1-D7, "
            "e.g. 'atlas_snap', 'cb_filter', 'pas_gene_assignment', 'preprocess', "
            "'marker_subset'). NEVER left ambiguous between 'survived' and "
            "'we forgot to record'; always explicitly '' or a stage name."
        ),
    )
    drop_reason: str | None = Field(
        default=None, description="Human-readable reason, e.g. 'no atlas hit within atlas_distance=100'."
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pas_uid(self) -> str:
        """Content-addressed PAS id (`chrom:pos:strand`, strand-aware 3'-summit
        position -- NOT the raw `end` column), per ids.pas_uid / spec §7d.

        Exposed as a computed field (not a stored column) so it can never
        drift out of sync with chrom/start/end/strand -- it is *derived*, not
        independently settable. Formula aligned with engine-team's E1 message
        (2026-07-14): `pos = end - 1 if strand == "+" else start`.
        """
        return _mint_pas_uid(self.chrom, self.start, self.end, self.strand)


class CellLedgerRow(BaseModel):
    """One row of the append-only cell provenance ledger.

    Columns per Data Controller Design §2 exactly: ``barcode, dataset_id,
    total_reads, n_pas, dropped_at, drop_reason, cluster``.
    """

    barcode: str = Field(description="Raw cell barcode as read from the BAM barcode_tag (not yet namespaced).")
    dataset_id: str
    total_reads: int = Field(description="Total 3'-end reads observed for this barcode before any filtering.")
    n_pas: int = Field(
        description=(
            "Number of distinct PAS this cell has >=1 read at. NOTE (spec §7e): "
            "the real pipeline's clusters.h5ad stores this under "
            "obs['n_genes'], which is a scanpy-convention name left over from "
            "gene-expression data -- it is PAS-per-cell, NOT a gene count. This "
            "field is deliberately named n_pas to avoid re-propagating that "
            "mislabel into the contract."
        )
    )
    dropped_at: str = Field(
        default="",
        description="Empty string if this cell survived to clusters.h5ad; otherwise the stage where it was dropped (e.g. 'cb_filter' D4, 'preprocess' D6).",
    )
    drop_reason: str | None = Field(default=None)
    cluster: str | None = Field(
        default=None,
        description="Raw per-dataset leiden label (None if dropped before clustering). Not cross-sample comparable -- see cluster_uid / canonical_cluster.",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cell_uid(self) -> str:
        """Namespaced cell id (`dataset_id:barcode`), per ids.cell_uid."""
        return _mint_cell_uid(self.dataset_id, self.barcode)


# --------------------------------------------------------------------------
# Normalized long tables (Data Controller Design §5 E5)
# --------------------------------------------------------------------------


class FindingRow(BaseModel):
    """One row of `findings_long` -- the normalized target schema for engine
    stage E5, which does not exist in the engine yet; THIS MODEL DEFINES IT.

    Grounded in the real `switch diff` wide TSV columns (IO reference §3):
    ``pas_id, gene_id, chrom, start, end, strand, cluster1, cluster2,
    pvalue, qvalue, n_cells, n_cells_cluster1, n_cells_cluster2,
    n_reads_pas_cluster1, n_reads_pas_cluster2, odds_ratio,
    delta_proportion, log2fc`` -- reshaped to long format (one row per PAS x
    comparison x strategy), keyed by the minted ``pas_uid``/
    ``canonical_cluster`` (spec §7g), with ``direction`` added (never
    silently NA, Data Controller Design D8).

    Deliberately NOT included: ``chrom/start/end/strand``. Per spec §7d,
    coordinates must always be sourced from `pasbed.bed` / the pas ledger
    (join on ``pas_uid``), never duplicated onto a findings row -- that
    duplication is exactly how bug B4 (blank/stale coords in switch
    diff/length TSVs after a layout change) happened in the first place.
    """

    finding_uid: str = Field(description="Minted via ids.finding_uid(resolved_label, var_name, strategy, arm, pas_uid).")
    pas_uid: str = Field(description="Content-addressed PAS id; join key into PasLedgerRow for coordinates/tier/provenance.")
    gene_id: str = Field(description="Ensembl gene id, sourced from PasLedgerRow.gene_id (never var['gene_id'], B7).")
    canonical_cluster: str = Field(
        description=(
            "This row's subject cluster, cross-sample comparable (post-B6 "
            "canonical_cluster round-trip) -- never a raw per-sample leiden label."
        )
    )
    comparison_cluster: str | None = Field(
        default=None,
        description="The partner cluster for a pairwise comparison (fisher/nb_pairwise). None for nb_multi omnibus rows, which have no single partner.",
    )
    celltype: str | None = Field(
        default=None,
        description=(
            "GEX-derived cell type label, resolved via RunManifest.stratum_to_label "
            "(never a raw/truncated directory name, D10). Gated on roadmap item A1 "
            "(ema celltype does not exist yet, spec §7c); always None until then."
        ),
    )
    strategy: Strategy
    arm: str = Field(
        description="Analysis/arm identifier (Data Controller Design §4a 'Analysis(arm)'), e.g. a switch-diff run/config label.",
    )
    direction: Direction = Field(
        description="Never silently absent -- one of shorten/lengthen/flat/undetermined (D8/E5)."
    )
    utr_class: str | None = Field(
        default=None,
        description="Tandem UTR / alternative-last-exon / etc., from --isoform-agg per_isoform resolution. Gated on E5 landing; None until available.",
    )
    qvalue: float
    pvalue: float
    delta_proportion: float = Field(description="NOT 'delta_p' -- see research_stats_validity_bugs: this is a proportion delta, not a p-value delta.")
    log2fc: float | None = Field(default=None, description="NB-strategy log2 fold change; may be None for fisher rows that only report odds_ratio.")
    odds_ratio: float | None = Field(default=None, description="Fisher-strategy only; kept for parity with the real per-comparison TSV column.")
    n_cells: int = Field(description="Total cells tested across canonical_cluster (+ comparison_cluster if pairwise).")
    n_reads: int = Field(description="Total reads at this PAS across the cells tested.")
    n_cells_subject: int | None = Field(default=None, description="Cells in canonical_cluster specifically (parity with n_cells_cluster1/2).")
    n_cells_comparison: int | None = Field(default=None, description="Cells in comparison_cluster specifically, if pairwise.")
    n_reads_subject: int | None = Field(default=None, description="Reads at this PAS within canonical_cluster specifically.")
    n_reads_comparison: int | None = Field(default=None, description="Reads at this PAS within comparison_cluster specifically, if pairwise.")


class LengthRow(BaseModel):
    """One row of `length_long` -- the normalized target for the three
    `switch length` strategies, each of which has distinct native columns
    today (IO reference §3 "switch length"):

    * ``classic``: ``gene_id, transcript_id, cell, pdui, cluster``
    * ``proportion``: ``gene_id, transcript_id, pas_id, rank, cell, proportion, cluster``
    * ``shannon``: ``gene_id, cell, entropy, cluster``

    ``value`` holds pdui / proportion / entropy depending on ``strategy``.

    CORRECTED (2026-07-14, engine-team `ema/switch_test/long_output.py`):
    an earlier version of this docstring said only ``proportion`` carries a
    per-row ``direction`` -- that's now stale. Engine emits a REAL
    ``direction`` for ALL THREE strategies: a deterministic one-vs-rest
    per-(gene, canonical_cluster) structural call (this gene's distal usage
    in this cluster vs. the mean distal usage across the OTHER clusters in
    the same length output; sign of delta -> lengthen/shorten/flat,
    ``undetermined`` if the gene appears in <2 clusters or for ``shannon``,
    which has no polarity axis). ``pas_uid``/``rank`` remain populated only
    for ``proportion`` (the only strategy with a per-PAS row grain); that
    part of the original design still holds.
    """

    strategy: LengthStrategy
    gene_id: str
    transcript_id: str | None = Field(
        default=None,
        description=(
            "ENST id for classic/proportion. Deliberately None (not the pipeline's "
            "'_gene_' sentinel) when isoform-agg is per-gene mode -- Data Controller "
            "Design §1 notes the sentinel is fabricated, not a real transcript; the "
            "contract represents 'no specific isoform' as an explicit null instead."
        ),
    )
    cell_uid: str = Field(description="Namespaced cell id, minted via ids.cell_uid(dataset_id, barcode).")
    canonical_cluster: str = Field(description="Cross-sample comparable cluster label (post-B6), not a raw leiden label.")
    value: float = Field(description="pdui (classic) / proportion (proportion) / entropy (shannon), per `strategy`.")
    pas_uid: str | None = Field(default=None, description="Populated only for strategy='proportion' (per-PAS row).")
    rank: int | None = Field(default=None, description="Populated only for strategy='proportion' (PAS rank within gene/transcript, e.g. proximal=0).")
    direction: Direction | None = Field(
        default=None,
        description=(
            "Populated for ALL strategies (engine 2026-07-14): a deterministic "
            "one-vs-rest per-(gene, canonical_cluster) structural call -- this "
            "gene's distal usage in this cluster vs. the mean distal usage "
            "across the other clusters in the same length output. "
            "'classic': value IS the distal fraction (pdui), used directly. "
            "'proportion': distal PAS = max(rank) within the gene (proximal=0). "
            "'shannon': always 'undetermined' (no polarity axis). Still "
            "nullable in the type (Optional) for forward/backward tolerance "
            "with older engine outputs that predate this field being wired, "
            "but a conformant E5 writer should never actually leave it None."
        ),
    )
    direction_basis: str | None = Field(
        default=None,
        description=(
            "Informational provenance for `direction`'s methodology, e.g. "
            "'structural' (the one-vs-rest geometric call above) vs. a future "
            "'differential' (explicit pairwise subject-vs-named-reference-"
            "cluster mode, not yet implemented -- no reference-cluster "
            "convention is defined engine-side as of 2026-07-14). Surface this "
            "in the UI wherever direction is shown, per the caveat-flag "
            "philosophy (spec §7e) -- one-vs-rest and pairwise deltas are not "
            "the same claim and should not look interchangeable to an analyst."
        ),
    )
