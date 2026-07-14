"""STUB `Run` read-facade + `validate_run()` — see README.md in this directory.

Reads a manifest-driven run directory into the peakatail_contract pydantic
row models. Zero heavy imports at module scope (anndata is imported lazily
inside `open_clusters_h5ad()` / `gene_counts()` only), matching spec §7a's
"heavy reader imported on exactly one path" rule even inside the stub.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from peakatail_contract import (
    CellLedgerRow,
    FindingRow,
    LengthRow,
    PasLedgerRow,
    RunManifest,
)
from peakatail_contract import validate as _contract_validate
from peakatail_contract.models import Tier


def _blank_to_none(value: Any) -> Any:
    """TSV/CSV round-tripping renders `None` as `''`; parquet round-tripping
    (via pandas) renders it as `NaN`. Normalize both to `None` before handing
    a row dict to a pydantic model constructor.
    """
    if value is None:
        return None
    if isinstance(value, str) and value == "":
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _int_or_none(value: Any) -> int | None:
    value = _blank_to_none(value)
    return None if value is None else int(float(value))


class RunReadError(Exception):
    """Mirrors `peakatail_io.run.RunReadError` -- raised for a missing/
    unparseable run directory or artifact. Kept in sync with the real
    package's exception name so `io_compat.py`'s `except RunReadError`
    callers work unchanged whichever implementation is active.
    """


class GeneNotFoundError(RunReadError, KeyError):
    """Mirrors `peakatail_io.run.GeneNotFoundError` -- raised by
    `gene_counts()` when `var_name` is not in `adata.var_names`.
    """


class Run:
    """Manifest-driven read facade over one contract-conformant run directory.

    Construct via :meth:`from_dir`, never directly.
    """

    def __init__(self, root: Path, manifest: RunManifest):
        self._root = root
        self.manifest = manifest

    # -- construction ----------------------------------------------------

    @classmethod
    def from_dir(cls, path: str | Path) -> "Run":
        path = Path(path)
        manifest_path = path / "run_manifest.json"
        if not manifest_path.exists():
            raise RunReadError(f"no run_manifest.json under {path}")
        try:
            manifest = RunManifest.model_validate(json.loads(manifest_path.read_text()))
        except (json.JSONDecodeError, ValueError) as exc:
            raise RunReadError(f"malformed run_manifest.json at {manifest_path}: {exc}") from exc
        return cls(root=path, manifest=manifest)

    # -- artifact path resolution -----------------------------------------

    def _artifact_path(self, *, schema_name: str | None = None, stage: str | None = None, fallback: str) -> Path:
        """Resolve an artifact's on-disk path from the manifest, preferring a
        match on schema_name/stage over the hardcoded `fallback` filename.
        Tries the artifact path relative to this Run's own directory first
        (the directory actually passed to `from_dir`), then relative to
        `manifest.root` (handles a run that was copied/moved after the
        manifest was written), then finally the bare fallback under root.
        """
        candidates: list[str] = []
        for artifact in self.manifest.artifacts:
            if (schema_name is not None and artifact.schema_name == schema_name) or (
                stage is not None and artifact.stage == stage
            ):
                candidates.append(artifact.path)
        candidates.append(fallback)

        bases = [self._root, Path(self.manifest.root)]
        for rel in candidates:
            rel_path = Path(rel)
            if rel_path.is_absolute() and rel_path.exists():
                return rel_path
            for base in bases:
                candidate = base / rel_path
                if candidate.exists():
                    return candidate
        # Nothing on disk -- return the best-guess path so the caller's
        # FileNotFoundError points at the right place.
        return self._root / candidates[0]

    # -- ledgers / long tables --------------------------------------------

    def pas_ledger(self) -> list[PasLedgerRow]:
        path = self._artifact_path(schema_name="PasLedgerRow", fallback="pas_ledger.tsv")
        rows: list[PasLedgerRow] = []
        with path.open(newline="") as fh:
            for record in csv.DictReader(fh, delimiter="\t"):
                record.pop("pas_uid", None)  # computed_field, not settable
                tier_raw = _blank_to_none(record.get("tier"))
                rows.append(
                    PasLedgerRow(
                        orig_pas_key=record["orig_pas_key"],
                        chrom=record["chrom"],
                        start=int(record["start"]),
                        end=int(record["end"]),
                        strand=record["strand"],
                        unified_pas_id=record["unified_pas_id"],
                        snap_distance_bp=_int_or_none(record.get("snap_distance_bp")),
                        gene_id=record.get("gene_id") or "",
                        gene_distance_bp=_int_or_none(record.get("gene_distance_bp")),
                        tier=Tier(tier_raw) if tier_raw else None,
                        last_stage=record["last_stage"],
                        dropped_at=record.get("dropped_at") or "",
                        drop_reason=_blank_to_none(record.get("drop_reason")),
                    )
                )
        return rows

    def cell_ledger(self) -> list[CellLedgerRow]:
        path = self._artifact_path(schema_name="CellLedgerRow", fallback="cell_ledger.tsv")
        rows: list[CellLedgerRow] = []
        with path.open(newline="") as fh:
            for record in csv.DictReader(fh, delimiter="\t"):
                record.pop("cell_uid", None)  # computed_field, not settable
                rows.append(
                    CellLedgerRow(
                        barcode=record["barcode"],
                        dataset_id=record["dataset_id"],
                        total_reads=int(record["total_reads"]),
                        n_pas=int(record["n_pas"]),
                        dropped_at=record.get("dropped_at") or "",
                        drop_reason=_blank_to_none(record.get("drop_reason")),
                        cluster=_blank_to_none(record.get("cluster")),
                    )
                )
        return rows

    def findings(self) -> list[FindingRow]:
        path = self._artifact_path(schema_name="FindingRow", fallback="findings_long.parquet")
        df = pd.read_parquet(path)
        rows: list[FindingRow] = []
        for record in df.to_dict(orient="records"):
            clean = {k: _blank_to_none(v) for k, v in record.items()}
            rows.append(FindingRow(**clean))
        return rows

    def length_rows(self) -> list[LengthRow]:
        path = self._artifact_path(schema_name="LengthRow", fallback="length_long.parquet")
        df = pd.read_parquet(path)
        rows: list[LengthRow] = []
        for record in df.to_dict(orient="records"):
            clean = {k: _blank_to_none(v) for k, v in record.items()}
            rows.append(LengthRow(**clean))
        return rows

    def pasbed(self) -> pd.DataFrame:
        """PAS coordinates from `pasbed.bed`. Per spec §7d this -- NOT the
        findings-table coordinate columns (which don't exist on FindingRow
        precisely to prevent that mistake) -- is the source of truth for
        rendering PAS positions.
        """
        path = self._artifact_path(schema_name="pasbed.bed", fallback="pasbed.bed")
        return pd.read_csv(
            path,
            sep="\t",
            header=None,
            names=["chrom", "start", "end", "name", "score", "strand"],
        )

    # -- heavy reader: the ONE place this stub imports anndata -------------

    def open_clusters_h5ad(self):
        """Lazy anndata import -- spec §7a: the heavy reader must be
        importable on exactly one path. Callers (the indexer's umap_points
        extraction, and `gene_counts()` below) both funnel through here.
        """
        import anndata as ad  # noqa: PLC0415 -- intentionally lazy

        path = self._artifact_path(schema_name="clusters.h5ad", fallback="clusters.h5ad")
        return ad.read_h5ad(path)

    def n_vars(self) -> int:
        for artifact in self.manifest.artifacts:
            if artifact.schema_name == "clusters.h5ad" and "n_vars" in artifact.entity_counts:
                return artifact.entity_counts["n_vars"]
        return int(self.open_clusters_h5ad().n_vars)

    def gene_counts(self, var_name: str, cluster: str | None = None) -> "GeneCounts":
        """Raw per-cell counts for one PAS/`var_name` (matches the real
        `peakatail_io.Run.gene_counts()` per-var signature, NOT per-gene --
        callers resolve gene_id -> surviving `unified_pas_id`s via
        `pas_ledger()` themselves, see `peakatail_hub.api.genes.gene_counts`).

        MUST join on `adata.var_names`, NEVER `adata.var['gene_id']` (bug
        B7, ~59% NaN in real runs; the fixture reproduces this deliberately).
        Raises `GeneNotFoundError` if `var_name` isn't in `var_names`.
        """
        adata = self.open_clusters_h5ad()
        if var_name not in adata.var_names:
            raise GeneNotFoundError(f"{var_name!r} not found in adata.var_names")

        sub = adata[:, [var_name]]
        x = sub.X
        if hasattr(x, "toarray"):
            x = x.toarray()  # noqa: PLC0415 -- scipy sparse, imported implicitly by anndata
        import numpy as np  # noqa: PLC0415 -- only needed for this ravel/aggregate step

        counts_all = np.asarray(x).ravel()
        cell_uids_all = tuple(str(c) for c in adata.obs_names)

        cluster_col: str | None = None
        if cluster is not None:
            cluster_col = "canonical_cluster" if "canonical_cluster" in adata.obs.columns else "leiden"
            mask = (adata.obs[cluster_col].astype(str) == str(cluster)).to_numpy()
            cell_uids = tuple(c for c, m in zip(cell_uids_all, mask, strict=True) if m)
            counts = counts_all[mask]
        else:
            cell_uids = cell_uids_all
            counts = counts_all

        n_cells = int(counts.shape[0])
        return GeneCounts(
            var_name=var_name,
            cluster=cluster,
            cluster_col=cluster_col,
            cell_uids=cell_uids,
            counts=counts,
            total=float(counts.sum()) if n_cells else 0.0,
            mean=float(counts.mean()) if n_cells else 0.0,
            n_cells=n_cells,
        )


@dataclass(frozen=True, eq=False)
class GeneCounts:
    """Mirrors `peakatail_io.run.GeneCounts` -- see that class's docstring."""

    var_name: str
    cluster: str | None
    cluster_col: str | None
    cell_uids: tuple[str, ...]
    counts: Any
    total: float
    mean: float
    n_cells: int


def validate_run(run: Run, *, check_ledger_invariant: bool = True) -> None:
    """Thin wrapper around `peakatail_contract.validate()` that supplies the
    n_vars_clusters_h5ad invariant check from this Run's clusters.h5ad
    (opened once, lazily, via `open_clusters_h5ad()`), unless
    `check_ledger_invariant=False` -- see the real `peakatail_io.validate_run`
    docstring: engine's provenance ledger is being wired drop-site by
    drop-site, so the invariant only holds once every drop site is wired.
    Kept in sync with the real package's signature so `io_compat`'s
    stub-fallback path stays a drop-in replacement.

    Raises `peakatail_contract.ContractValidationError` on any violation;
    callers (the indexer) are responsible for catching it per-run so one bad
    run doesn't abort an entire `hub index` pass.
    """
    _contract_validate(
        manifest=run.manifest,
        pas_ledger=run.pas_ledger(),
        cell_ledger=run.cell_ledger(),
        findings=run.findings(),
        length_rows=run.length_rows(),
        n_vars_clusters_h5ad=run.n_vars() if check_ledger_invariant else None,
    )
