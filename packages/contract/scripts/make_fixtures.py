#!/usr/bin/env python3
"""Generate the complete fixture run under packages/contract/fixtures/.

Per spec §7b, this fixture is step 1 for the whole hub: every hub feature
(indexer, DuckDB store, all endpoints, all six views, the geneview renderer)
builds and tests against this fixture in parallel with the engine work.

Requires the `test` extra (anndata, h5py, pyarrow, pandas, numpy) -- these
are NOT runtime deps of peakatail_contract itself (spec §7a), which is why
this generator lives in scripts/ rather than in the importable package.

Usage (from packages/contract/):
    uv pip install -e ".[test]"
    uv run python scripts/make_fixtures.py

Regenerate whenever the model schemas or fixture data intentionally change;
commit the resulting fixture files (they are small).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the src/ package importable without installing, so this also works
# from a bare checkout before `pip install -e .`.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import numpy as np
import pandas as pd

from peakatail_contract import CONTRACT_VERSION
from peakatail_contract.ids import cell_uid, cluster_uid, finding_uid, pas_uid
from peakatail_contract.models import (
    Artifact,
    CellLedgerRow,
    DatasetRef,
    Direction,
    FindingRow,
    Format,
    LengthRow,
    LengthStrategy,
    PasLedgerRow,
    RunManifest,
    Strategy,
    Tier,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"

RUN_ID = "fixture-run-0001"
DATASETS = ["ds1", "ds2"]

# ---------------------------------------------------------------------
# PAS ledger: 6 rows, 4 survivors (matches clusters.h5ad n_vars=4 exactly,
# satisfying the core invariant). 2 genes x 2 PAS each (proximal/distal,
# i.e. a tandem-UTR pair) survive; 2 more PAS are dropped at two different
# real drop points (D1 atlas_snap, D5 pas_gene_assignment) to exercise the
# ledger's provenance columns.
# ---------------------------------------------------------------------
GENE_1 = "ENSG00000000001"
GENE_2 = "ENSG00000000002"

_PAS_SPECS = [
    # (chrom, start, end, strand, gene_id, gene_distance_bp, tier, dropped_at, drop_reason, snap_distance_bp)
    ("chr1", 999, 1000, "+", GENE_1, 50, Tier.TIER_1, "", None, 12),
    ("chr1", 1499, 1500, "+", GENE_1, 550, Tier.TIER_2, "", None, 8),
    ("chr2", 4999, 5000, "-", GENE_2, 30, Tier.TIER_1, "", None, 5),
    ("chr2", 5399, 5400, "-", GENE_2, 430, Tier.TIER_2, "", None, 15),
    ("chr3", 9999, 10000, "+", "", None, None, "atlas_snap", "no atlas hit within atlas_distance=100", None),
    ("chr1", 17999, 18000, "+", "", 8000, Tier.INTERGENIC, "pas_gene_assignment", "distance 8000bp > max_gene_distance=5000", 20),
]

pas_ledger_rows: list[PasLedgerRow] = []
for i, (chrom, start, end, strand, gene_id, gdist, tier, dropped_at, reason, snap_dist) in enumerate(_PAS_SPECS):
    pas_ledger_rows.append(
        PasLedgerRow(
            orig_pas_key=f"ds1:{strand}:{i + 1}",
            chrom=chrom,
            start=start,
            end=end,
            strand=strand,
            unified_pas_id=f"unified_{i + 1}",
            snap_distance_bp=snap_dist,
            gene_id=gene_id,
            gene_distance_bp=gdist,
            tier=tier,
            last_stage="clustering" if dropped_at == "" else dropped_at,
            dropped_at=dropped_at,
            drop_reason=reason,
        )
    )

SURVIVING_PAS = [r for r in pas_ledger_rows if r.dropped_at == ""]
assert len(SURVIVING_PAS) == 4, "fixture must keep exactly 4 surviving PAS to match clusters.h5ad n_vars"

# ---------------------------------------------------------------------
# Cell ledger: 7 rows, 6 survivors across 2 datasets x 3 cells, 1 dropped
# at cb_filter (D4) -- matches clusters.h5ad n_obs=6.
# ---------------------------------------------------------------------
_CELL_SPECS = [
    # (dataset_id, barcode, total_reads, n_pas, dropped_at, drop_reason, leiden)
    ("ds1", "AAACCCAAGT", 512, 4, "", None, "0"),
    ("ds1", "AAACCCAAGC", 480, 4, "", None, "0"),
    ("ds1", "AAACCCAAGG", 390, 3, "", None, "1"),
    ("ds2", "TTTGTTGGTA", 470, 4, "", None, "0"),
    ("ds2", "TTTGTTGGTC", 505, 4, "", None, "1"),
    ("ds2", "TTTGTTGGTG", 415, 3, "", None, "1"),
    ("ds1", "AAACCCAAGA", 8, 1, "cb_filter", "total_reads=8 < min_read=50", None),
]

cell_ledger_rows: list[CellLedgerRow] = [
    CellLedgerRow(
        barcode=barcode,
        dataset_id=ds,
        total_reads=reads,
        n_pas=n_pas,
        dropped_at=dropped_at,
        drop_reason=reason,
        cluster=leiden,
    )
    for ds, barcode, reads, n_pas, dropped_at, reason, leiden in _CELL_SPECS
]

SURVIVING_CELLS = [r for r in cell_ledger_rows if r.dropped_at == ""]
assert len(SURVIVING_CELLS) == 6, "fixture must keep exactly 6 surviving cells to match clusters.h5ad n_obs"

# canonical_cluster mapping: leiden "0" -> "cl_A", leiden "1" -> "cl_B" in
# BOTH datasets (this is the cross-dataset alignment bug B6 is meant to fix
# -- the fixture demonstrates the post-fix state).
_LEIDEN_TO_CANONICAL = {"0": "cl_A", "1": "cl_B"}


def _canonical_for(dataset_id: str, leiden: str) -> str:
    return _LEIDEN_TO_CANONICAL[leiden]


# ---------------------------------------------------------------------
# findings_long: a handful of rows spanning all 3 strategies, all 4
# directions, referencing real surviving pas_uids.
# ---------------------------------------------------------------------
STRATUM_LABEL = "TCell_activated"  # the manifest-resolved (untruncated) label
ARM = "cl_A_vs_cl_B"

_FINDING_SPECS = [
    # (pas_row_index_in_SURVIVING_PAS, strategy, direction, qvalue, pvalue, delta_proportion, log2fc, odds_ratio)
    (0, Strategy.FISHER, Direction.SHORTEN, 0.01, 0.001, 0.35, 1.2, 2.1),
    (1, Strategy.FISHER, Direction.LENGTHEN, 0.02, 0.004, -0.28, -0.9, 0.6),
    (2, Strategy.NB_PAIRWISE, Direction.FLAT, 0.8, 0.6, 0.02, 0.05, None),
    (3, Strategy.NB_MULTI, Direction.UNDETERMINED, 0.15, 0.09, 0.10, None, None),
]

finding_rows: list[FindingRow] = []
for pas_idx, strategy, direction, qval, pval, dprop, log2fc, odds in _FINDING_SPECS:
    pas_row = SURVIVING_PAS[pas_idx]
    puid = pas_row.pas_uid
    gene = pas_row.gene_id
    # var_names in clusters.h5ad == unified_pas_id (see README "fixture var_names
    # convention") -- deliberately NOT pas_uid itself, since pas_uid contains ':'
    # and var_name here must not (see ids.finding_uid docstring).
    var_name = pas_row.unified_pas_id
    fuid = finding_uid(
        resolved_label=STRATUM_LABEL,
        var_name=var_name,
        strategy=strategy.value,
        arm=ARM,
        pas_uid_value=puid,
    )
    comparison_cluster = "cl_B" if strategy != Strategy.NB_MULTI else None
    finding_rows.append(
        FindingRow(
            finding_uid=fuid,
            pas_uid=puid,
            gene_id=gene,
            canonical_cluster="cl_A",
            comparison_cluster=comparison_cluster,
            celltype=STRATUM_LABEL,
            strategy=strategy,
            arm=ARM,
            direction=direction,
            utr_class="tandem_utr",
            qvalue=qval,
            pvalue=pval,
            delta_proportion=dprop,
            log2fc=log2fc,
            odds_ratio=odds,
            n_cells=6,
            n_reads=250,
            n_cells_subject=3,
            n_cells_comparison=3 if comparison_cluster else None,
            n_reads_subject=130,
            n_reads_comparison=120 if comparison_cluster else None,
        )
    )

# ---------------------------------------------------------------------
# length_long: classic + proportion + shannon rows over the surviving cells
# and genes; proportion rows carry pas_uid/rank/direction.
# ---------------------------------------------------------------------
length_rows: list[LengthRow] = []
for ds, barcode, *_rest, leiden in _CELL_SPECS:
    if leiden is None:
        continue  # dropped cell, not in clusters.h5ad
    c_uid = cell_uid(ds, barcode)
    canon = _canonical_for(ds, leiden)
    # classic: one row per gene per cell. Engine (2026-07-14) now emits a
    # REAL direction for classic too: one-vs-rest structural call, value
    # (pdui = distal fraction) used directly -- cl_A's 0.62 > cl_B's 0.41
    # (the "rest"), so cl_A is relatively LENGTHENED and cl_B relatively
    # SHORTENED. See LengthRow.direction docstring.
    for gene in (GENE_1, GENE_2):
        length_rows.append(
            LengthRow(
                strategy=LengthStrategy.CLASSIC,
                gene_id=gene,
                transcript_id=f"{gene.replace('ENSG', 'ENST')}",
                cell_uid=c_uid,
                canonical_cluster=canon,
                value=0.62 if canon == "cl_A" else 0.41,
                direction=Direction.LENGTHEN if canon == "cl_A" else Direction.SHORTEN,
                direction_basis="structural",
            )
        )
    # shannon: one row per cell (gene-agnostic entropy over all its PAS).
    # Engine: shannon has no polarity axis -> direction is ALWAYS
    # 'undetermined' (never None -- see LengthRow.direction docstring).
    length_rows.append(
        LengthRow(
            strategy=LengthStrategy.SHANNON,
            gene_id=GENE_1,
            cell_uid=c_uid,
            canonical_cluster=canon,
            value=0.87 if canon == "cl_A" else 0.55,
            direction=Direction.UNDETERMINED,
            direction_basis="structural",
        )
    )
    # proportion: one row per surviving PAS for GENE_1, per cell
    gene1_pas = [r for r in SURVIVING_PAS if r.gene_id == GENE_1]
    for rank, pas_row in enumerate(sorted(gene1_pas, key=lambda r: r.end)):
        length_rows.append(
            LengthRow(
                strategy=LengthStrategy.PROPORTION,
                gene_id=GENE_1,
                transcript_id=GENE_1.replace("ENSG", "ENST"),
                cell_uid=c_uid,
                canonical_cluster=canon,
                value=0.7 if rank == 0 else 0.3,
                pas_uid=pas_row.pas_uid,
                rank=rank,
                direction=Direction.SHORTEN if canon == "cl_A" else Direction.LENGTHEN,
                direction_basis="structural",
            )
        )


def _write_pas_ledger_tsv(path: Path) -> None:
    df = pd.DataFrame([r.model_dump(mode="json") for r in pas_ledger_rows])
    df["tier"] = df["tier"].fillna("")
    df["pas_uid"] = [r.pas_uid for r in pas_ledger_rows]
    df.to_csv(path, sep="\t", index=False)


def _write_cell_ledger_tsv(path: Path) -> None:
    df = pd.DataFrame([r.model_dump(mode="json") for r in cell_ledger_rows])
    df["cell_uid"] = [r.cell_uid for r in cell_ledger_rows]
    df.to_csv(path, sep="\t", index=False)


def _write_findings_parquet(path: Path) -> None:
    # mode="json" serializes enums to their plain .value string.
    rows = [r.model_dump(mode="json") for r in finding_rows]
    pd.DataFrame(rows).to_parquet(path, index=False)


def _write_length_parquet(path: Path) -> None:
    rows = [r.model_dump(mode="json") for r in length_rows]
    pd.DataFrame(rows).to_parquet(path, index=False)


def _write_pasbed(path: Path) -> None:
    lines = []
    for i, r in enumerate(SURVIVING_PAS):
        lines.append(f"{r.chrom}\t{r.start}\t{r.end}\t{i + 1}\t0\t{r.strand}")
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------
# genes.gtf: gene models for GENE_1/GENE_2, hand-chosen so every surviving
# PAS above falls inside the terminal exon of at least one isoform --
# mirroring a real tandem-3'UTR gene (a short/proximal isoform whose
# terminal exon ends at the proximal PAS, and a long/distal isoform whose
# terminal exon spans both PAS). This is the exact shape
# `peakatail_hub.gtf.load_isoforms()` / the geneview gene-structure track
# is meant to render. Coordinates are 1-based, closed-interval (standard
# GTF convention) -- the reader converts to BED half-open at parse time,
# not here.
# ---------------------------------------------------------------------
_GENE_MODELS: list[tuple[str, str, str, str, list[tuple[str, list[tuple[int, int]]]]]] = [
    (
        GENE_1,
        "TESTA1",
        "chr1",
        "+",
        [
            # long/distal isoform: terminal exon 951-1500 covers BOTH PAS
            # (chr1:999-1000 and chr1:1499-1500).
            ("ENST00000000001", [(851, 900), (951, 1500)]),
            # short/proximal isoform: terminal exon 951-1000 covers only
            # the proximal PAS (chr1:999-1000).
            ("ENST00000000002", [(851, 900), (951, 1000)]),
        ],
    ),
    (
        GENE_2,
        "TESTB2",
        "chr2",
        "-",
        [
            # long/distal isoform (minus strand: the terminal/3'-most exon
            # in transcription order is the LOWER-coordinate one): exon
            # 5000-5400 covers BOTH PAS (chr2:4999-5000 and chr2:5399-5400).
            ("ENST00000000003", [(5000, 5400), (5451, 5500)]),
            # short/proximal isoform: terminal exon 5351-5400 covers only
            # chr2:5399-5400.
            ("ENST00000000004", [(5351, 5400), (5451, 5500)]),
        ],
    ),
]


def _write_gtf(path: Path) -> None:
    """Write the fixture GTF (`genes.gtf`): standard 9-column, tab-separated,
    1-based inclusive coordinates, `gene`/`transcript`/`exon` feature rows
    with `gene_id`/`gene_name`/`transcript_id` attributes. Only `exon` rows
    are actually parsed by `peakatail_hub.gtf.load_isoforms` (feature_type
    defaults to "exon"); `gene`/`transcript` rows are included purely for
    realism, matching what a real Ensembl/GENCODE GTF looks like.

    Regenerate via `uv run python scripts/make_fixtures.py` from
    packages/contract/ whenever `_GENE_MODELS` above changes -- this
    function is the single source of truth for `fixtures/genes.gtf`.
    """
    lines = ["# PeakATail hub fixture GTF -- generated by make_fixtures.py::_write_gtf, do not hand-edit"]
    for gene_id, gene_name, chrom, strand, transcripts in _GENE_MODELS:
        all_exons = [exon for _, exons in transcripts for exon in exons]
        g_start = min(e[0] for e in all_exons)
        g_end = max(e[1] for e in all_exons)
        gene_attrs = f'gene_id "{gene_id}"; gene_name "{gene_name}";'
        lines.append(f"{chrom}\tfixture\tgene\t{g_start}\t{g_end}\t.\t{strand}\t.\t{gene_attrs}")
        for transcript_id, exons in transcripts:
            t_start = min(e[0] for e in exons)
            t_end = max(e[1] for e in exons)
            t_attrs = f'gene_id "{gene_id}"; gene_name "{gene_name}"; transcript_id "{transcript_id}";'
            lines.append(f"{chrom}\tfixture\ttranscript\t{t_start}\t{t_end}\t.\t{strand}\t.\t{t_attrs}")
            for exon_start, exon_end in exons:
                lines.append(f"{chrom}\tfixture\texon\t{exon_start}\t{exon_end}\t.\t{strand}\t.\t{t_attrs}")
    path.write_text("\n".join(lines) + "\n")


def _write_clusters_h5ad(path: Path) -> None:
    import anndata as ad

    n_obs = len(SURVIVING_CELLS)
    n_vars = len(SURVIVING_PAS)
    rng = np.random.default_rng(0)
    # Dense array (fixture is tiny) -- avoids adding scipy as an explicit
    # test-extra dep; anndata itself is happy with a plain ndarray here.
    X = rng.poisson(2.0, size=(n_obs, n_vars)).astype(np.float32)

    obs = pd.DataFrame(
        {
            "dataset_id": [r.dataset_id for r in SURVIVING_CELLS],
            "barcode": [r.barcode for r in SURVIVING_CELLS],
            "leiden": [r.cluster for r in SURVIVING_CELLS],
            "canonical_cluster": [_canonical_for(r.dataset_id, r.cluster) for r in SURVIVING_CELLS],
            "n_genes": [r.n_pas for r in SURVIVING_CELLS],  # NOTE: PAS count, see §7e caveat
            "total_counts": [r.total_reads for r in SURVIVING_CELLS],
        },
        index=[cell_uid(r.dataset_id, r.barcode) for r in SURVIVING_CELLS],
    )
    var = pd.DataFrame(
        {
            "gene_id": [r.gene_id if rng.random() > 0.3 else None for r in SURVIVING_PAS],  # simulate B7 NaNs on purpose
            "chrom": [r.chrom for r in SURVIVING_PAS],
            "end": [r.end for r in SURVIVING_PAS],
            "strand": [r.strand for r in SURVIVING_PAS],
        },
        # var_names = unified_pas_id (a stable, colon-free per-PAS token distinct
        # from pas_uid) -- exercises spec §7d "join on var_names, never
        # var['gene_id']" without conflating var_names with pas_uid syntax.
        # The fixture's var['gene_id'] column deliberately has holes (B7) to
        # exercise that exact defense in tests; readers must reconcile
        # var_names -> pas_uid via the PAS ledger (unified_pas_id), not by
        # string equality.
        index=[r.unified_pas_id for r in SURVIVING_PAS],
    )
    umap = rng.normal(size=(n_obs, 2)).astype(np.float32)

    adata = ad.AnnData(X=X, obs=obs, var=var)
    adata.obsm["X_umap"] = umap
    adata.write_h5ad(path)


def _write_run_manifest(path: Path, artifact_paths: dict[str, Path]) -> None:
    manifest = RunManifest(
        run_id=RUN_ID,
        root=str(FIXTURES_DIR),
        contract_version=CONTRACT_VERSION,
        datasets=[
            DatasetRef(dataset_id="ds1", bam_paths=["ds1.bam"], label="Dataset 1 (T cell, activated) [truncated-example]"),
            DatasetRef(dataset_id="ds2", bam_paths=["ds2.bam"], label="Dataset 2 (T cell, activated) [truncated-example]"),
        ],
        # Nested {directories, variables, filters, args} shape -- matches
        # engine's ema/outputs.py::build_resolved_run_config() (B0 fix)
        # exactly, not a flat dict. This is what real runs actually emit
        # into run_manifest.json's resolved_config; the hub's config-diff
        # view (spec §7d) reads THIS shape, never run_config.json's
        # argparse-defaults shape (the B0 bug). Keeping the fixture
        # structurally aligned means that view gets exercised correctly
        # against fixtures rather than only against real runs.
        resolved_config={
            "directories": {
                "output_dir": str(FIXTURES_DIR),
                "bam_dir": None,
                "gtf_dir": "genes.gtf",
                "atlas": None,
                "atlas_distance": None,
                "datasets": [
                    {"id": "ds1", "bams": ["ds1.bam"]},
                    {"id": "ds2", "bams": ["ds2.bam"]},
                ],
                "filenames": {},
            },
            "variables": {
                "seqlen": 100,
                "cb_len": 16,
                "barcode_tag": "CB",
                "default_threshold": 0.05,
                "merge_len": 24,
                "min_pas_spacing": 10,
                "min_pas_prominence": 2,
            },
            "filters": {
                "min_read": 50,
                "min_cells": 2,
                "min_genes": None,
                "min_pas_per_cell": 2,
            },
            "args": {
                "merge_strategy": "before",
                "max_gene_distance": 5000,
            },
        },
        stratum_to_label={"ds1": STRATUM_LABEL, "ds2": STRATUM_LABEL},
        artifacts=[
            Artifact(
                path=str(artifact_paths["pas_ledger"].relative_to(FIXTURES_DIR)),
                stage="provenance",
                format=Format.TSV,
                schema_name="PasLedgerRow",
                schema_version=CONTRACT_VERSION,
                entity_counts={"n_rows": len(pas_ledger_rows), "n_surviving": len(SURVIVING_PAS)},
            ),
            Artifact(
                path=str(artifact_paths["cell_ledger"].relative_to(FIXTURES_DIR)),
                stage="provenance",
                format=Format.TSV,
                schema_name="CellLedgerRow",
                schema_version=CONTRACT_VERSION,
                entity_counts={"n_rows": len(cell_ledger_rows), "n_surviving": len(SURVIVING_CELLS)},
            ),
            Artifact(
                path=str(artifact_paths["findings"].relative_to(FIXTURES_DIR)),
                stage="switch_diff",
                format=Format.PARQUET,
                schema_name="FindingRow",
                schema_version=CONTRACT_VERSION,
                entity_counts={"n_rows": len(finding_rows)},
            ),
            Artifact(
                path=str(artifact_paths["length"].relative_to(FIXTURES_DIR)),
                stage="switch_length",
                format=Format.PARQUET,
                schema_name="LengthRow",
                schema_version=CONTRACT_VERSION,
                entity_counts={"n_rows": len(length_rows)},
            ),
            Artifact(
                path=str(artifact_paths["clusters_h5ad"].relative_to(FIXTURES_DIR)),
                stage="clustering",
                format=Format.H5AD,
                schema_name="clusters.h5ad",
                schema_version=CONTRACT_VERSION,
                entity_counts={"n_obs": len(SURVIVING_CELLS), "n_vars": len(SURVIVING_PAS)},
            ),
            Artifact(
                path=str(artifact_paths["pasbed"].relative_to(FIXTURES_DIR)),
                stage="per_dataset_beds",
                format=Format.BED,
                schema_name="pasbed.bed",
                schema_version=CONTRACT_VERSION,
                entity_counts={"n_pas": len(SURVIVING_PAS)},
            ),
        ],
        entity_counts={
            "n_pas": len(SURVIVING_PAS),
            "n_cells": len(SURVIVING_CELLS),
            "n_genes": 2,
            "n_datasets": len(DATASETS),
            "n_findings": len(finding_rows),
            "n_length_rows": len(length_rows),
        },
    )
    path.write_text(json.dumps(manifest.model_dump(), indent=2, sort_keys=True) + "\n")


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    artifact_paths = {
        "pas_ledger": FIXTURES_DIR / "pas_ledger.tsv",
        "cell_ledger": FIXTURES_DIR / "cell_ledger.tsv",
        "findings": FIXTURES_DIR / "findings_long.parquet",
        "length": FIXTURES_DIR / "length_long.parquet",
        "clusters_h5ad": FIXTURES_DIR / "clusters.h5ad",
        "pasbed": FIXTURES_DIR / "pasbed.bed",
    }
    _write_pas_ledger_tsv(artifact_paths["pas_ledger"])
    _write_cell_ledger_tsv(artifact_paths["cell_ledger"])
    _write_findings_parquet(artifact_paths["findings"])
    _write_length_parquet(artifact_paths["length"])
    _write_pasbed(artifact_paths["pasbed"])
    _write_clusters_h5ad(artifact_paths["clusters_h5ad"])
    _write_gtf(FIXTURES_DIR / "genes.gtf")
    _write_run_manifest(FIXTURES_DIR / "run_manifest.json", artifact_paths)
    print(f"wrote fixtures to {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
