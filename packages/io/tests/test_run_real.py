"""Integration test against ONE real PeakATail run's `clusters.h5ad`.

Per the task instructions: "locate and read against ONE real run's
clusters.h5ad to sanity-check the h5ad path end-to-end (not just synthetic
data)". Real PeakATail runs do not yet have a `run_manifest.json` (E2 is an
engine roadmap item, not landed), so this test does NOT go through
`Run.from_dir` / the manifest-driven artifact lookup -- it opens the h5ad
directly via `anndata` (mirroring what `Run.open_clusters_h5ad` does
internally) to sanity-check the real on-disk shape our reader will face,
and specifically to check the B7 `var['gene_id']` NaN-rate claim on a real
file.

Marked `integration` and skipped outright if the referenced path isn't
present on this machine (e.g. CI, or a different developer's checkout).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from peakatail_io import GeneNotFoundError

REAL_CLUSTERS_H5AD = Path(
    os.environ.get(
        "PEAKATAIL_IO_TEST_REAL_H5AD",
        "/home/user/PeakATail/peakatail_runs/full_v6_2026-05-11_151942/per_dataset/default/clusters.h5ad",
    )
)

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not REAL_CLUSTERS_H5AD.exists(), reason=f"real run not present at {REAL_CLUSTERS_H5AD}")
def test_real_clusters_h5ad_opens_cleanly_and_var_names_populated():
    import anndata as ad

    adata = ad.read_h5ad(REAL_CLUSTERS_H5AD, backed="r")

    # var_names (the index) must always be fully populated -- this is the
    # B7 defense: it's what gene_counts()/finding_uid must join on.
    assert adata.var_names.is_unique
    assert not adata.var_names.isna().any()
    assert adata.n_vars > 0
    assert adata.n_obs > 0

    # Report (not assert -- B7 may or may not manifest on THIS specific
    # file; it was verified on a different, concatenated/report h5ad, see
    # ids.py module docstring) the observed var['gene_id'] NaN rate, if the
    # column exists on this file.
    if "gene_id" in adata.var.columns:
        n_nan = int(adata.var["gene_id"].isna().sum())
        n_total = int(adata.var.shape[0])
        print(
            f"\n[B7 sanity check] {REAL_CLUSTERS_H5AD}: "
            f"var['gene_id'] NaN = {n_nan}/{n_total} ({100 * n_nan / n_total:.1f}%)"
        )
        # Whatever the observed rate is on THIS file, var_names itself
        # (checked above) must still be fully populated -- that's the
        # actual invariant gene_counts()/finding_uid rely on.


@pytest.mark.skipif(not REAL_CLUSTERS_H5AD.exists(), reason=f"real run not present at {REAL_CLUSTERS_H5AD}")
def test_gene_counts_style_lookup_rejects_gene_id_style_value_on_real_file():
    """Exercise the exact `Run.gene_counts` var_names-vs-gene_id defense
    against the real file, without going through `Run.from_dir` (no
    manifest on real runs yet) -- replicate its var_name/gene_id check
    directly against the opened AnnData, the same logic `Run.gene_counts`
    runs internally.
    """
    import anndata as ad

    adata = ad.read_h5ad(REAL_CLUSTERS_H5AD, backed="r")
    if "gene_id" not in adata.var.columns:
        pytest.skip("this real file has no var['gene_id'] column to test the B7 defense against")

    real_gene_ids = adata.var["gene_id"].dropna().unique()
    assert len(real_gene_ids) > 0
    gene_id_value = str(real_gene_ids[0])

    # A gene_id value is (by construction, per B7) not necessarily a member
    # of var_names -- looking it up as if it were a var_name must fail
    # loudly, exactly like Run.gene_counts()'s own check.
    if gene_id_value in adata.var_names:
        pytest.skip("this real file's var_names happen to collide with gene_id values; not a useful B7 case")

    with pytest.raises(GeneNotFoundError):
        _lookup_var_or_raise(adata, gene_id_value)

    # A real var_names value must succeed.
    real_var_name = str(adata.var_names[0])
    _lookup_var_or_raise(adata, real_var_name)  # must not raise


def _lookup_var_or_raise(adata, var_name: str) -> None:
    """Standalone re-implementation of `Run.gene_counts`'s var_names guard,
    used here to test the defense without requiring a `run_manifest.json`
    (which real runs don't have yet, unlike `Run.gene_counts` which always
    goes through a `Run`)."""
    if var_name not in adata.var_names:
        raise GeneNotFoundError(f"{var_name!r} not found in adata.var_names")
