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
) -> None:
    """Assemble everything `peakatail_contract.validate()` needs from `run`
    (manifest, pas_ledger, cell_ledger, findings, length_rows, and
    `n_vars_clusters_h5ad` via `run.n_vars()`) and call it, so callers
    (e.g. the backend indexer) get a single "is this run contract-
    conformant" check.

    `dataset_id` is forwarded to `run.n_vars()` to disambiguate which
    `clusters.h5ad` to open when a run has more than one dataset (see
    `Run.clusters_h5ad_path`). Lets `ContractValidationError` (listing
    every violation found, not just the first) propagate to the caller --
    this function itself never catches or summarizes it.
    """
    validate(
        manifest=run.manifest,
        pas_ledger=run.pas_ledger(),
        cell_ledger=run.cell_ledger(),
        findings=run.findings(),
        length_rows=run.length_rows(),
        n_vars_clusters_h5ad=run.n_vars(dataset_id=dataset_id),
        required_artifact_stages=required_artifact_stages,
    )
