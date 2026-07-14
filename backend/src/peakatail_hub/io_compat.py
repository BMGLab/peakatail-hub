"""Single seam through which the rest of peakatail_hub reaches the `Run`
read-facade and `validate_run()`.

Per the task brief, `peakatail-io` (the sibling package that owns
`Run.from_dir()` / `.pas_ledger()` / `.open_clusters_h5ad()` / `.gene_counts()`
/ `validate_run()`) may not be finished -- or even installable -- yet. Rather
than block on it or scatter `try/except ImportError` all over the codebase,
every other module in peakatail_hub imports `Run` and `validate_run` from
*this* module only.

Today (peakatail-io absent) this resolves to the bundled stub in
`peakatail_hub.io_stub`, which implements the exact interface documented in
the task brief by reading the packages/contract fixture-shaped run directory
directly (manifest json, ledger tsvs, findings/length parquet, pasbed.bed,
and a lazily-imported anndata read of clusters.h5ad). It is clearly marked
as a stub (see io_stub/README.md) and deliberately mirrors peakatail-io's
public surface so that once the real package lands, swapping the import
below (or just `pip install`-ing peakatail-io so the first import succeeds)
is the ONLY change required -- no router/indexer/store code changes.
"""

from __future__ import annotations

USING_IO_STUB: bool

try:
    from peakatail_io import Run, validate_run  # type: ignore[import-not-found]
    from peakatail_io.run import GeneNotFoundError, RunReadError  # type: ignore[import-not-found]

    USING_IO_STUB = False
except ImportError:
    from peakatail_hub.io_stub.run import GeneNotFoundError, Run, RunReadError, validate_run

    USING_IO_STUB = True

__all__ = ["GeneNotFoundError", "Run", "RunReadError", "USING_IO_STUB", "validate_run"]
