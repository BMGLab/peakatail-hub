# io_stub — STUB, superseded by the real `peakatail-io`

**Status update**: `packages/io/` landed partway through this task (the
sibling agent finished it), and continued evolving for a while after that --
notably `Run.gene_counts()` changed from a per-gene bulk-DataFrame call to a
per-`var_name` call returning a `GeneCounts` dataclass (`cell_uids`/`counts`/
`total`/`mean`/`n_cells`), and `Run.from_dir()`/artifact reads raise
`RunReadError` (a dedicated exception, not bare `FileNotFoundError`).
`peakatail_hub/api/genes.py`'s `/genes/{id}/counts` endpoint was updated to
match: it resolves `gene_id` -> surviving `unified_pas_id`s via the DuckDB
pas_ledger first, then calls `gene_counts()` once per var_name and pivots
the results into one gene-level table. This stub's `gene_counts()` and
`from_dir()` were updated to mirror that same final shape (see below), so
whichever implementation is active behaves identically to callers.

`backend/pyproject.toml` now depends on `packages/io/` directly
(`peakatail-io = { path = "../packages/io", editable = true }`), and
`peakatail_hub/io_compat.py`'s `try: from peakatail_io import Run,
validate_run` succeeds first, so **this stub is no longer imported by
anything** in normal operation (verified: `peakatail_hub.io_compat.
USING_IO_STUB is False` in a synced venv). One known, harmless drift:
`pasbed()` still returns a `pandas.DataFrame` here vs. the real package's
`list[PasBedRecord]` -- left unfixed because nothing in `backend/` calls
`Run.pasbed()` (geneview coordinates are sourced from the DuckDB
`pas_ledger` table, itself populated from `Run.pas_ledger()`).

It is kept only as the documented fallback for a checkout that has this
`backend/` but not yet `uv sync`'d `packages/io/` (e.g. partial clones,
older lockfiles). Safe to delete once that's no longer a concern.

Original rationale (kept for history): `packages/io/` did not exist on disk
when this backend was built (checked at the start of this task — see the
parent task's "required reading" step; `find . -iname '*peakatail-io*'`
came up empty across the whole monorepo).

Per the task brief: *"if either package isn't 100% finished when you start,
treat the interface described above as authoritative and stub/mock what's
missing, clearly marked, so you are not blocked."* This directory is that
stub. It implements the **documented** interface:

```
Run.from_dir(path) -> Run
Run.manifest                          # RunManifest
Run.pas_ledger()    -> list[PasLedgerRow]
Run.cell_ledger()   -> list[CellLedgerRow]
Run.findings()      -> list[FindingRow]
Run.length_rows()   -> list[LengthRow]
Run.pasbed()        -> pandas.DataFrame[chrom,start,end,name,score,strand]  # NOTE: real pkg returns list[PasBedRecord]; unused by backend/
Run.open_clusters_h5ad() -> anndata.AnnData   # lazy anndata import
Run.gene_counts(var_name, cluster=None) -> GeneCounts(var_name, cluster,
                                               cluster_col, cell_uids, counts,
                                               total, mean, n_cells)
                                               # lazy anndata import; PER-VAR
                                               # (one PAS at a time) -- join on
                                               # var_names, never var['gene_id']
                                               # (spec §7d). Raises
                                               # GeneNotFoundError if var_name
                                               # isn't in adata.var_names.
Run.n_vars()        -> int
validate_run(run)                             # thin wrapper around
                                               # peakatail_contract.validate()
RunReadError / GeneNotFoundError(RunReadError, KeyError)  # exception types
```

It reads a fixture-shaped run directory (`run_manifest.json` + the artifacts
it registers) exactly as a real `peakatail-io` reader would, using only the
paths/schema_name/stage fields in the manifest -- no hardcoded filenames
beyond the fallbacks used when an expected artifact stage is absent.

## How to retire this stub

Nothing outside `peakatail_hub/io_compat.py` imports this package directly.
Once `packages/io/` lands as a real, installable `peakatail-io`:

1. Add it as a path dependency in `backend/pyproject.toml` (uncomment the
   `io` extra / add `peakatail-io = { path = "../packages/io", editable =
   true }` under `[tool.uv.sources]`, mirroring how `peakatail-contract` is
   wired) and `uv sync`.
2. That's it — `io_compat.py`'s `try: from peakatail_io import Run,
   validate_run` will succeed first and this stub is never imported again.
3. Delete this directory once the real package's interface is confirmed to
   match (or adjust `io_compat.py` if the real signature differs from what's
   assumed here, especially `gene_counts()`'s exact parameter name/return
   shape, which was not observable anywhere on disk at stub-authoring time).
