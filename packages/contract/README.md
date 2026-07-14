# peakatail-contract

The schema-only coupling layer between the **PeakATail engine** (bioinformatics
pipeline) and **peakatail-hub** (analyst cockpit: FastAPI + DuckDB + React).
Per the hub design spec §7a, this package is intentionally dependency-light:
pydantic models, an ID grammar, `validate()`, and fixtures. **No
anndata/h5py/scipy/scanpy/pysam as runtime deps.** The h5ad/mtx/bed *reader*
(the `Run` facade) lives in a separate `peakatail-io` package, not here.

Both the engine and the hub depend on this package and nothing else couples
them.

## Install

```bash
cd packages/contract
uv venv --python 3.12
uv pip install -e .            # runtime only (pydantic)
uv pip install -e ".[test]"    # + pytest/anndata/pyarrow/pandas/numpy, for
                                #   fixture generation and the test suite
```

## What's here

| Module | Contents |
|---|---|
| `peakatail_contract/models.py` | `RunManifest`, `DatasetRef`, `Artifact`, `PasLedgerRow`, `CellLedgerRow`, `FindingRow`, `LengthRow` + enums (`Format`, `Strategy`, `LengthStrategy`, `Direction`, `Tier`). |
| `peakatail_contract/ids.py` | Pure ID-minting functions: `pas_uid`, `cell_uid`, `cluster_uid`, `finding_uid`. |
| `peakatail_contract/validate.py` | `validate()` + `ContractValidationError` — cross-artifact referential integrity + the core drop-ledger invariant. |
| `peakatail_contract/schema_export.py` | Exports JSON Schema (one file per model) to `schema/*.json`, for the frontend's `lib/contract` TS-type generation. |
| `scripts/make_fixtures.py` | Regenerates the fixture run under `fixtures/`. Needs the `test` extra. |
| `fixtures/` | A complete, internally-consistent tiny synthetic run (committed). |

`CONTRACT_VERSION = "0.1.0"` lives in `peakatail_contract/__init__.py` and is
the default for `RunManifest.contract_version`. Bump the **major** component
whenever a model field is removed/renamed/retyped in a backward-incompatible
way — `validate()` rejects manifests/artifacts whose major version differs
from the installed contract.

## Schema summary

### `RunManifest`
`run_id, root, contract_version, datasets: list[DatasetRef], resolved_config: dict,
stratum_to_label: dict[str, str], artifacts: list[Artifact], entity_counts: dict[str, int]`.

`resolved_config` MUST be the actual resolved `RunConfig` object, not argparse
defaults (bug B0). `stratum_to_label` MUST be used to resolve any
celltype/stratum label before it's used for display, ID minting, or joins —
raw output-directory names are truncated to 48 characters by the filesystem
(bug D10) and are not safe to use directly.

### `DatasetRef`
`dataset_id, bam_paths: list[str], label: str | None`. `label` is
display-only; never join/mint on it.

### `Artifact`
`path, stage, format (Format enum), schema_name, schema_version, entity_counts: dict[str, int]`.

### `PasLedgerRow` (→ `provenance/pas_ledger.tsv`)
`orig_pas_key, chrom, start, end, strand, unified_pas_id, snap_distance_bp,
gene_id, gene_distance_bp, tier (Tier enum), last_stage, dropped_at, drop_reason`
+ computed `pas_uid` (`chrom:end:strand`).

### `CellLedgerRow` (→ `provenance/cell_ledger.tsv`)
`barcode, dataset_id, total_reads, n_pas, dropped_at, drop_reason, cluster`
+ computed `cell_uid` (`dataset_id:barcode`).

Note: `n_pas` is deliberately named that way, NOT `n_genes` — the real
pipeline's `clusters.h5ad obs['n_genes']` is actually a PAS-per-cell count
(scanpy-convention name left over from gene-expression data). See spec §7e.

### `FindingRow` (→ `findings_long`, defines the not-yet-existing engine stage E5)
`finding_uid, pas_uid, gene_id, canonical_cluster, comparison_cluster,
celltype, strategy (Strategy enum), arm, direction (Direction enum, never
silently NA), utr_class, qvalue, pvalue, delta_proportion, log2fc, odds_ratio,
n_cells, n_reads, n_cells_subject, n_cells_comparison, n_reads_subject,
n_reads_comparison`.

Long format: one row per PAS × comparison × strategy. Coordinates are
deliberately NOT duplicated here — always resolve via `pas_uid` → `PasLedgerRow`
(this is exactly how bug B4, blank/stale coords in switch diff/length TSVs, was
introduced upstream; the contract does not repeat that mistake).

### `LengthRow` (→ `length_long`)
`strategy (LengthStrategy enum), gene_id, transcript_id, cell_uid,
canonical_cluster, value, pas_uid, rank, direction`.

One schema covers all three `switch length` strategies (`classic` /
`proportion` / `shannon`); `value` holds pdui / proportion / entropy
respectively. Only `proportion` rows populate `pas_uid`/`rank`/`direction`
today (spec §7c) — `direction` is nullable specifically for this reason
(contrast with `FindingRow.direction`, which is never null).

## ID grammar (`peakatail_contract/ids.py`)

| Function | Grammar | Why |
|---|---|---|
| `pas_uid(chrom, end, strand)` | `chrom:end:strand` | Content-addressed, strand-safe (fixes bug B1: run-local `pas_id` collides across strand). Supersedes the Data Controller Design draft `{run}:{ds}:{pas_id}` per spec §7d. |
| `cell_uid(dataset_id, barcode)` | `dataset_id:barcode` | Standardizes the existing namespaced-barcode convention. |
| `cluster_uid(dataset_id, leiden)` | `dataset_id:leiden` | Makes per-sample cluster-label collisions explicit/joinable; NOT the same as `canonical_cluster` (post-B6 cross-sample alignment). |
| `finding_uid(resolved_label, var_name, strategy, arm, pas_uid_value)` | `arm:strategy:resolved_label:var_name:pas_uid_value` | Per spec §7g: minted from the **manifest-resolved label** (never a raw/truncated directory name, D10) and **`var_names`** (never `var['gene_id']`, ~59% NaN, B7). |

All four are pure functions of already-known values — no lookups, no
randomness — so the engine indexer, the hub indexer, and test fixtures always
re-mint byte-identical IDs. Each rejects inputs containing the `:` separator
(except `finding_uid`'s trailing `pas_uid_value`, which is allowed to contain
`:` because it is always the last field — see the docstring in `ids.py`).

## `validate()`

`peakatail_contract.validate.validate(manifest, pas_ledger, cell_ledger=...,
findings=..., length_rows=..., n_vars_clusters_h5ad=..., required_artifact_stages=...)`
checks, accumulating ALL violations before raising `ContractValidationError`:

1. Required artifacts present (by stage).
2. `manifest.contract_version` / each `Artifact.schema_version` share a major
   version with the installed contract.
3. Referential integrity: every `FindingRow.pas_uid` / populated
   `LengthRow.pas_uid` exists in the PAS ledger; every `LengthRow.cell_uid`
   exists in the cell ledger (if provided).
4. **The core invariant**: `rows(pas_ledger where dropped_at=="") ==
   n_vars(clusters.h5ad)`. This package cannot open an h5ad itself (schema-only,
   §7a) — callers pass `n_vars_clusters_h5ad` in as a plain `int` (computed by
   `peakatail-io` or a test fixture).

## Fixtures (`fixtures/`)

A complete, internally-consistent synthetic run: `run_manifest.json`,
`pas_ledger.tsv`, `cell_ledger.tsv`, `findings_long.parquet`,
`length_long.parquet`, `clusters.h5ad`, `pasbed.bed`. Six PAS ledger rows, four
of which survive (`dropped_at == ""`) — `clusters.h5ad` has exactly
`n_vars=4` to match. Seven cell-ledger rows, six of which survive —
`clusters.h5ad` has exactly `n_obs=6` to match. `findings_long` and
`length_long` reference only real, surviving `pas_uid`s and `cell_uid`s.

Regenerate:

```bash
cd packages/contract
uv pip install -e ".[test]"
uv run python scripts/make_fixtures.py
```

## JSON Schema export

```bash
cd packages/contract
uv run peakatail-contract-schema-export   # writes schema/*.json
```

Output is sorted-key, indented JSON so it diffs cleanly; this is what the
hub frontend's `lib/contract` TS types are generated from.

## Tests

```bash
cd packages/contract
uv pip install -e ".[test]"
uv run pytest
```

## Open questions / judgment calls made building v0

- **`finding_uid` join order.** The grammar is
  `arm:strategy:resolved_label:var_name:pas_uid_value`, with `pas_uid_value`
  last specifically because it may itself contain `:` — every other field is
  guarded against containing the separator. If a future field also needs to
  contain `:`, only one such field may safely be last; revisit if that happens.
- **`FindingRow.comparison_cluster` / `n_cells_comparison` / etc.** are not
  named explicitly in the frontend-design spec's field list, but are included
  to avoid losing information already present in the real `switch diff` wide
  TSVs (`cluster2`, `n_cells_cluster2`, `n_reads_pas_cluster2`). All are
  nullable so `nb_multi` omnibus rows (no single partner cluster) can omit them.
- **`LengthRow.transcript_id` for per-gene isoform-agg mode.** The real
  pipeline fabricates a `"_gene_"` sentinel transcript id in this mode (Data
  Controller Design §1). The contract represents "no specific isoform" as an
  explicit `None` instead of propagating that sentinel — engine writers
  should map `"_gene_"` → `None` when populating this schema.
- **Fixture `var_names == unified_pas_id`, not `pas_uid`.** `pas_uid` contains
  `:` (`chrom:end:strand`) and `ids.finding_uid`'s `var_name` argument rejects
  `:` (it must be unambiguously joinable with the other colon-separated
  fields — see `ids.py`). So the fixture's `clusters.h5ad var_names` uses the
  ledger's `unified_pas_id` token (colon-free, still stable and unique per
  PAS) instead. This exercises spec §7d's "join on `var_names`, never
  `var['gene_id']`" without conflating `var_names` syntax with `pas_uid`
  syntax. The real engine's `clusters.h5ad` `var_names` convention isn't
  pinned down yet upstream; whatever it turns out to be, the hub's indexer is
  the place to reconcile `var_names` → `pas_uid` (via the PAS ledger), not
  this contract.
- **`Artifact.stage` and `RunManifest.entity_counts` keys are free-form
  strings/dicts, not enums.** The engine's stage set is open-ended (new `NN_*`
  stage dirs get added routinely); over-constraining this would just mean
  updating the contract every time the engine adds a stage. `validate()`'s
  `required_artifact_stages` param lets a caller assert specific stages exist
  without the schema itself enumerating all possible stages.
