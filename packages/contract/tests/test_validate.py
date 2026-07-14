from __future__ import annotations

import pytest

from peakatail_contract.validate import ContractValidationError, validate


def test_fixture_passes_validation(
    fixture_manifest, fixture_pas_ledger, fixture_cell_ledger, fixture_findings, fixture_length_rows, fixture_n_vars_clusters_h5ad
):
    # Should not raise.
    validate(
        manifest=fixture_manifest,
        pas_ledger=fixture_pas_ledger,
        cell_ledger=fixture_cell_ledger,
        findings=fixture_findings,
        length_rows=fixture_length_rows,
        n_vars_clusters_h5ad=fixture_n_vars_clusters_h5ad,
        required_artifact_stages=["provenance", "switch_diff", "switch_length", "clustering"],
    )


def test_fixture_invariant_matches_h5ad_exactly(fixture_pas_ledger, fixture_n_vars_clusters_h5ad):
    n_surviving = sum(1 for r in fixture_pas_ledger if r.dropped_at == "")
    assert n_surviving == fixture_n_vars_clusters_h5ad == 4


def test_mutated_fixture_fails_invariant(fixture_manifest, fixture_pas_ledger, fixture_n_vars_clusters_h5ad):
    # Delete one surviving ledger row -> n_surviving no longer matches
    # n_vars(clusters.h5ad); validate() must catch this, not silently pass.
    mutated = [r for r in fixture_pas_ledger if r.dropped_at == ""][1:]  # drop one survivor
    mutated += [r for r in fixture_pas_ledger if r.dropped_at != ""]

    with pytest.raises(ContractValidationError) as exc_info:
        validate(
            manifest=fixture_manifest,
            pas_ledger=mutated,
            n_vars_clusters_h5ad=fixture_n_vars_clusters_h5ad,
        )
    assert any("invariant violated" in e for e in exc_info.value.errors)


def test_mutated_fixture_fails_referential_integrity(fixture_manifest, fixture_pas_ledger, fixture_findings):
    # Remove the ledger row that a finding references -> dangling pas_uid.
    referenced = fixture_findings[0].pas_uid
    mutated_ledger = [r for r in fixture_pas_ledger if r.pas_uid != referenced]

    with pytest.raises(ContractValidationError) as exc_info:
        validate(
            manifest=fixture_manifest,
            pas_ledger=mutated_ledger,
            findings=fixture_findings,
        )
    assert any("references unknown pas_uid" in e for e in exc_info.value.errors)


def test_missing_required_artifact_stage_fails(fixture_manifest, fixture_pas_ledger):
    with pytest.raises(ContractValidationError) as exc_info:
        validate(
            manifest=fixture_manifest,
            pas_ledger=fixture_pas_ledger,
            required_artifact_stages=["this_stage_does_not_exist"],
        )
    assert any("missing required artifact" in e for e in exc_info.value.errors)


def test_contract_version_major_mismatch_fails(fixture_manifest, fixture_pas_ledger):
    bad_manifest = fixture_manifest.model_copy(update={"contract_version": "9.0.0"})
    with pytest.raises(ContractValidationError) as exc_info:
        validate(manifest=bad_manifest, pas_ledger=fixture_pas_ledger)
    assert any("major version" in e for e in exc_info.value.errors)


def test_accumulates_multiple_errors_not_just_first(fixture_manifest, fixture_pas_ledger):
    bad_manifest = fixture_manifest.model_copy(update={"contract_version": "9.0.0"})
    with pytest.raises(ContractValidationError) as exc_info:
        validate(
            manifest=bad_manifest,
            pas_ledger=fixture_pas_ledger,
            required_artifact_stages=["nope"],
            n_vars_clusters_h5ad=999,
        )
    # at least: version mismatch + missing artifact + invariant violation
    assert len(exc_info.value.errors) >= 3


def test_dangling_cell_uid_in_length_rows_fails(fixture_manifest, fixture_pas_ledger, fixture_cell_ledger, fixture_length_rows):
    truncated_cell_ledger = fixture_cell_ledger[:1]  # keep only one cell
    with pytest.raises(ContractValidationError) as exc_info:
        validate(
            manifest=fixture_manifest,
            pas_ledger=fixture_pas_ledger,
            cell_ledger=truncated_cell_ledger,
            length_rows=fixture_length_rows,
        )
    assert any("unknown cell_uid" in e for e in exc_info.value.errors)
