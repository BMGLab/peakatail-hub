"""Tests exercising the specific correctness defenses spec §7d mandates the
hub implement -- run here against the fixture h5ad so a regression in the
fixture's shape (or a future contract change) is caught immediately, not
only when the hub is built.
"""

from __future__ import annotations

from pathlib import Path

import anndata as ad

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_var_gene_id_column_has_holes_like_the_real_bug_b7():
    # The fixture deliberately reproduces bug B7 (var['gene_id'] ~59% NaN)
    # so that any reader joining on that column (instead of var_names) is
    # demonstrably wrong against this fixture.
    adata = ad.read_h5ad(FIXTURES_DIR / "clusters.h5ad")
    assert adata.var["gene_id"].isna().any(), "fixture must include at least one NaN gene_id to exercise B7"


def test_var_names_are_fully_populated_and_unique():
    adata = ad.read_h5ad(FIXTURES_DIR / "clusters.h5ad")
    assert adata.var_names.isna().sum() == 0
    assert len(set(adata.var_names)) == adata.n_vars


def test_correct_reader_joins_on_var_names_not_gene_id_column():
    """Demonstrates the §7d-mandated join: iterate var_names (always
    populated), NOT var['gene_id'] (holes). A naive reader that joined on
    the gene_id column would silently drop the NaN rows; this reader does not.
    """
    adata = ad.read_h5ad(FIXTURES_DIR / "clusters.h5ad")
    # "Correct" reader: every var gets a row, keyed by var_names.
    correct = {name: idx for idx, name in enumerate(adata.var_names)}
    assert len(correct) == adata.n_vars

    # "Naive/buggy" reader: joins on the (NaN-holed) gene_id column and
    # silently drops rows -- included here only to document why it's wrong,
    # not as something the contract endorses.
    naive = {gid: idx for idx, gid in enumerate(adata.var["gene_id"]) if isinstance(gid, str)}
    assert len(naive) < adata.n_vars, "the whole point of B7: naive gene_id join loses rows"


def test_h5ad_shape_matches_ledger_invariant(fixture_n_vars_clusters_h5ad, fixture_n_obs_clusters_h5ad, fixture_pas_ledger, fixture_cell_ledger):
    n_surviving_pas = sum(1 for r in fixture_pas_ledger if r.dropped_at == "")
    n_surviving_cells = sum(1 for r in fixture_cell_ledger if r.dropped_at == "")
    assert n_surviving_pas == fixture_n_vars_clusters_h5ad
    assert n_surviving_cells == fixture_n_obs_clusters_h5ad
