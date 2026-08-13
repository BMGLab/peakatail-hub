"""The `Run` read-facade: one on-disk PeakATail pipeline run directory.

LAZY-IMPORT RULE (spec §7a): `import anndata`, `import h5py`, and
`import scipy...` are used ONLY inside the bodies of `open_clusters_h5ad`,
`n_vars`, and `gene_counts` (the functions that actually touch the h5ad /
its sparse matrix) -- never at this module's top level. Every other method
on `Run` (`from_dir`, `pas_ledger`, `cell_ledger`, `findings`, `length_rows`,
`pasbed`, `canonical_cluster`, `clusters_h5ad_path`) only touches JSON/TSV/
parquet/BED text files via pandas/csv/json, so a bare `import peakatail_io`
stays fast and never pulls anndata into process memory. If you add a new
method here that needs anndata/h5py/scipy, put the import inside the
function body and say so in its docstring.
"""

from __future__ import annotations

import csv
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from peakatail_contract.models import (
    CellLedgerRow,
    FindingRow,
    Format,
    LengthRow,
    PasLedgerRow,
    RunManifest,
    Tier,
)


class RunReadError(Exception):
    """Raised for any problem reading a run directory or one of its artifacts:
    missing/unparseable `run_manifest.json`, a missing artifact file, an
    ambiguous artifact lookup, etc. Never silently swallowed -- callers get
    a clear message pointing at the offending path.
    """


class GeneNotFoundError(RunReadError, KeyError):
    """Raised by `Run.gene_counts()` when `var_name` is not in
    `adata.var_names`. Subclasses both `RunReadError` (so `except
    RunReadError` catches it) and `KeyError` (so callers doing a
    dict-lookup-style `except KeyError` also catch it, per the "clear
    KeyError-style error" requirement -- never a silent empty result).
    """


@dataclass(frozen=True)
class PasBedRecord:
    """One row of `pasbed.bed` (BED6, tab-separated, no header).

    Per spec §7d, THIS (or `Run.pas_ledger()`) is the canonical source of
    PAS coordinates. Callers (backend included) must never read coordinates
    off `switch diff`/`switch length` TSV coordinate columns -- those are
    blank/stale until bug B4 lands (Data Controller Design). `start`/`end`
    are BED convention (0-based half-open); `pas_id` is the run-local
    integer/label in BED col4, NOT the content-addressed `pas_uid` -- join
    on `pas_uid` (chrom:end:strand, see `peakatail_contract.ids.pas_uid`) or
    on `PasLedgerRow` for stable cross-run identity.
    """

    chrom: str
    start: int
    end: int
    pas_id: str
    score: float
    strand: str


@dataclass(frozen=True, eq=False)
class GeneCounts:
    """Result of `Run.gene_counts()` -- the `/genes/{id}/counts` drill-down.

    `cell_uids`/`counts` are always aligned (same order, same length):
    per-cell rows when `cluster is None`, or the subset of cells in
    `cluster` when it is given. `total`/`mean`/`n_cells` are always the
    aggregate over whatever subset `cell_uids` represents, so callers doing
    a per-cluster aggregation don't need to recompute it themselves.
    """

    var_name: str
    dataset_id: str | None
    cluster: str | None
    cluster_col: str | None
    """Which obs column `cluster` was matched against ('canonical_cluster'
    if available, else 'leiden' with a B6 warning); None if `cluster` was
    not given."""
    cell_uids: tuple[str, ...]
    counts: np.ndarray
    total: float
    mean: float
    n_cells: int


def _opt_int(value: str) -> int | None:
    """Empty-string convention for optional int ledger columns (see
    `ema/provenance.py::_sanitize`): `""` means the field was never set,
    not the integer `0`.

    Parses via `float()` first, then `int()`: a TSV round-tripped through
    pandas (e.g. `DataFrame.to_csv` after a column that mixes real ints
    with missing values) commonly serializes those ints as `"12.0"` rather
    than `"12"` (pandas upcasts an int column with NaN to float64).
    `int("12.0")` raises `ValueError`; `int(float("12.0"))` does not.
    """
    return None if value == "" else int(float(value))


def _opt_str(value: str) -> str | None:
    """Empty-string convention for optional str ledger columns: `""` means
    `None` (the field was never set)."""
    return None if value == "" else value


def _parquet_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """`df.to_dict("records")`, but with every NaN replaced by `None`.

    `DataFrame.where(pd.notnull(df), None)` does NOT reliably do this: on a
    float64 (or nullable-numeric) column, assigning `None` back into a
    `.where()` call gets silently re-coerced to NaN by pandas because the
    column's dtype doesn't hold Python `None` -- the NaN survives the round
    trip. Optional `FindingRow`/`LengthRow` fields (e.g. `odds_ratio`,
    `log2fc`, `pas_uid`, `direction`) are written as NaN by
    `pandas.DataFrame.to_parquet` for exactly this reason (mixed None/value
    columns upcast to float64/object-with-NaN), so pydantic must see a real
    `None`, not a `nan` float, or validation fails with a confusing
    "not a valid string"/"not a finite number" error. We instead walk each
    record's values explicitly with `pd.isna()`, which is dtype-agnostic.
    """
    records: list[dict[str, Any]] = df.to_dict("records")
    for rec in records:
        for key, value in rec.items():
            if isinstance(value, float) and pd.isna(value):
                rec[key] = None
    return records


@dataclass(frozen=True)
class Run:
    """Read-only facade over one on-disk PeakATail pipeline run directory.

    Deliberately a plain frozen dataclass (not a class with `__init__`) --
    `root` and `manifest` are the only state, both immutable once
    constructed via `from_dir`, and every other capability is a plain
    method that re-reads its artifact from disk on each call (no caching:
    this package is a thin reader, not a cache layer -- render/query
    caching, if any, belongs in the backend per spec §3).

    `root` is the actual on-disk directory passed to `from_dir`, which is
    what every relative artifact path is resolved against -- NOT
    `manifest.root` (a string the manifest carries for provenance/display).
    This makes `Run` robust to a run directory being copied/moved after the
    manifest was written, at the cost of trusting the manifest's *relative*
    paths but not its absolute `root` field for resolution.
    """

    root: Path
    manifest: RunManifest

    # -- construction ----------------------------------------------------

    @classmethod
    def from_dir(cls, path: str | Path) -> Run:
        """Read `run_manifest.json` at `path` and return a `Run`.

        Raises `RunReadError` (never returns a partially-empty manifest) if
        the file is missing, unreadable, or fails `RunManifest` validation.
        """
        root = Path(path).expanduser().resolve()
        manifest_path = root / "run_manifest.json"
        if not manifest_path.exists():
            raise RunReadError(
                f"no run_manifest.json found at {manifest_path} -- is {root} a "
                "PeakATail run output directory produced with manifest writing (E2) enabled?"
            )
        try:
            raw = manifest_path.read_text()
        except OSError as exc:
            raise RunReadError(f"could not read {manifest_path}: {exc}") from exc
        try:
            manifest = RunManifest.model_validate_json(raw)
        except Exception as exc:  # pydantic ValidationError or json.JSONDecodeError
            raise RunReadError(
                f"{manifest_path} exists but is not a valid RunManifest: {exc}"
            ) from exc
        return cls(root=root, manifest=manifest)

    # -- path resolution ---------------------------------------------------

    def _resolve(self, rel_or_abs: str) -> Path:
        p = Path(rel_or_abs)
        return p if p.is_absolute() else self.root / p

    def _resolve_artifact(self, schema_name: str, conventional_relpath: str) -> Path:
        """Look up `schema_name` in `manifest.artifacts`; fall back to the
        conventional relative path (with a warning) if the manifest doesn't
        register it -- manifests are allowed to be incomplete (E2 is a
        roadmap item), but callers should be told when we're guessing.
        """
        for artifact in self.manifest.artifacts:
            if artifact.schema_name == schema_name:
                return self._resolve(artifact.path)
        warnings.warn(
            f"RunManifest (run_id={self.manifest.run_id!r}) does not register an artifact "
            f"with schema_name={schema_name!r}; falling back to the conventional path "
            f"{conventional_relpath!r} under the run root. This is a manifest-completeness "
            "gap, not a guarantee the file exists there.",
            stacklevel=3,
        )
        return self._resolve(conventional_relpath)

    # -- provenance ledgers ------------------------------------------------

    def pas_ledger(self) -> list[PasLedgerRow]:
        """Read `provenance/pas_ledger.tsv`.

        Columns exactly per `ema/provenance.py::PAS_LEDGER_COLUMNS`:
        `orig_pas_key, chrom, start, end, strand, unified_pas_id,
        snap_distance_bp, gene_id, gene_distance_bp, tier, last_stage,
        dropped_at, drop_reason`. Empty-string convention: `dropped_at`
        stays `""` (survived) -- never coerced to `None` -- `gene_id`
        stays `""` (INTERGENIC has no gene), and optional int/enum/str
        fields (`snap_distance_bp`, `gene_distance_bp`, `tier`,
        `drop_reason`) become `None` when empty.
        """
        path = self._resolve_artifact("PasLedgerRow", "provenance/pas_ledger.tsv")
        if not path.exists():
            raise RunReadError(f"pas_ledger.tsv not found at {path}")
        rows: list[PasLedgerRow] = []
        with path.open(newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for rec in reader:
                rows.append(
                    PasLedgerRow(
                        orig_pas_key=rec["orig_pas_key"],
                        chrom=rec["chrom"],
                        start=_opt_int(rec["start"]),
                        end=_opt_int(rec["end"]),
                        strand=rec["strand"],
                        unified_pas_id=rec["unified_pas_id"],
                        snap_distance_bp=_opt_int(rec["snap_distance_bp"]),
                        gene_id=rec["gene_id"],
                        gene_distance_bp=_opt_int(rec["gene_distance_bp"]),
                        tier=Tier(rec["tier"]) if rec["tier"] else None,
                        last_stage=rec["last_stage"],
                        dropped_at=rec["dropped_at"],
                        drop_reason=_opt_str(rec["drop_reason"]),
                    )
                )
        return rows

    def cell_ledger(self) -> list[CellLedgerRow]:
        """Read `provenance/cell_ledger.tsv`.

        Columns exactly per `ema/provenance.py::CELL_LEDGER_COLUMNS`:
        `barcode, dataset_id, total_reads, n_pas, dropped_at, drop_reason,
        cluster`. Same empty-string convention as `pas_ledger()`.
        """
        path = self._resolve_artifact("CellLedgerRow", "provenance/cell_ledger.tsv")
        if not path.exists():
            raise RunReadError(f"cell_ledger.tsv not found at {path}")
        rows: list[CellLedgerRow] = []
        with path.open(newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for rec in reader:
                rows.append(
                    CellLedgerRow(
                        barcode=rec["barcode"],
                        dataset_id=rec["dataset_id"],
                        total_reads=_opt_int(rec["total_reads"]),
                        n_pas=_opt_int(rec["n_pas"]),
                        dropped_at=rec["dropped_at"],
                        drop_reason=_opt_str(rec["drop_reason"]),
                        cluster=_opt_str(rec["cluster"]),
                    )
                )
        return rows

    # -- normalized long tables -------------------------------------------

    def findings(self) -> list[FindingRow]:
        """Read `findings_long.parquet` into `FindingRow` objects."""
        path = self._resolve_artifact("FindingRow", "findings_long.parquet")
        if not path.exists():
            return []
        df = pd.read_parquet(path)
        return [FindingRow.model_validate(rec) for rec in _parquet_records(df)]

    def length_rows(self) -> list[LengthRow]:
        """Read `length_long.parquet` into `LengthRow` objects."""
        path = self._resolve_artifact("LengthRow", "length_long.parquet")
        if not path.exists():
            return []
        df = pd.read_parquet(path)
        return [LengthRow.model_validate(rec) for rec in _parquet_records(df)]

    # -- coordinates --------------------------------------------------------

    def pasbed(self) -> list[PasBedRecord]:
        """Read `pasbed.bed` (BED6, tab-separated, no header).

        CANONICAL COORDINATE SOURCE (spec §7d): callers must source PAS
        coordinates from here (or from `pas_ledger()`'s
        chrom/start/end/strand columns), NEVER from the coordinate columns
        in `switch diff`/`switch length` TSVs, which are blank/stale until
        bug B4 is fixed.
        """
        path = self._resolve_artifact("pasbed.bed", "pasbed.bed")
        if not path.exists():
            raise RunReadError(f"pasbed.bed not found at {path}")
        records: list[PasBedRecord] = []
        with path.open() as fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.rstrip("\n")
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) < 6:
                    raise RunReadError(
                        f"{path}:{lineno}: expected BED6 (>=6 tab-separated fields), got {len(parts)}: {line!r}"
                    )
                chrom, start, end, pas_id, score, strand = parts[:6]
                records.append(
                    PasBedRecord(
                        chrom=chrom,
                        start=int(start),
                        end=int(end),
                        pas_id=pas_id,
                        score=float(score),
                        strand=strand,
                    )
                )
        return records

    # -- clusters.h5ad -------------------------------------------------------

    def clusters_h5ad_path(self, dataset_id: str | None = None) -> Path:
        """Resolve the path to the relevant `clusters.h5ad`.

        Looked up via `manifest.artifacts` (an `Artifact` whose `format`
        is `h5ad` and whose `stage` mentions "cluster", or whose
        `schema_name == "clusters.h5ad"`) -- NEVER hardcoded, because real
        run layouts vary (`per_dataset/<id>/clusters.h5ad` in some runs,
        `07_clustering/<id>/clusters.h5ad` / `09_clustering/<id>/` in
        others, see `PeakATail_Pipeline_IO_Reference.md` §1 step 9). If
        `dataset_id` is given and multiple candidates exist, we scope by
        matching `dataset_id` against the artifact path's parent directory
        name (the `Artifact` model has no dedicated `dataset_id` field
        today). Raises `RunReadError` if the scoped result is still
        ambiguous. If the manifest registers no matching artifact at all,
        falls back to the conventional `per_dataset/<dataset_id>/
        clusters.h5ad` path with a clear warning (this is a manifest gap,
        not a promise the file exists there).
        """
        candidates = [
            a
            for a in self.manifest.artifacts
            if a.format == Format.H5AD and ("cluster" in a.stage.lower() or a.schema_name == "clusters.h5ad")
        ]
        if dataset_id is not None and len(candidates) > 1:
            scoped = [a for a in candidates if Path(a.path).parent.name == dataset_id]
            if scoped:
                candidates = scoped

        if len(candidates) == 1:
            return self._resolve(candidates[0].path)
        if len(candidates) > 1:
            raise RunReadError(
                f"ambiguous clusters.h5ad artifact for dataset_id={dataset_id!r} in run_id="
                f"{self.manifest.run_id!r}: {len(candidates)} candidates "
                f"{[a.path for a in candidates]!r}; pass dataset_id to disambiguate."
            )

        ds = dataset_id or (self.manifest.datasets[0].dataset_id if self.manifest.datasets else "default")
        fallback = self.root / "per_dataset" / ds / "clusters.h5ad"
        warnings.warn(
            f"RunManifest (run_id={self.manifest.run_id!r}) registers no clustering h5ad "
            f"artifact (no Artifact with format=h5ad and stage mentioning 'cluster'); falling "
            f"back to the conventional path {fallback}. This is a manifest-completeness gap "
            "(E2), not a guarantee the file exists there.",
            stacklevel=2,
        )
        return fallback

    def open_clusters_h5ad(self, dataset_id: str | None = None) -> Any:
        """Open `clusters.h5ad` for `dataset_id` (or the manifest's
        sole/first dataset if omitted / unambiguous).

        LAZY IMPORT: `import anndata` happens here, not at module top
        level (spec §7a) -- this is the ONE heavy-import entry point most
        other `Run` methods avoid calling. Opened with `backed='r'`: the
        expression matrix stays on disk (h5py-backed access), so opening a
        run with a huge `clusters.h5ad` to check e.g. `n_vars` or slice one
        gene's column does not materialize the whole matrix in memory.
        Tradeoff: some anndata/scanpy operations don't support backed mode
        and per-access latency is higher than a fully in-memory read --
        acceptable here since this facade only ever needs `obs`/`var`
        metadata (loaded eagerly regardless -- they're small) and small
        slices of `X`, never a full recompute.
        """
        import anndata as ad

        path = self.clusters_h5ad_path(dataset_id)
        if not path.exists():
            raise RunReadError(f"clusters.h5ad not found at {path} (dataset_id={dataset_id!r})")
        return ad.read_h5ad(path, backed="r")

    def n_vars(self, dataset_id: str | None = None) -> int:
        """`adata.n_vars` for the `validate()` core invariant check
        (`rows(pas_ledger where dropped_at=='') == n_vars(clusters.h5ad)`).
        Opens via `open_clusters_h5ad` (lazy anndata import; see there).
        """
        adata = self.open_clusters_h5ad(dataset_id)
        return int(adata.n_vars)

    def gene_counts(
        self,
        var_name: str,
        dataset_id: str | None = None,
        cluster: str | None = None,
    ) -> GeneCounts:
        """The `/genes/{id}/counts` drill-down: per-cell (or
        per-cluster-filtered) raw counts for one PAS/var.

        MUST join on `adata.var_names`, NEVER `adata.var['gene_id']` (bug
        B7: that column is ~59% NaN in concatenated/report h5ad files
        because it is a plain carried-through column, not the index --
        verified 18368/30919 NaN on a real run, see `ids.py` module
        docstring). If `var_name` is not in `var_names`, raises
        `GeneNotFoundError` (a `KeyError` subclass) rather than silently
        returning an empty result -- and if the lookup would have
        "succeeded" via the unsafe `var['gene_id']` column, the error
        message says so explicitly, to steer callers away from repeating
        B7.

        `cluster`, if given, filters to `obs['canonical_cluster'] ==
        cluster` (falling back to the raw per-dataset `obs['leiden']` with
        a B6 warning if `canonical_cluster` hasn't been round-tripped into
        this h5ad yet) and returns just that subset's cells alongside the
        aggregate `total`/`mean`/`n_cells`; the same aggregate fields are
        populated over the full per-cell set when `cluster` is None.
        """
        adata = self.open_clusters_h5ad(dataset_id)

        if var_name not in adata.var_names:
            hint = ""
            if "gene_id" in adata.var.columns:
                by_gene_id = adata.var.index[adata.var["gene_id"] == var_name]
                if len(by_gene_id) > 0:
                    hint = (
                        f" (found {len(by_gene_id)} var(s) with var['gene_id']=={var_name!r}: "
                        f"{list(by_gene_id)[:5]!r} -- but var['gene_id'] is the WRONG join key, "
                        "it is ~59% NaN in concatenated/report h5ad files (bug B7); use one of "
                        "those var_names values instead)"
                    )
            raise GeneNotFoundError(f"{var_name!r} not found in adata.var_names{hint}")

        sub = adata[:, [var_name]]
        x = sub.X
        # Lazy scipy import: only needed if the matrix happens to be sparse
        # (backed h5ad columns are frequently returned as a scipy sparse
        # matrix even for a single-column slice).
        try:
            import scipy.sparse as sp

            is_sparse = sp.issparse(x)
        except ImportError:  # pragma: no cover - scipy is a declared dep, defensive only
            is_sparse = False
        if is_sparse:
            counts_all = np.asarray(x.todense()).ravel()
        else:
            counts_all = np.asarray(x).ravel()

        cell_uids_all = tuple(str(c) for c in adata.obs_names)

        cluster_col: str | None = None
        if cluster is not None:
            if "canonical_cluster" in adata.obs.columns:
                cluster_col = "canonical_cluster"
            elif "leiden" in adata.obs.columns:
                cluster_col = "leiden"
                warnings.warn(
                    "gene_counts(cluster=...) is filtering by the raw per-dataset "
                    "obs['leiden'] label because obs['canonical_cluster'] is absent "
                    "(bug B6: canonical_cluster_map.tsv is written but never "
                    "round-tripped into clusters.h5ad obs). This is NOT cross-sample "
                    "comparable -- see Run.canonical_cluster().",
                    stacklevel=2,
                )
            else:
                raise RunReadError(
                    "gene_counts(cluster=...) requires an obs['canonical_cluster'] or "
                    "obs['leiden'] column; neither is present on this clusters.h5ad"
                )
            mask = (adata.obs[cluster_col].astype(str) == str(cluster)).to_numpy()
            cell_uids = tuple(c for c, m in zip(cell_uids_all, mask) if m)
            counts = counts_all[mask]
        else:
            cell_uids = cell_uids_all
            counts = counts_all

        n_cells = int(counts.shape[0])
        total = float(counts.sum()) if n_cells else 0.0
        mean = float(counts.mean()) if n_cells else 0.0

        return GeneCounts(
            var_name=var_name,
            dataset_id=dataset_id,
            cluster=cluster,
            cluster_col=cluster_col,
            cell_uids=cell_uids,
            counts=counts,
            total=total,
            mean=mean,
            n_cells=n_cells,
        )

    # -- canonical cluster (bug B6) ------------------------------------------

    def canonical_cluster(self, dataset_id: str, leiden: str) -> str | None:
        """Look up `cross_dataset/canonical_cluster_map.tsv` (columns:
        `dataset_id, original_cluster, canonical_cluster, match_confidence,
        matched_to`, confirmed against real run output) for the canonical,
        cross-sample-comparable label of `(dataset_id, leiden)`.

        Returns `None` (with a warning) if the file doesn't exist at all
        (single-dataset run, or the cross-dataset match step hasn't run).
        Per bug B6 (Data Controller Design), this mapping is written by the
        engine but is NEVER round-tripped into `clusters.h5ad`'s `obs` --
        so even when this file DOES exist, `clusters.h5ad.obs` alone cannot
        answer this question; you must read this TSV. Cross-sample
        UMAP-by-cluster and "compare" features (spec §7d) MUST gate on this
        method returning non-None before treating clusters from different
        datasets as comparable.
        """
        path = self.root / "cross_dataset" / "canonical_cluster_map.tsv"
        if not path.exists():
            warnings.warn(
                "cross_dataset/canonical_cluster_map.tsv not found -- either this is a "
                "single-dataset run (no cross-dataset match step ran), or the match step "
                "has not run yet. Returning None; see bug B6: even when this file exists, "
                "clusters.h5ad's obs does NOT carry canonical_cluster today, so "
                "cross-sample compare/UMAP-by-cluster features must gate on this returning "
                "non-None rather than reading obs directly.",
                stacklevel=2,
            )
            return None
        with path.open(newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                if row["dataset_id"] == dataset_id and row["original_cluster"] == str(leiden):
                    return row["canonical_cluster"]
        return None
