"""One-line contract-conformance check for a `Run`.

No anndata/h5py/scipy imports at this module's top level either -- the one
heavy call here is `run.n_vars()`, which itself lazily imports anndata
inside `Run.open_clusters_h5ad` (see run.py). Nothing in this module needs
its own lazy-import guard beyond delegating to `Run`.
"""

from __future__ import annotations

from collections.abc import Sequence

from peakatail_contract import validate
from peakatail_contract.validate import ContractValidationError

from peakatail_io.run import Run

__all__ = ["validate_run", "ContractValidationError"]


def validate_run(
    run: Run,
    *,
    dataset_id: str | None = None,
    required_artifact_stages: Sequence[str] | None = None,
    check_ledger_invariant: bool = True,
) -> None:
    """Assemble everything `peakatail_contract.validate()` needs from `run`
    (manifest, pas_ledger, cell_ledger, findings, length_rows, and --
    conditionally, see `check_ledger_invariant` -- `n_vars_clusters_h5ad`
    via `run.n_vars()`) and call it, so callers (e.g. the backend indexer)
    get a single "is this run contract-conformant" check.

    `dataset_id` is forwarded to `run.n_vars()` to disambiguate which
    `clusters.h5ad` to open when a run has more than one dataset (see
    `Run.clusters_h5ad_path`). Lets `ContractValidationError` (listing
    every violation found, not just the first) propagate to the caller --
    this function itself never catches or summarizes it.

    `check_ledger_invariant` (default True, matching the fixtures/tests
    where the ledger IS complete): pass False to SKIP the
    `rows(pas_ledger where dropped_at=="") == n_vars(clusters.h5ad)`
    invariant entirely (by simply not computing/forwarding
    `n_vars_clusters_h5ad` -- `peakatail_contract.validate()` only checks
    the invariant when that argument is supplied). Engine-team's E3 ledger
    is being wired incrementally, drop-site by drop-site (atlas-snap first;
    cb-filter/pas-gene/preprocess still to come as of 2026-07-14) -- until
    ALL drop sites are wired for a given run, `pas_ledger` is legitimately
    partial and this invariant WILL NOT hold. The backend indexer must call
    this with `check_ledger_invariant=False` for real (non-fixture) runs
    until the manifest can self-declare ledger completeness; fixtures and
    contract-level tests should keep the default (True) since the fixture
    ledger IS deliberately complete.
    """
    validate(
        manifest=run.manifest,
        pas_ledger=run.pas_ledger(),
        cell_ledger=run.cell_ledger(),
        findings=run.findings(),
        length_rows=run.length_rows(),
        n_vars_clusters_h5ad=run.n_vars(dataset_id=dataset_id) if check_ledger_invariant else None,
        required_artifact_stages=required_artifact_stages,
    )
