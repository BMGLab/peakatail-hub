"""Round-trip tests against the real `packages/contract/fixtures` run.

Per the task instructions: contract's fixtures were checked (they exist and
are complete on `feature/contract-v0`, committed by the sibling contract
agent) so these tests read that fixture end-to-end rather than building an
interim synthetic one for the primary suite. See `test_run_synthetic.py` for
the interim fixture that was built before that was confirmed, kept here as
a second, independent exercise of the same read paths.
"""

from __future__ import annotations

import warnings

import pytest

from peakatail_contract import CellLedgerRow, FindingRow, LengthRow, PasLedgerRow
from peakatail_io import GeneNotFoundError, PasBedRecord, Run, validate_run
from peakatail_io.run import RunReadError


def test_from_dir_missing_manifest(tmp_path):
    with pytest.raises(RunReadError, match="run_manifest.json"):
        Run.from_dir(tmp_path)


def test_manifest(contract_run: Run):
    m = contract_run.manifest
    assert m.run_id == "fixture-run-0001"
    assert {d.dataset_id for d in m.datasets} == {"ds1", "ds2"}
    assert m.entity_counts["n_pas"] == 4
    assert m.entity_counts["n_cells"] == 6


def test_pas_ledger(contract_run: Run):
    rows = contract_run.pas_ledger()
    assert len(rows) == 6
    assert all(isinstance(r, PasLedgerRow) for r in rows)
    surviving = [r for r in rows if r.dropped_at == ""]
    assert len(surviving) == 4
    dropped = {r.dropped_at for r in rows if r.dropped_at != ""}
    assert dropped == {"atlas_snap", "pas_gene_assignment"}
    # empty-string vs None conventions
    survivor = next(r for r in rows if r.orig_pas_key == "ds1:+:1")
    assert survivor.dropped_at == ""  # never coerced to None
    assert survivor.drop_reason is None  # empty numeric/str fields -> None
    assert survivor.snap_distance_bp == 12
    assert isinstance(survivor.snap_distance_bp, int)
    dropped_row = next(r for r in rows if r.orig_pas_key == "ds1:+:5")
    assert dropped_row.dropped_at == "atlas_snap"
    assert dropped_row.drop_reason == "no atlas hit within atlas_distance=100"
    assert dropped_row.gene_id == ""  # INTERGENIC / never assigned -> "" not None
    assert dropped_row.snap_distance_bp is None
    # computed pas_uid field: strand-aware 3'-summit position (E1, frozen
    # 2026-07-14) is `end - 1` on `+` strand, not the raw BED `end` --
    # start=999/end=1000/+ -> summit 999, per ids.pas_summit_pos.
    assert survivor.pas_uid == "chr1:999:+"


def test_cell_ledger(contract_run: Run):
    rows = contract_run.cell_ledger()
    assert len(rows) == 7
    assert all(isinstance(r, CellLedgerRow) for r in rows)
    surviving = [r for r in rows if r.dropped_at == ""]
    assert len(surviving) == 6
    dropped_row = next(r for r in rows if r.dropped_at != "")
    assert dropped_row.dropped_at == "cb_filter"
    assert dropped_row.cluster is None
    survivor = next(r for r in rows if r.barcode == "AAACCCAAGT")
    assert survivor.cluster == "0"
    assert survivor.cell_uid == "ds1:AAACCCAAGT"


def test_findings(contract_run: Run):
    rows = contract_run.findings()
    assert len(rows) == 4
    assert all(isinstance(r, FindingRow) for r in rows)
    pas_uids = {r.pas_uid for r in contract_run.pas_ledger()}
    assert all(r.pas_uid in pas_uids for r in rows)
    # at least one nullable numeric field really is None (nb_multi has no odds_ratio)
    assert any(r.odds_ratio is None for r in rows)


def test_length_rows(contract_run: Run):
    rows = contract_run.length_rows()
    assert len(rows) == 30
    assert all(isinstance(r, LengthRow) for r in rows)
    # only 'proportion' strategy rows populate pas_uid/rank/direction
    for r in rows:
        if r.strategy.value == "proportion":
            assert r.pas_uid is not None
            assert r.rank is not None
        else:
            assert r.pas_uid is None
            assert r.direction is None


def test_pasbed(contract_run: Run):
    records = contract_run.pasbed()
    assert len(records) == 4
    assert all(isinstance(r, PasBedRecord) for r in records)
    first = records[0]
    assert (first.chrom, first.start, first.end, first.strand) == ("chr1", 999, 1000, "+")


def test_clusters_h5ad_path_resolved_via_manifest(contract_run: Run):
    path = contract_run.clusters_h5ad_path()
    assert path.name == "clusters.h5ad"
    assert path.exists()


def test_open_clusters_h5ad_and_n_vars(contract_run: Run):
    adata = contract_run.open_clusters_h5ad()
    assert adata.n_vars == 4
    assert adata.n_obs == 6
    assert contract_run.n_vars() == 4


def test_gene_counts_by_var_name(contract_run: Run):
    result = contract_run.gene_counts("unified_2")
    assert result.n_cells == 6
    assert len(result.cell_uids) == 6
    assert result.counts.shape == (6,)
    assert result.total == pytest.approx(float(result.counts.sum()))


def test_gene_counts_by_cluster(contract_run: Run):
    result = contract_run.gene_counts("unified_2", cluster="cl_A")
    assert result.cluster_col == "canonical_cluster"
    assert result.n_cells > 0
    assert result.n_cells < 6  # a strict subset of all cells


def test_gene_counts_rejects_var_gene_id(contract_run: Run):
    """B7 defense: var['gene_id'] must NEVER be a usable join key here."""
    with pytest.raises(GeneNotFoundError):
        contract_run.gene_counts("ENSG00000000001")  # a gene_id value, not a var_name


def test_gene_counts_unknown_var_name_raises_keyerror(contract_run: Run):
    with pytest.raises(KeyError):
        contract_run.gene_counts("not-a-real-var-name")


def test_canonical_cluster_map_missing_returns_none_with_warning(contract_run: Run):
    # The committed fixture deliberately ships clusters.h5ad with
    # obs['canonical_cluster'] already populated (simulating the
    # post-B6-fix state, per make_fixtures.py) but does NOT ship a
    # cross_dataset/canonical_cluster_map.tsv file -- exercise the "file
    # doesn't exist" branch directly against it.
    assert not (contract_run.root / "cross_dataset" / "canonical_cluster_map.tsv").exists()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = contract_run.canonical_cluster("ds1", "0")
    assert result is None
    assert any("B6" in str(w.message) for w in caught)


def test_canonical_cluster_reads_real_map_format(tmp_path, contract_run: Run):
    """Column layout confirmed against a real engine run's
    cross_dataset/canonical_cluster_map.tsv: `dataset_id, original_cluster,
    canonical_cluster, match_confidence, matched_to`.
    """
    import shutil

    dest = tmp_path / "run_with_cross_dataset"
    shutil.copytree(contract_run.root, dest)
    cross_dir = dest / "cross_dataset"
    cross_dir.mkdir()
    (cross_dir / "canonical_cluster_map.tsv").write_text(
        "dataset_id\toriginal_cluster\tcanonical_cluster\tmatch_confidence\tmatched_to\n"
        'ds1\t0\tcl_A\t1.0\t"[[""ds2"", ""0""]]"\n'
        'ds2\t0\tcl_A\t1.0\t"[[""ds1"", ""0""]]"\n'
        'ds1\t1\tcl_B\t1.0\t"[[""ds2"", ""1""]]"\n'
        'ds2\t1\tcl_B\t1.0\t"[[""ds1"", ""1""]]"\n'
    )
    run = Run.from_dir(dest)
    assert run.canonical_cluster("ds1", "0") == "cl_A"
    assert run.canonical_cluster("ds1", "1") == "cl_B"
    assert run.canonical_cluster("ds2", "0") == "cl_A"
    assert run.canonical_cluster("ds1", "nonexistent") is None


def test_validate_run_passes(contract_run: Run):
    validate_run(contract_run)  # must not raise
