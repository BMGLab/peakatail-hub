#!/usr/bin/env python3
"""Generate a LARGE, contract-valid demo run for exploring the hub UI.

Unlike `make_fixtures.py` (a deliberately tiny 2-gene fixture the test suite
pins exact counts against), this writes a populated run -- dozens of genes,
~100 PAS, six clusters, hundreds of switch findings with a realistic spread
of effect sizes -- so the Browser/geneview/Findings views have something rich
to show, including many genuine HIGH-SCORE switches (low q + large
|delta_proportion|).

It is emitted to a SEPARATE directory (default: repo-root/demo_runs/
demo-cohort) and never touches packages/contract/fixtures, so the test
fixture and its pinned invariants are unaffected. Index it into the hub with:

    uv run hub index <this-run-dir>          # from backend/
or add its parent dir as a Source in the Dashboard.

The biology is SYNTHETIC but internally coherent: each gene gets a per-cluster
distal-usage fraction, the h5ad read counts are drawn to match it, and every
finding's delta_proportion/qvalue is derived from that same fraction -- so the
proportion bars, the diff overlays, and the Findings table all agree. This is
demo data, clearly labelled as such in the run manifest; it is not real
experimental output.

Usage (from packages/contract/):
    uv run python scripts/make_demo_run.py [OUTPUT_DIR]
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import numpy as np
import pandas as pd

from peakatail_contract import CONTRACT_VERSION
from peakatail_contract.ids import cell_uid, finding_uid
from peakatail_contract.models import (
    Artifact,
    CellLedgerRow,
    DatasetRef,
    Direction,
    FindingRow,
    Format,
    LengthRow,
    LengthStrategy,
    PasLedgerRow,
    RunManifest,
    Strategy,
    Tier,
)

# --------------------------------------------------------------------------
# Scale knobs -- big enough to feel like a real cohort, small enough to
# generate + index in a couple seconds.
# --------------------------------------------------------------------------
RUN_ID = "demo-cohort-0001"
N_GENES = 48
CLUSTERS = [f"cl_{i}" for i in range(6)]          # 6 canonical clusters
DATASETS = ["dsA", "dsB"]
CELLS_PER_CLUSTER_PER_DS = 15                      # 6 * 15 * 2 = 180 cells
STRATUM_LABEL = "Tumor_epithelial"
RNG = np.random.default_rng(7)

# Cluster "axis": clusters at the ends prefer the distal PAS most strongly,
# so an arm comparing cl_0 vs cl_5 yields the biggest (highest-score) switches.
_CLUSTER_AXIS = np.linspace(-1.0, 1.0, len(CLUSTERS))


# --------------------------------------------------------------------------
# Genes + PAS: each gene is a tandem-3'UTR locus with 2 PAS (proximal/distal);
# every ~4th gene gets a 3rd (mid) PAS. Two isoforms per gene (short covers
# proximal only; long covers all), so the isoform track has structure.
# --------------------------------------------------------------------------
def _gene_meta(gi: int) -> dict:
    chrom = f"chr{(gi % 6) + 1}"
    strand = "+" if gi % 2 == 0 else "-"
    g_start = 200_000 + gi * 20_000
    # strength of this gene's cluster-dependent switch (skewed so ~40% are
    # strong): amplitude of the distal-fraction swing across clusters.
    s = float(RNG.random()) ** 0.7
    amp = 0.12 + 0.40 * s
    sign = 1.0 if RNG.random() > 0.5 else -1.0
    has_mid = gi % 4 == 0
    return {
        "gi": gi,
        "gene_id": f"ENSDG{gi:08d}",
        "gene_name": f"GENE{gi:03d}",
        "chrom": chrom,
        "strand": strand,
        "g_start": g_start,
        "amp": amp,
        "sign": sign,
        "has_mid": has_mid,
    }


GENES = [_gene_meta(gi) for gi in range(N_GENES)]


def _distal_fraction(g: dict, cluster_idx: int) -> float:
    """Within-gene fraction of reads on the DISTAL PAS for this gene in this
    cluster -- the quantity the proportion bars and the switch deltas both
    derive from."""
    f = 0.5 + g["sign"] * g["amp"] * float(_CLUSTER_AXIS[cluster_idx])
    return float(min(0.92, max(0.08, f)))


# PAS spec per gene: proximal, (optional mid), distal -- positions inside the
# long isoform's terminal exon [g_start+500, g_start+1500].
def _pas_positions(g: dict) -> list[tuple[str, int]]:
    b = g["g_start"]
    out = [("proximal", b + 1000)]
    if g["has_mid"]:
        out.append(("mid", b + 1240))
    out.append(("distal", b + 1480))
    return out


pas_ledger_rows: list[PasLedgerRow] = []
pas_index: list[dict] = []  # parallel metadata (gene, role, unified id)
_pas_counter = 0
for g in GENES:
    for role, end in _pas_positions(g):
        _pas_counter += 1
        uid = f"u{_pas_counter}"
        tier = Tier.TIER_1 if role != "distal" else Tier.TIER_2
        pas_ledger_rows.append(
            PasLedgerRow(
                orig_pas_key=f"{DATASETS[0]}:{g['strand']}:{_pas_counter}",
                chrom=g["chrom"],
                start=end - 1,
                end=end,
                strand=g["strand"],
                unified_pas_id=uid,
                snap_distance_bp=int(RNG.integers(2, 25)),
                gene_id=g["gene_id"],
                gene_distance_bp=int(abs(end - (g["g_start"] + 1000))) + 20,
                tier=tier,
                last_stage="clustering",
                dropped_at="",
                drop_reason=None,
            )
        )
        pas_index.append({"gene": g, "role": role, "uid": uid, "end": end})

N_PAS = len(pas_ledger_rows)
UID_TO_POS = {p["uid"]: i for i, p in enumerate(pas_index)}


# --------------------------------------------------------------------------
# Cells: 6 clusters x 2 datasets x CELLS_PER_CLUSTER_PER_DS.
# --------------------------------------------------------------------------
_BC_ALPH = "ACGT"


def _barcode(n: int) -> str:
    s = ""
    for _ in range(12):
        s += _BC_ALPH[n % 4]
        n //= 4
    return s


cell_ledger_rows: list[CellLedgerRow] = []
cell_meta: list[dict] = []  # {ds, barcode, cluster, cluster_idx}
_bc = 1000
for ci, cluster in enumerate(CLUSTERS):
    for ds in DATASETS:
        for _ in range(CELLS_PER_CLUSTER_PER_DS):
            _bc += 1
            bc = _barcode(_bc)
            total_reads = int(RNG.integers(300, 900))
            cell_ledger_rows.append(
                CellLedgerRow(
                    barcode=bc,
                    dataset_id=ds,
                    total_reads=total_reads,
                    n_pas=int(RNG.integers(20, N_PAS)),
                    dropped_at="",
                    drop_reason=None,
                    cluster=str(ci),
                    canonical_cluster=cluster,
                )
                if "canonical_cluster" in CellLedgerRow.model_fields
                else CellLedgerRow(
                    barcode=bc,
                    dataset_id=ds,
                    total_reads=total_reads,
                    n_pas=int(RNG.integers(20, N_PAS)),
                    dropped_at="",
                    drop_reason=None,
                    cluster=str(ci),
                )
            )
            cell_meta.append({"ds": ds, "barcode": bc, "cluster": cluster, "cluster_idx": ci})

N_CELLS = len(cell_meta)


# --------------------------------------------------------------------------
# clusters.h5ad: X[cell, pas] read counts drawn to MATCH _distal_fraction, so
# the backend's within-gene proportion == the fraction we designed.
# --------------------------------------------------------------------------
def _write_clusters_h5ad(path: Path) -> None:
    import anndata as ad

    X = np.zeros((N_CELLS, N_PAS), dtype=np.float32)
    # group PAS by gene
    by_gene: dict[str, list[int]] = {}
    for i, p in enumerate(pas_index):
        by_gene.setdefault(p["gene"]["gene_id"], []).append(i)

    for cell_i, cm in enumerate(cell_meta):
        ci = cm["cluster_idx"]
        for gene_id, idxs in by_gene.items():
            g = pas_index[idxs[0]]["gene"]
            f_distal = _distal_fraction(g, ci)
            depth = int(RNG.integers(4, 16))  # reads for this gene in this cell
            # split depth across PAS: distal gets f_distal, proximal the rest,
            # mid (if any) shares the proximal pool.
            roles = [pas_index[i]["role"] for i in idxs]
            weights = []
            for role in roles:
                if role == "distal":
                    weights.append(f_distal)
                elif role == "proximal":
                    weights.append((1.0 - f_distal) * (0.6 if "mid" in roles else 1.0))
                else:  # mid
                    weights.append((1.0 - f_distal) * 0.4)
            w = np.array(weights, dtype=float)
            w = w / w.sum() if w.sum() > 0 else np.ones(len(idxs)) / len(idxs)
            counts = RNG.multinomial(depth, w)
            for k, i in enumerate(idxs):
                X[cell_i, i] = counts[k]

    obs = pd.DataFrame(
        {
            "dataset_id": [c["ds"] for c in cell_meta],
            "barcode": [c["barcode"] for c in cell_meta],
            "leiden": [str(c["cluster_idx"]) for c in cell_meta],
            "canonical_cluster": [c["cluster"] for c in cell_meta],
            "n_genes": [int(x) for x in (X > 0).sum(axis=1)],
            "total_counts": [float(x) for x in X.sum(axis=1)],
        },
        index=[cell_uid(c["ds"], c["barcode"]) for c in cell_meta],
    )
    var = pd.DataFrame(
        {
            "gene_id": [p["gene"]["gene_id"] for p in pas_index],
            "chrom": [p["gene"]["chrom"] for p in pas_index],
            "end": [p["end"] for p in pas_index],
            "strand": [p["gene"]["strand"] for p in pas_index],
        },
        index=[p["uid"] for p in pas_index],
    )
    adata = ad.AnnData(X=X, obs=obs, var=var)
    adata.obsm["X_umap"] = RNG.normal(size=(N_CELLS, 2)).astype(np.float32)
    adata.write_h5ad(path)


# --------------------------------------------------------------------------
# findings_long: switch findings derived from the SAME distal fractions.
# For each gene, three arms (extreme -> mild) x {fisher, nb_pairwise} on the
# distal PAS (and the proximal PAS, complementary), plus one nb_multi omnibus.
# --------------------------------------------------------------------------
_ARMS = [(0, 5), (1, 4), (2, 3)]  # cluster index pairs, extreme first


def _q_from_delta(abs_delta: float) -> float:
    q = 0.5 * math.exp(-8.0 * abs_delta) * (0.6 + 0.8 * float(RNG.random()))
    return float(min(0.999, max(1e-6, q)))


finding_rows: list[FindingRow] = []
cluster_cell_counts = {ci: sum(1 for c in cell_meta if c["cluster_idx"] == ci) for ci in range(len(CLUSTERS))}

for p in pas_index:
    if p["role"] == "mid":
        continue  # findings on proximal/distal only, keeps it readable
    g = p["gene"]
    puid = pas_ledger_rows[UID_TO_POS[p["uid"]]].pas_uid
    for a, b in _ARMS:
        f_a = _distal_fraction(g, a)
        f_b = _distal_fraction(g, b)
        # delta on THIS pas: distal moves with the fraction, proximal opposite.
        delta = (f_a - f_b) if p["role"] == "distal" else (f_b - f_a)
        abs_d = abs(delta)
        q = _q_from_delta(abs_d)
        if delta > 0.05:
            direction = Direction.LENGTHEN if p["role"] == "distal" else Direction.SHORTEN
        elif delta < -0.05:
            direction = Direction.SHORTEN if p["role"] == "distal" else Direction.LENGTHEN
        else:
            direction = Direction.FLAT
        log2fc = float(np.sign(delta) * min(3.0, abs_d * 5.0))
        arm = f"{CLUSTERS[a]}_vs_{CLUSTERS[b]}"
        for strategy in (Strategy.FISHER, Strategy.NB_PAIRWISE):
            fuid = finding_uid(
                resolved_label=STRATUM_LABEL,
                var_name=p["uid"],
                strategy=strategy.value,
                arm=arm,
                pas_uid_value=puid,
            )
            finding_rows.append(
                FindingRow(
                    finding_uid=fuid,
                    pas_uid=puid,
                    gene_id=g["gene_id"],
                    canonical_cluster=CLUSTERS[a],
                    comparison_cluster=CLUSTERS[b],
                    celltype=STRATUM_LABEL,
                    strategy=strategy,
                    arm=arm,
                    direction=direction,
                    utr_class="tandem_utr",
                    qvalue=q if strategy == Strategy.FISHER else min(0.999, q * 1.3),
                    pvalue=q * 0.6,
                    delta_proportion=float(delta),
                    log2fc=log2fc,
                    odds_ratio=float(math.exp(log2fc)),
                    n_cells=cluster_cell_counts[a] + cluster_cell_counts[b],
                    n_reads=int(RNG.integers(150, 600)),
                    n_cells_subject=cluster_cell_counts[a],
                    n_cells_comparison=cluster_cell_counts[b],
                    n_reads_subject=int(RNG.integers(80, 300)),
                    n_reads_comparison=int(RNG.integers(80, 300)),
                )
            )
    # nb_multi omnibus on the distal PAS (comparison_cluster=None)
    if p["role"] == "distal":
        spread = max(_distal_fraction(g, ci) for ci in range(len(CLUSTERS))) - min(
            _distal_fraction(g, ci) for ci in range(len(CLUSTERS))
        )
        q = _q_from_delta(spread)
        fuid = finding_uid(
            resolved_label=STRATUM_LABEL,
            var_name=p["uid"],
            strategy=Strategy.NB_MULTI.value,
            arm="omnibus",
            pas_uid_value=puid,
        )
        finding_rows.append(
            FindingRow(
                finding_uid=fuid,
                pas_uid=puid,
                gene_id=g["gene_id"],
                canonical_cluster="cl_0",
                comparison_cluster=None,
                celltype=STRATUM_LABEL,
                strategy=Strategy.NB_MULTI,
                arm="omnibus",
                direction=Direction.UNDETERMINED,
                utr_class="tandem_utr",
                qvalue=q,
                pvalue=q * 0.6,
                delta_proportion=float(spread),
                log2fc=None,
                odds_ratio=None,
                n_cells=N_CELLS,
                n_reads=int(RNG.integers(300, 900)),
                n_cells_subject=cluster_cell_counts[0],
                n_cells_comparison=None,
                n_reads_subject=int(RNG.integers(100, 400)),
                n_reads_comparison=None,
            )
        )


# --------------------------------------------------------------------------
# length_long: classic (per gene per cluster-representative cell) + shannon +
# proportion (per PAS per cell, subsampled to keep the parquet small).
# --------------------------------------------------------------------------
length_rows: list[LengthRow] = []
# one representative cell per (dataset, cluster) keeps classic/shannon compact
# while still populating the PDUI-by-stage scatter across all clusters.
rep_cells = {}
for cm in cell_meta:
    rep_cells.setdefault((cm["ds"], cm["cluster_idx"]), cm)

for g in GENES:
    for (ds, ci), cm in rep_cells.items():
        c_uid = cell_uid(ds, cm["barcode"])
        canon = CLUSTERS[ci]
        f_distal = _distal_fraction(g, ci)
        length_rows.append(
            LengthRow(
                strategy=LengthStrategy.CLASSIC,
                gene_id=g["gene_id"],
                transcript_id=g["gene_id"].replace("ENSDG", "ENSDT"),
                cell_uid=c_uid,
                canonical_cluster=canon,
                value=float(f_distal),  # pdui = distal fraction
                direction=Direction.LENGTHEN if f_distal > 0.5 else Direction.SHORTEN,
                direction_basis="structural",
            )
        )
        length_rows.append(
            LengthRow(
                strategy=LengthStrategy.SHANNON,
                gene_id=g["gene_id"],
                cell_uid=c_uid,
                canonical_cluster=canon,
                value=float(-(f_distal * math.log(f_distal + 1e-9) + (1 - f_distal) * math.log(1 - f_distal + 1e-9))),
                direction=Direction.UNDETERMINED,
                direction_basis="structural",
            )
        )
        for rank, p in enumerate([pp for pp in pas_index if pp["gene"]["gene_id"] == g["gene_id"]]):
            is_distal = p["role"] == "distal"
            length_rows.append(
                LengthRow(
                    strategy=LengthStrategy.PROPORTION,
                    gene_id=g["gene_id"],
                    transcript_id=g["gene_id"].replace("ENSDG", "ENSDT"),
                    cell_uid=c_uid,
                    canonical_cluster=canon,
                    value=float(f_distal if is_distal else (1 - f_distal) / (1 if not g["has_mid"] else 2)),
                    pas_uid=pas_ledger_rows[UID_TO_POS[p["uid"]]].pas_uid,
                    rank=rank,
                    direction=Direction.LENGTHEN if (is_distal and f_distal > 0.5) else Direction.SHORTEN,
                    direction_basis="structural",
                )
            )


# --------------------------------------------------------------------------
# Writers (same formats as make_fixtures.py).
# --------------------------------------------------------------------------
def _write_pas_ledger_tsv(path: Path) -> None:
    df = pd.DataFrame([r.model_dump(mode="json") for r in pas_ledger_rows])
    df["tier"] = df["tier"].fillna("")
    df["pas_uid"] = [r.pas_uid for r in pas_ledger_rows]
    df.to_csv(path, sep="\t", index=False)


def _write_cell_ledger_tsv(path: Path) -> None:
    df = pd.DataFrame([r.model_dump(mode="json") for r in cell_ledger_rows])
    df["cell_uid"] = [r.cell_uid for r in cell_ledger_rows]
    df.to_csv(path, sep="\t", index=False)


def _write_findings_parquet(path: Path) -> None:
    pd.DataFrame([r.model_dump(mode="json") for r in finding_rows]).to_parquet(path, index=False)


def _write_length_parquet(path: Path) -> None:
    pd.DataFrame([r.model_dump(mode="json") for r in length_rows]).to_parquet(path, index=False)


def _write_pasbed(path: Path) -> None:
    lines = [f"{r.chrom}\t{r.start}\t{r.end}\t{i + 1}\t0\t{r.strand}" for i, r in enumerate(pas_ledger_rows)]
    path.write_text("\n".join(lines) + "\n")


def _write_gtf(path: Path) -> None:
    lines = ["# PeakATail hub DEMO run GTF -- synthetic, generated by make_demo_run.py"]
    for g in GENES:
        b = g["g_start"]
        long_exons = [(b, b + 300), (b + 500, b + 1500)]
        short_exons = [(b, b + 300), (b + 500, b + 1010)]
        transcripts = [
            (g["gene_id"].replace("ENSDG", "ENSDT") + "L", long_exons),
            (g["gene_id"].replace("ENSDG", "ENSDT") + "S", short_exons),
        ]
        all_exons = [e for _, exons in transcripts for e in exons]
        g_start = min(e[0] for e in all_exons)
        g_end = max(e[1] for e in all_exons)
        gene_attrs = f'gene_id "{g["gene_id"]}"; gene_name "{g["gene_name"]}";'
        lines.append(f'{g["chrom"]}\tdemo\tgene\t{g_start}\t{g_end}\t.\t{g["strand"]}\t.\t{gene_attrs}')
        for tid, exons in transcripts:
            t_attrs = f'gene_id "{g["gene_id"]}"; gene_name "{g["gene_name"]}"; transcript_id "{tid}";'
            lines.append(f'{g["chrom"]}\tdemo\ttranscript\t{min(e[0] for e in exons)}\t{max(e[1] for e in exons)}\t.\t{g["strand"]}\t.\t{t_attrs}')
            for es, ee in exons:
                lines.append(f'{g["chrom"]}\tdemo\texon\t{es}\t{ee}\t.\t{g["strand"]}\t.\t{t_attrs}')
    path.write_text("\n".join(lines) + "\n")


def _write_run_manifest(out_dir: Path, artifact_paths: dict[str, Path]) -> None:
    def art(key, stage, fmt, schema, counts):
        return Artifact(
            path=str(artifact_paths[key].relative_to(out_dir)),
            stage=stage,
            format=fmt,
            schema_name=schema,
            schema_version=CONTRACT_VERSION,
            entity_counts=counts,
        )

    manifest = RunManifest(
        run_id=RUN_ID,
        root=str(out_dir),
        contract_version=CONTRACT_VERSION,
        datasets=[
            DatasetRef(dataset_id="dsA", bam_paths=["dsA.bam"], label="Demo cohort A (tumor epithelial) [SYNTHETIC]"),
            DatasetRef(dataset_id="dsB", bam_paths=["dsB.bam"], label="Demo cohort B (tumor epithelial) [SYNTHETIC]"),
        ],
        resolved_config={
            "directories": {"output_dir": str(out_dir), "bam_dir": None, "gtf_dir": "genes.gtf", "atlas": None, "atlas_distance": None,
                            "datasets": [{"id": "dsA", "bams": ["dsA.bam"]}, {"id": "dsB", "bams": ["dsB.bam"]}], "filenames": {}},
            "variables": {"seqlen": 100, "cb_len": 16, "barcode_tag": "CB", "default_threshold": 0.05, "merge_len": 24, "min_pas_spacing": 10, "min_pas_prominence": 2},
            "filters": {"min_read": 50, "min_cells": 2, "min_genes": None, "min_pas_per_cell": 2},
            "args": {"merge_strategy": "before", "max_gene_distance": 5000, "note": "SYNTHETIC DEMO DATA -- not a real experiment"},
        },
        stratum_to_label={"dsA": STRATUM_LABEL, "dsB": STRATUM_LABEL},
        artifacts=[
            art("pas_ledger", "provenance", Format.TSV, "PasLedgerRow", {"n_rows": len(pas_ledger_rows), "n_surviving": N_PAS}),
            art("cell_ledger", "provenance", Format.TSV, "CellLedgerRow", {"n_rows": len(cell_ledger_rows), "n_surviving": N_CELLS}),
            art("findings", "switch_diff", Format.PARQUET, "FindingRow", {"n_rows": len(finding_rows)}),
            art("length", "switch_length", Format.PARQUET, "LengthRow", {"n_rows": len(length_rows)}),
            art("clusters_h5ad", "clustering", Format.H5AD, "clusters.h5ad", {"n_obs": N_CELLS, "n_vars": N_PAS}),
            art("pasbed", "per_dataset_beds", Format.BED, "pasbed.bed", {"n_pas": N_PAS}),
        ],
        entity_counts={"n_pas": N_PAS, "n_cells": N_CELLS, "n_genes": N_GENES, "n_datasets": len(DATASETS),
                       "n_findings": len(finding_rows), "n_length_rows": len(length_rows)},
    )
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest.model_dump(), indent=2, sort_keys=True) + "\n")


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[3] / "demo_runs" / "demo-cohort"
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_paths = {
        "pas_ledger": out_dir / "pas_ledger.tsv",
        "cell_ledger": out_dir / "cell_ledger.tsv",
        "findings": out_dir / "findings_long.parquet",
        "length": out_dir / "length_long.parquet",
        "clusters_h5ad": out_dir / "clusters.h5ad",
        "pasbed": out_dir / "pasbed.bed",
    }
    _write_pas_ledger_tsv(artifact_paths["pas_ledger"])
    _write_cell_ledger_tsv(artifact_paths["cell_ledger"])
    _write_findings_parquet(artifact_paths["findings"])
    _write_length_parquet(artifact_paths["length"])
    _write_pasbed(artifact_paths["pasbed"])
    _write_clusters_h5ad(artifact_paths["clusters_h5ad"])
    _write_gtf(out_dir / "genes.gtf")
    _write_run_manifest(out_dir, artifact_paths)
    print(f"wrote demo run '{RUN_ID}' to {out_dir}")
    print(f"  {N_GENES} genes, {N_PAS} PAS, {N_CELLS} cells, {len(finding_rows)} findings, {len(length_rows)} length rows")


if __name__ == "__main__":
    main()
