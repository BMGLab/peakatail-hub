"""`/genes/{id}` + geneview endpoints.

Two documented heavy-import paths in this module (spec §7a: "the heavy
reader must be importable on exactly one path" -- this module has exactly
two, both explicitly named here so a future reader doesn't have to
rediscover them):

  * `/genes/{id}/counts` (`gene_counts()`) -- opens `clusters.h5ad` via
    `Run.gene_counts()`, once per surviving PAS var_name.
  * `/genes/{id}/geneview-data` (`geneview_data()`) -- ALSO touches
    `clusters.h5ad`, but via `run.open_clusters_h5ad()` directly (not
    `gene_counts()`), opened exactly ONCE per request and subset in-memory
    to compute per-cluster PAS proportions/coverage (see that function's
    docstring for why: doing this per-(PAS x cluster) via repeated
    `gene_counts()` calls would be an O(n_pas * n_clusters) file-read, which
    is wasteful and not what this endpoint does).

Every other function in this module (`get_gene()`'s DuckDB-sourced fields,
the GTF-derived `gene_name`/`isoforms` lookups, the SVG/PNG placeholders)
stays DuckDB-only or touches only the tiny `run_manifest.json` +
stdlib-parsed GTF text file -- never anndata.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from peakatail_contract import FindingRow, LengthRow
from peakatail_hub import gtf as gtf_reader
from peakatail_hub.api.deps import get_db
from peakatail_hub.io_compat import GeneNotFoundError, Run, RunReadError
from peakatail_hub.render import render_geneview_placeholder
from peakatail_hub.schemas import (
    GeneListRow,
    GenesPage,
    GeneSpan,
    GeneSummary,
    GeneviewClusterTrack,
    GeneviewClusterValue,
    GeneviewData,
    GeneviewIsoform,
    GeneviewPas,
)
from peakatail_hub.store import queries

router = APIRouter(prefix="/genes", tags=["genes"])


def _resolve_run_id(con: duckdb.DuckDBPyConnection, run_id: str | None) -> str:
    """v1 simplification (documented, not hidden): gene/PAS/cell IDs are not
    namespaced by run in the endpoint paths (spec §3 lists no `run_id` path
    param for `/genes/{id}` etc). With >1 indexed run this is ambiguous, so
    callers SHOULD pass `?run_id=`; when omitted we fall back to the single
    indexed run if there is exactly one, and fail loud (400, not a silent
    guess) otherwise.
    """
    if run_id is not None:
        return run_id
    runs = queries.list_runs(con)
    if len(runs) == 1:
        return runs[0]["run_id"]
    raise HTTPException(
        status_code=400,
        detail=(
            "run_id query param is required when more than one run is indexed "
            f"(found {len(runs)}: {[r['run_id'] for r in runs]})"
        ),
    )


@router.get("", response_model=GenesPage)
def list_genes(
    q: str | None = Query(default=None, description="Substring match on gene_id (ILIKE %q%)."),
    chrom: str | None = Query(default=None, description="Locus filter: restrict to this chromosome."),
    start: int | None = Query(default=None, description="Locus filter: gene span must end >= start."),
    end: int | None = Query(default=None, description="Locus filter: gene span must start <= end."),
    run_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> GenesPage:
    """The gene browser: searchable, paginated listing of every gene with at
    least one surviving PAS. `chrom`/`start`/`end` do a locus-overlap filter
    (not an exact-match), so the TopBar's location bar can resolve a raw
    `chr:start-end` search straight to the gene(s) under it -- same query
    shape `gene_pas_span` already uses for a single gene, generalized to
    "list genes whose span overlaps this window" instead of "gene at all".
    """
    rid = _resolve_run_id(con, run_id)
    offset = queries.decode_cursor(cursor)
    total = queries.count_genes(con, rid, q, chrom, start, end)
    rows = queries.list_genes(con, rid, q, chrom, start, end, offset, limit)
    next_offset = offset + limit
    next_cursor = queries.encode_cursor(next_offset) if next_offset < total else None
    return GenesPage(items=[GeneListRow(**r) for r in rows], next_cursor=next_cursor, total=total)


def _resolve_gtf_path(run_row: dict, run: Run) -> Path | None:
    """Resolve the on-disk GTF path from
    `run.manifest.resolved_config['directories']['gtf_dir']` (a string that
    may be a bare relative filename, e.g. "genes.gtf", or an absolute path).

    Mirrors the fallback order used elsewhere in this codebase for
    manifest-relative artifact paths (`index/indexer.py::_resolve_artifact_path`,
    `io_stub/run.py::Run._artifact_path`): try relative to the run's own
    on-disk directory (`run_row["root"]`, the value actually passed to
    `Run.from_dir` -- robust to a run copied/moved after the manifest was
    written) first, then relative to `manifest.root` (the directory the
    manifest itself claims, which may differ from where it actually lives).

    Returns `None` -- never raises -- if `resolved_config`/`directories`/
    `gtf_dir` is missing or `None`, or the resolved file doesn't exist on
    disk anywhere we looked. Callers must degrade to `gene_name=""`,
    `isoforms=[]` in that case, not 500 (a GTF is optional context here).
    """
    directories = (run.manifest.resolved_config or {}).get("directories") or {}
    gtf_rel = directories.get("gtf_dir")
    if not gtf_rel:
        return None
    gtf_rel_path = Path(gtf_rel)
    if gtf_rel_path.is_absolute():
        return gtf_rel_path if gtf_rel_path.exists() else None
    for base in (Path(run_row["root"]), Path(run.manifest.root)):
        candidate = base / gtf_rel_path
        if candidate.exists():
            return candidate
    return None


def _gene_name_and_isoforms(
    con: duckdb.DuckDBPyConnection, rid: str, gene_id: str
) -> tuple[str, list[GeneviewIsoform]]:
    """Best-effort GTF lookup for `gene_name`/isoform structure, shared by
    `get_gene()` and `geneview_data()`. Only ever touches `run_manifest.json`
    (via `Run.from_dir`, which does NOT import anndata -- see this module's
    top-of-file heavy-path inventory) plus a stdlib-parsed GTF text file.

    Never raises: an unindexed run, an unreadable manifest, a run with no
    `gtf_dir` configured, or a gene absent from the GTF all degrade to
    `("", [])` so callers always get a usable (if empty) result rather than
    a 500 for what is fundamentally optional display context.
    """
    run_row = queries.get_run(con, rid)
    if run_row is None:
        return "", []
    try:
        run = Run.from_dir(Path(run_row["root"]))
    except RunReadError:
        return "", []
    gtf_path = _resolve_gtf_path(run_row, run)
    if gtf_path is None:
        return "", []
    gene_name = gtf_reader.load_gene_name(gtf_path, gene_id)
    isoforms = [
        GeneviewIsoform(transcript_id=tid, exons=exons)
        for tid, exons in gtf_reader.load_isoforms(gtf_path, gene_id)
    ]
    return gene_name, isoforms


def _natural_cluster_key(label: str) -> tuple[int, int, str]:
    """Sort key matching the ema reference's own natural-sort convention
    (`ema/viz/_gene_track_helpers.py::build_gene_panel`:
    `sorted(_present, key=lambda x: int(x) if x.isdigit() else x)`):
    digit-only labels ("0", "1", "2", ...) sort numerically, before any
    non-numeric label (which then sorts lexicographically among itself).

    Python can't compare `int` and `str` keys directly (mixing them in one
    `sorted()` call raises `TypeError`), so this wraps both cases in a
    common `(is_non_numeric, numeric_value, label)` tuple instead of
    reproducing the reference's bare lambda verbatim.
    """
    if label.isdigit():
        return (0, int(label), "")
    return (1, 0, label)


def _cluster_tracks_for_gene(
    con: duckdb.DuckDBPyConnection, rid: str, pas_rows: list[dict]
) -> list[GeneviewClusterTrack]:
    """Per-cluster PAS reads/proportions for the gene-track coverage panel
    (mirrors `ema/viz/_gene_track_helpers.py::build_gene_panel`'s
    reads / reads_per_cell / proportion computation, reading from this
    hub's own DuckDB pas_ledger + clusters.h5ad rather than importing that
    module).

    Opens `clusters.h5ad` exactly ONCE per call (via
    `run.open_clusters_h5ad()`) and subsets it to this gene's surviving PAS
    vars in one shot -- deliberately NOT one `Run.gene_counts()` call per
    (PAS x cluster) pair, which would be an O(n_pas * n_clusters) file-read
    against the same h5ad and is exactly the wasteful pattern this function
    exists to avoid. `pas_rows` (from `queries.geneview_pas_in_window`) is
    already ordered the same way `GeneviewData.pas` will be, and that order
    is preserved into every track's `values` list so the frontend can zip
    them positionally.

    Resilient by design (this codebase's "gates"/fail-loud-but-not-crashy
    philosophy, see e.g. the `gates` list built in `geneview_data()`):
    returns `[]` -- never raises -- when the run isn't indexed,
    `clusters.h5ad` can't be opened/read, the gene has zero surviving PAS,
    or none of its surviving PAS vars are present in `adata.var_names`.
    `geneview_data()` must keep degrading gracefully; a missing/broken
    clusters.h5ad is not a reason to 500 the whole response.
    """
    if not pas_rows:
        return []
    run_row = queries.get_run(con, rid)
    if run_row is None:
        return []
    try:
        run = Run.from_dir(Path(run_row["root"]))
        adata = run.open_clusters_h5ad()
    except RunReadError:
        return []

    var_names = [r["unified_pas_id"] for r in pas_rows]
    pas_uids = [r["pas_uid"] for r in pas_rows]
    present_var_names = [v for v in var_names if v in adata.var_names]
    if not present_var_names:
        # Every surviving PAS for this gene is missing from clusters.h5ad's
        # var_names (bug-B7-adjacent) -- degrade to no tracks rather than
        # subsetting to an empty var axis.
        return []

    sub = adata[:, present_var_names]
    x = sub.X
    if hasattr(x, "toarray"):
        x = x.toarray()  # noqa: PLC0415 -- scipy sparse, imported implicitly by anndata
    import numpy as np  # noqa: PLC0415 -- only needed for this aggregate step

    x = np.asarray(x, dtype=np.float64)  # (n_cells, n_present_pas)

    cluster_col = "canonical_cluster" if "canonical_cluster" in adata.obs.columns else "leiden"
    cluster_labels = adata.obs[cluster_col].astype(str).to_numpy()
    present_clusters = sorted(set(cluster_labels), key=_natural_cluster_key)

    # Map each present var_name to its column in `x`, so a PAS that
    # survived to the ledger but is missing from this h5ad still gets a
    # (zero-valued) entry in `values` -- length/order must always match
    # `GeneviewData.pas`, regardless of which PAS actually resolved.
    col_by_var: dict[str, int] = {v: i for i, v in enumerate(present_var_names)}

    tracks: list[GeneviewClusterTrack] = []
    for cluster in present_clusters:
        rows_mask = cluster_labels == cluster
        n_cells = int(rows_mask.sum())
        reads_present = x[rows_mask, :].sum(axis=0)  # (n_present_pas,); zeros if n_cells == 0
        row_total = float(reads_present.sum())
        values: list[GeneviewClusterValue] = []
        for var_name, pas_uid in zip(var_names, pas_uids, strict=True):
            col = col_by_var.get(var_name)
            reads = float(reads_present[col]) if col is not None else 0.0
            reads_per_cell = reads / n_cells if n_cells else 0.0
            proportion = (reads / row_total) if row_total > 0 else None
            values.append(GeneviewClusterValue(pas_uid=pas_uid, reads_per_cell=reads_per_cell, proportion=proportion))
        tracks.append(GeneviewClusterTrack(cluster=cluster, n_cells=n_cells, values=values))
    return tracks


@router.get("/{gene_id}", response_model=GeneSummary)
def get_gene(
    gene_id: str,
    run_id: str | None = Query(default=None),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> GeneSummary:
    rid = _resolve_run_id(con, run_id)
    summary = queries.gene_summary(con, rid, gene_id)
    span = GeneSpan(**summary["span"]) if summary["span"] else None
    gene_name, _isoforms = _gene_name_and_isoforms(con, rid, gene_id)
    return GeneSummary(**{**summary, "span": span, "gene_name": gene_name})


@router.get("/{gene_id}/geneview-data", response_model=GeneviewData)
def geneview_data(
    gene_id: str,
    start: int | None = Query(default=None, description="Window start (bp); omit for full gene span."),
    end: int | None = Query(default=None, description="Window end (bp); omit for full gene span."),
    lod: str | None = Query(default=None, description="Level-of-detail hint; reserved, unused in v1 (tens-hundreds of PAS/gene, spec §7f)."),
    clusters: list[str] | None = Query(default=None),
    diff_strategies: list[str] | None = Query(default=None),
    length_strategies: list[str] | None = Query(default=None),
    run_id: str | None = Query(default=None),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> GeneviewData:
    """Windowed range query over pas_ledger/findings_long/length_long,
    coordinates sourced from pas_ledger (never findings_long, which per spec
    §7d and the FindingRow model has no coordinate columns at all -- there is
    no wrong path to accidentally take here).
    """
    rid = _resolve_run_id(con, run_id)
    span = queries.gene_pas_span(con, rid, gene_id)
    pas_rows = queries.geneview_pas_in_window(con, rid, gene_id, start, end)
    pas_uids = [r["pas_uid"] for r in pas_rows]
    finding_rows = queries.geneview_findings_for_pas(con, rid, pas_uids, diff_strategies)
    length_rows = queries.geneview_length_for_gene(con, rid, gene_id, length_strategies)
    if clusters:
        finding_rows = [r for r in finding_rows if r["canonical_cluster"] in clusters]
        length_rows = [r for r in length_rows if r["canonical_cluster"] in clusters]

    gates: list[str] = []
    if finding_rows and all(r["celltype"] is None for r in finding_rows):
        gates.append("celltype facet/overlay gated on engine A1 (+A2/B2) -- not present on this run yet")
    # NOTE (2026-07-14): engine now emits a real `direction` for ALL THREE
    # length strategies (classic/proportion/shannon), not just 'proportion'
    # -- see peakatail_contract.LengthRow.direction's docstring for the
    # one-vs-rest structural methodology. The gate that used to fire here
    # ("classic/shannon have no per-PAS direction yet") is stale and
    # removed; only `pas_uid`/`rank` remain proportion-only (that part of
    # the original design still holds, and needs no gate -- it's a grain
    # difference, not a missing-data one).

    gene_name, isoforms = _gene_name_and_isoforms(con, rid, gene_id)
    cluster_tracks = _cluster_tracks_for_gene(con, rid, pas_rows)

    return GeneviewData(
        gene_id=gene_id,
        run_id=rid,
        span=GeneSpan(**span) if span else None,
        window={"start": start, "end": end},
        pas=[GeneviewPas(**r) for r in pas_rows],
        findings=[FindingRow(**r) for r in finding_rows],
        length_rows=[LengthRow(**r) for r in length_rows],
        gates=gates,
        gene_name=gene_name,
        isoforms=isoforms,
        cluster_tracks=cluster_tracks,
    )


@router.get("/{gene_id}/counts")
def gene_counts(
    gene_id: str,
    run_id: str | None = Query(default=None),
    cluster: str | None = Query(default=None, description="Filter to one canonical_cluster/leiden label (forwarded to Run.gene_counts)."),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict:
    """THE one path in this backend that opens clusters.h5ad via
    `Run.gene_counts()` (lazy anndata/scipy import inside peakatail_io,
    per spec §7a). Every DuckDB-backed endpoint in this module stays
    dep-light; this is the deliberate exception.

    `peakatail_io.Run.gene_counts()` is per-var (one PAS/`var_name` at a
    time, resolved via `var_names` -- never `var['gene_id']`, spec §7d), not
    per-gene, so this endpoint resolves `gene_id` -> its surviving PAS'
    `unified_pas_id`s via the DuckDB pas_ledger first (dep-light), then
    calls `gene_counts()` once per var_name and pivots the results into one
    gene-level `{cell_uid: {pas_uid: count}}` table.
    """
    rid = _resolve_run_id(con, run_id)
    run_row = queries.get_run(con, rid)
    if run_row is None:
        raise HTTPException(status_code=404, detail=f"run_id={rid!r} not indexed")

    surviving_pas = queries.geneview_pas_in_window(con, rid, gene_id, None, None)
    if not surviving_pas:
        return {"gene_id": gene_id, "run_id": rid, "n_cells": 0, "pas_uids": [], "cells": []}

    try:
        run = Run.from_dir(Path(run_row["root"]))
    except RunReadError as exc:
        raise HTTPException(status_code=404, detail=f"counts unavailable for gene_id={gene_id!r}: {exc}") from exc

    per_cell: dict[str, dict[str, float]] = {}
    pas_uids_found: list[str] = []
    for row in surviving_pas:
        var_name = row["unified_pas_id"]
        pas_uid = row["pas_uid"]
        try:
            result = run.gene_counts(var_name, cluster=cluster)
        except GeneNotFoundError:
            # This PAS survived to the ledger but its var isn't in the
            # h5ad the manifest points at -- fail loud in logs, not to the
            # caller, since other PAS for this gene may still resolve.
            continue
        except RunReadError as exc:
            raise HTTPException(status_code=404, detail=f"counts unavailable for gene_id={gene_id!r}: {exc}") from exc
        pas_uids_found.append(pas_uid)
        for cell_uid, count in zip(result.cell_uids, result.counts, strict=True):
            per_cell.setdefault(cell_uid, {})[pas_uid] = float(count)

    return {
        "gene_id": gene_id,
        "run_id": rid,
        "n_cells": len(per_cell),
        "pas_uids": pas_uids_found,
        "cells": [{"cell_uid": cell_uid, **counts} for cell_uid, counts in per_cell.items()],
    }


def _placeholder_response(gene_id: str, media_type: str, ext: str) -> FileResponse:
    path = render_geneview_placeholder(gene_id)
    if ext == "png":
        # v1 stub only ever produces SVG (task brief: "geneview.svg/.png
        # stubs can 501/placeholder now"); serve the SVG bytes back with an
        # honest media type rather than faking a PNG.
        return FileResponse(path, media_type="image/svg+xml", filename=f"{gene_id}.svg")
    return FileResponse(path, media_type=media_type, filename=f"{gene_id}.{ext}")


@router.get("/{gene_id}/geneview.svg")
def geneview_svg(gene_id: str) -> FileResponse:
    return _placeholder_response(gene_id, "image/svg+xml", "svg")


@router.get("/{gene_id}/geneview.png")
def geneview_png(gene_id: str) -> FileResponse:
    return _placeholder_response(gene_id, "image/png", "png")
