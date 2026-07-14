from __future__ import annotations

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


def _roundtrip(model_cls, instance):
    as_dict = instance.model_dump(mode="json")
    rehydrated = model_cls(**as_dict)
    assert rehydrated.model_dump(mode="json") == as_dict
    return rehydrated


def test_artifact_roundtrip():
    a = Artifact(
        path="pas_ledger.tsv",
        stage="provenance",
        format=Format.TSV,
        schema_name="PasLedgerRow",
        schema_version="0.1.0",
        entity_counts={"n_rows": 6},
    )
    _roundtrip(Artifact, a)


def test_dataset_ref_roundtrip():
    d = DatasetRef(dataset_id="ds1", bam_paths=["a.bam", "b.bam"], label="raw label")
    _roundtrip(DatasetRef, d)


def test_run_manifest_roundtrip():
    m = RunManifest(
        run_id="run1",
        root="/tmp/run1",
        datasets=[DatasetRef(dataset_id="ds1", bam_paths=["a.bam"])],
        resolved_config={"atlas": None, "min_read": 50},
        stratum_to_label={"ds1": "TCell_activated"},
        artifacts=[
            Artifact(
                path="x.tsv", stage="provenance", format=Format.TSV, schema_name="PasLedgerRow"
            )
        ],
        entity_counts={"n_pas": 4, "n_cells": 6},
    )
    rehydrated = _roundtrip(RunManifest, m)
    assert rehydrated.contract_version == "0.1.0"


def test_pas_ledger_row_roundtrip_and_computed_pas_uid():
    row = PasLedgerRow(
        orig_pas_key="ds1:+:1",
        chrom="chr1",
        start=999,
        end=1000,
        strand="+",
        unified_pas_id="unified_1",
        snap_distance_bp=12,
        gene_id="ENSG00000000001",
        gene_distance_bp=50,
        tier=Tier.TIER_1,
        last_stage="clustering",
        dropped_at="",
        drop_reason=None,
    )
    rehydrated = _roundtrip(PasLedgerRow, row)
    assert rehydrated.pas_uid == "chr1:1000:+"
    # pas_uid is a computed field: it must be present in the serialized form
    # too (not just accessible as a Python attribute), since the hub relies
    # on it being in the JSON that crosses the wire.
    assert row.model_dump(mode="json")["pas_uid"] == "chr1:1000:+"


def test_pas_ledger_row_dropped_and_survivor_are_distinguishable():
    survivor = PasLedgerRow(
        orig_pas_key="k1", chrom="chr1", start=1, end=2, strand="+",
        unified_pas_id="u1", last_stage="clustering", dropped_at="",
    )
    dropped = PasLedgerRow(
        orig_pas_key="k2", chrom="chr1", start=1, end=2, strand="+",
        unified_pas_id="u2", last_stage="atlas_snap", dropped_at="atlas_snap",
        drop_reason="no atlas hit",
    )
    assert survivor.dropped_at == ""
    assert dropped.dropped_at != ""


def test_cell_ledger_row_roundtrip_and_computed_cell_uid():
    row = CellLedgerRow(
        barcode="AAAA",
        dataset_id="ds1",
        total_reads=512,
        n_pas=4,
        dropped_at="",
        drop_reason=None,
        cluster="0",
    )
    rehydrated = _roundtrip(CellLedgerRow, row)
    assert rehydrated.cell_uid == "ds1:AAAA"


def test_finding_row_roundtrip_direction_never_omitted():
    row = FindingRow(
        finding_uid="arm:fisher:TCell:unified_1:chr1:1000:+",
        pas_uid="chr1:1000:+",
        gene_id="ENSG00000000001",
        canonical_cluster="cl_A",
        comparison_cluster="cl_B",
        celltype="TCell_activated",
        strategy=Strategy.FISHER,
        arm="cl_A_vs_cl_B",
        direction=Direction.SHORTEN,
        utr_class="tandem_utr",
        qvalue=0.01,
        pvalue=0.001,
        delta_proportion=0.35,
        log2fc=1.2,
        odds_ratio=2.1,
        n_cells=6,
        n_reads=250,
    )
    rehydrated = _roundtrip(FindingRow, row)
    assert rehydrated.direction in (Direction.SHORTEN, Direction.LENGTHEN, Direction.FLAT, Direction.UNDETERMINED)


def test_length_row_roundtrip_classic_and_proportion():
    classic = LengthRow(
        strategy=LengthStrategy.CLASSIC,
        gene_id="ENSG00000000001",
        transcript_id="ENST00000000001",
        cell_uid="ds1:AAAA",
        canonical_cluster="cl_A",
        value=0.62,
    )
    _roundtrip(LengthRow, classic)
    assert classic.pas_uid is None
    assert classic.direction is None

    proportion = LengthRow(
        strategy=LengthStrategy.PROPORTION,
        gene_id="ENSG00000000001",
        transcript_id="ENST00000000001",
        cell_uid="ds1:AAAA",
        canonical_cluster="cl_A",
        value=0.7,
        pas_uid="chr1:1000:+",
        rank=0,
        direction=Direction.SHORTEN,
    )
    rehydrated = _roundtrip(LengthRow, proportion)
    assert rehydrated.pas_uid == "chr1:1000:+"
    assert rehydrated.direction == Direction.SHORTEN
