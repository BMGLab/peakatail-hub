from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from peakatail_contract.models import CellLedgerRow, FindingRow, LengthRow, PasLedgerRow, RunManifest

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _none_if_nan(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _clean_record(rec: dict) -> dict:
    return {k: _none_if_nan(v) for k, v in rec.items()}


def _load_pas_ledger() -> list[PasLedgerRow]:
    df = pd.read_csv(FIXTURES_DIR / "pas_ledger.tsv", sep="\t")
    rows = []
    for raw in df.to_dict(orient="records"):
        rec = _clean_record(raw)
        rec.pop("pas_uid", None)  # computed field, not a constructor arg
        if rec.get("dropped_at") is None:
            rec["dropped_at"] = ""
        for k in ("snap_distance_bp", "gene_distance_bp"):
            rec[k] = int(rec[k]) if rec.get(k) is not None else None
        rec["start"] = int(rec["start"])
        rec["end"] = int(rec["end"])
        if rec.get("gene_id") is None:
            rec["gene_id"] = ""
        rows.append(PasLedgerRow(**rec))
    return rows


def _load_cell_ledger() -> list[CellLedgerRow]:
    df = pd.read_csv(FIXTURES_DIR / "cell_ledger.tsv", sep="\t")
    rows = []
    for raw in df.to_dict(orient="records"):
        rec = _clean_record(raw)
        rec.pop("cell_uid", None)
        if rec.get("dropped_at") is None:
            rec["dropped_at"] = ""
        if rec.get("cluster") is not None:
            rec["cluster"] = str(rec["cluster"])
        rows.append(CellLedgerRow(**rec))
    return rows


def _load_findings() -> list[FindingRow]:
    df = pd.read_parquet(FIXTURES_DIR / "findings_long.parquet")
    return [FindingRow(**_clean_record(rec)) for rec in df.to_dict(orient="records")]


def _load_length_rows() -> list[LengthRow]:
    df = pd.read_parquet(FIXTURES_DIR / "length_long.parquet")
    return [LengthRow(**_clean_record(rec)) for rec in df.to_dict(orient="records")]


def _load_manifest() -> RunManifest:
    data = json.loads((FIXTURES_DIR / "run_manifest.json").read_text())
    return RunManifest(**data)


@pytest.fixture()
def fixture_manifest() -> RunManifest:
    return _load_manifest()


@pytest.fixture()
def fixture_pas_ledger() -> list[PasLedgerRow]:
    return _load_pas_ledger()


@pytest.fixture()
def fixture_cell_ledger() -> list[CellLedgerRow]:
    return _load_cell_ledger()


@pytest.fixture()
def fixture_findings() -> list[FindingRow]:
    return _load_findings()


@pytest.fixture()
def fixture_length_rows() -> list[LengthRow]:
    return _load_length_rows()


@pytest.fixture()
def fixture_n_vars_clusters_h5ad() -> int:
    import anndata as ad

    adata = ad.read_h5ad(FIXTURES_DIR / "clusters.h5ad")
    return adata.n_vars


@pytest.fixture()
def fixture_n_obs_clusters_h5ad() -> int:
    import anndata as ad

    adata = ad.read_h5ad(FIXTURES_DIR / "clusters.h5ad")
    return adata.n_obs
