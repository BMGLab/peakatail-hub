# peakatail-io

The `Run` read-facade for `peakatail-hub`: reads one on-disk PeakATail
pipeline run directory (manifest, provenance ledgers, normalized
findings/length long tables, pasbed, `clusters.h5ad`) and returns the
`peakatail-contract` pydantic models.

Per the hub design spec §7a, `peakatail-contract` is schema-only (zero heavy
deps). This package is the opposite: its whole job is reading
anndata/h5py/scipy-shaped formats, so those ARE runtime dependencies here.
The mitigation is a **lazy-import discipline**, not avoiding the deps:

> Every `import anndata` / `import h5py` / `import scipy...` statement in
> this package lives INSIDE the body of the function that actually needs
> it (`Run.open_clusters_h5ad`, `Run.n_vars`, `Run.gene_counts`) — never at
> module top level. A bare `import peakatail_io` (e.g. to read a manifest
> or a BED/TSV file) stays fast and never pulls anndata into process
> memory. Grep for top-level `import anndata`/`import h5py`/`import scipy`
> in `src/peakatail_io/*.py` — there should be none.

## Install

```bash
cd packages/io
uv venv --python 3.12
uv pip install -e ".[dev]"   # pulls in the local editable ../contract too
```

`pyproject.toml` depends on `peakatail-contract` as an editable path
dependency (`../contract`) via `[tool.uv.sources]`.

## What's here

| Module | Contents |
|---|---|
| `peakatail_io/run.py` | The `Run` facade (see below) + `RunReadError`, `GeneNotFoundError`, `PasBedRecord`, `GeneCounts`. |
| `peakatail_io/validate_run.py` | `validate_run(run)` — one-line contract-conformance check wiring `Run` into `peakatail_contract.validate()`. |

## `Run` — design choice

`Run` is a **frozen dataclass** (`root: Path`, `manifest: RunManifest`), not
a class with `__init__` / internal caching. Every read method (`pas_ledger()`,
`cell_ledger()`, `findings()`, `length_rows()`, `pasbed()`,
`open_clusters_h5ad()`, `canonical_cluster()`) re-reads its artifact from
disk on every call — this package is a thin reader, not a cache; render/query
caching (if any) belongs in the backend (spec §3).

```python
from peakatail_io import Run, validate_run

run = Run.from_dir("/path/to/some_run")
run.manifest                 # RunManifest
run.pas_ledger()              # list[PasLedgerRow]
run.cell_ledger()             # list[CellLedgerRow]
run.findings()                 # list[FindingRow]
run.length_rows()              # list[LengthRow]
run.pasbed()                    # list[PasBedRecord]  -- canonical PAS coord source, see below
run.clusters_h5ad_path()        # Path, resolved via manifest.artifacts (never hardcoded)
run.open_clusters_h5ad()        # lazy `import anndata`; returns AnnData opened backed='r'
run.n_vars()                    # int, for the validate() core invariant
run.gene_counts("unified_2")    # GeneCounts -- the /genes/{id}/counts drill-down
run.canonical_cluster("ds1", "0")  # str | None, see bug B6 below

validate_run(run)  # raises ContractValidationError on any contract violation
```

### `Run.from_dir`

Reads `run_manifest.json` at the given directory root. Raises `RunReadError`
(never a silently empty manifest) if the file is missing or fails
`RunManifest` validation.

`Run.root` is the actual directory passed to `from_dir`, not
`manifest.root` (a string the manifest carries for provenance/display only).
All relative `Artifact.path` values are resolved against `Run.root`, so a
`Run` stays correct even if the run directory is copied/moved after the
manifest was written.

### Correctness defenses implemented (spec §7d)

- **`pasbed()` (or `pas_ledger()`) is the canonical PAS coordinate source.**
  Never read coordinates off `switch diff`/`switch length` TSV columns —
  those are blank/stale until bug B4 lands.
- **`gene_counts()` joins on `adata.var_names`, never `adata.var['gene_id']`**
  (bug B7: ~59% NaN in concatenated/report h5ad files). If the requested
  `var_name` isn't in `var_names`, raises `GeneNotFoundError` (a `KeyError`
  subclass) — if the value *would* have matched `var['gene_id']`, the error
  message says so explicitly, to steer callers away from repeating B7.
- **`clusters_h5ad_path()` looks up the artifact from `manifest.artifacts`**
  (matching `format=h5ad` + `stage` mentioning "cluster", or
  `schema_name == "clusters.h5ad"`) rather than hardcoding
  `per_dataset/<id>/clusters.h5ad` — real run layouts vary (some are
  `per_dataset/<id>/clusters.h5ad`, others `07_clustering/<id>/clusters.h5ad`).
  Falls back to the conventional path with a `warnings.warn` only if the
  manifest doesn't register the artifact at all.
- **`canonical_cluster(dataset_id, leiden)`** reads
  `cross_dataset/canonical_cluster_map.tsv` directly, because bug B6 means
  this mapping is written by the engine but never round-tripped into
  `clusters.h5ad`'s `obs` — `gene_counts(cluster=...)` will fall back to the
  raw `obs['leiden']` (with a warning) if `obs['canonical_cluster']` is
  absent, but that fallback is NOT cross-sample comparable. Cross-sample
  compare/UMAP-by-cluster features MUST gate on `canonical_cluster()`
  returning non-`None`.

### `GeneCounts`

`gene_counts(var_name, dataset_id=None, cluster=None)` returns per-cell raw
counts (aligned `cell_uids`/`counts` tuples/array) plus aggregate
`total`/`mean`/`n_cells`. If `cluster` is given, the same fields describe
just that cluster's subset (this is the "per-cluster-aggregated" mode) — the
aggregate fields are populated either way, so callers never need to
recompute them.

## Tests

```bash
cd packages/io
uv run pytest
```

Tests run against `../contract/fixtures` — the sibling `peakatail-contract`
package's committed, complete fixture run (`run_manifest.json`,
`pas_ledger.tsv`, `cell_ledger.tsv`, `findings_long.parquet`,
`length_long.parquet`, `pasbed.bed`, `clusters.h5ad`) — see
`tests/test_run_fixture.py`. Those fixtures were already complete and
committed on `feature/contract-v0` by the time this package's tests were
written, so no separate interim synthetic fixture was built (per the task
instructions: "if they're there and complete, write your tests against them
directly").

There is also `tests/test_run_real.py`, marked `@pytest.mark.integration`
and skipped automatically if the referenced real run directory isn't
present on the current machine; it opens one real Laughney-cohort
`clusters.h5ad` read-only and checks the `var_names`/`var['gene_id']` (B7)
invariant end to end.

## Interface notes for the backend agent

- `Run.from_dir(path)` never returns a partial/empty `Run` on error — it
  raises `RunReadError`. Catch that (not a bare `except Exception`) around
  indexer calls.
- `Run.findings()` / `Run.length_rows()` / `Run.pas_ledger()` /
  `Run.cell_ledger()` re-read from disk every call (no caching) — if you're
  building a DuckDB index, read once per index build, not per request.
- `Run.gene_counts()` raises `GeneNotFoundError(RunReadError, KeyError)` —
  both `except RunReadError` and `except KeyError` will catch it; return a
  4xx (not 5xx) from `/genes/{id}/counts` when you see it.
- `validate_run(run)` calls `run.n_vars()`, which opens `clusters.h5ad`
  (lazy anndata import) — don't call `validate_run` on a hot request path;
  call it once at index-build time.
- `Run.clusters_h5ad_path(dataset_id=...)` raises `RunReadError` if the
  manifest registers more than one clustering h5ad artifact and
  `dataset_id` doesn't disambiguate them — always pass `dataset_id` for
  multi-dataset runs.
