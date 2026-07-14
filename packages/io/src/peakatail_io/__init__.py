"""peakatail-io: the Run read-facade for peakatail-hub.

Reads one on-disk PeakATail pipeline run directory (manifest, provenance
ledgers, normalized findings/length long tables, pasbed, clusters.h5ad) and
returns the ``peakatail_contract`` pydantic models. This is the ONE package
in the hub stack that is allowed to depend on anndata/h5py/scipy (spec §7a) --
`peakatail-contract` itself stays schema-only/dependency-light.

LAZY-IMPORT RULE (spec §7a, binding for every module in this package): any
statement that imports ``anndata``, ``h5py``, or ``scipy`` (or a submodule of
those) must be written INSIDE the function body that actually needs it, never
at module top level. This keeps `import peakatail_io` itself fast and keeps
anndata/h5py out of process memory for callers that only need the manifest,
ledgers, findings/length tables, or pasbed (e.g. every DuckDB-backed FastAPI
endpoint per spec §7a). Grep for top-level `import anndata`/`import h5py`/
`import scipy` in this package's modules -- there should be none.
"""

from __future__ import annotations

from peakatail_io.run import GeneCounts, GeneNotFoundError, PasBedRecord, Run, RunReadError
from peakatail_io.validate_run import validate_run

__all__ = [
    "Run",
    "RunReadError",
    "GeneNotFoundError",
    "PasBedRecord",
    "GeneCounts",
    "validate_run",
]
