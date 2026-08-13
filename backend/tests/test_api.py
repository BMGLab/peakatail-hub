"""End-to-end router tests against the fixture run, via FastAPI's TestClient
(the `client` fixture in conftest.py points HUB_DB_PATH/HUB_CACHE_DIR at
tmp_path and indexes packages/contract/fixtures before the app starts).
"""

from __future__ import annotations


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_runs(client, fixture_run_id: str):
    resp = client.get("/runs")
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 1
    assert runs[0]["run_id"] == fixture_run_id
    assert runs[0]["n_pas"] == 4  # manifest entity_counts (surviving only)


def test_run_qc_funnel(client, fixture_run_id: str):
    resp = client.get(f"/runs/{fixture_run_id}/qc")
    assert resp.status_code == 200
    qc = resp.json()
    assert qc["n_pas_total"] == 6
    assert qc["n_pas_survived"] == 4
    assert qc["n_cells_total"] == 7
    assert qc["n_cells_survived"] == 6
    assert qc["per_sample_stats_available"] is False
    stages = {s["stage"]: s["dropped"] for s in qc["pas_drop_by_stage"]}
    assert stages["atlas_snap"] == 1
    assert stages["pas_gene_assignment"] == 1
    cell_stages = {s["stage"]: s["dropped"] for s in qc["cell_drop_by_stage"]}
    assert cell_stages["cb_filter"] == 1


def test_run_qc_404_for_unknown_run(client):
    resp = client.get("/runs/does-not-exist/qc")
    assert resp.status_code == 404


def test_findings_list_and_pagination(client):
    resp = client.get("/findings", params={"limit": 2})
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 4
    assert len(page["items"]) == 2
    assert page["next_cursor"] is not None

    resp2 = client.get("/findings", params={"limit": 2, "cursor": page["next_cursor"]})
    page2 = resp2.json()
    assert len(page2["items"]) == 2
    assert page2["next_cursor"] is None

    uids_page1 = {f["finding_uid"] for f in page["items"]}
    uids_page2 = {f["finding_uid"] for f in page2["items"]}
    assert uids_page1.isdisjoint(uids_page2)
    assert len(uids_page1 | uids_page2) == 4


def test_findings_filter_by_strategy(client):
    resp = client.get("/findings", params={"strategy": "fisher"})
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 2
    assert all(f["strategy"] == "fisher" for f in page["items"])


def test_findings_facets_reconcile(client):
    resp = client.get("/findings/facets")
    assert resp.status_code == 200
    facets = resp.json()
    assert facets["total"] == 4
    assert sum(v["count"] for v in facets["strategy"]) == 4
    assert sum(v["count"] for v in facets["direction"]) == 4


def test_finding_detail_and_404(client):
    listing = client.get("/findings").json()
    finding_uid = listing["items"][0]["finding_uid"]
    resp = client.get(f"/findings/{finding_uid}")
    assert resp.status_code == 200
    assert resp.json()["finding_uid"] == finding_uid

    resp404 = client.get("/findings/does-not-exist")
    assert resp404.status_code == 404


def test_gene_summary(client):
    resp = client.get("/genes/ENSG00000000001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_pas"] == 2
    assert body["span"]["chrom"] == "chr1"
    assert body["span"]["start"] == 999
    assert body["span"]["end"] == 1500
    assert body["gene_name"] == "TESTA1"


def test_geneview_data_sources_coords_from_ledger_not_findings(client):
    resp = client.get("/genes/ENSG00000000001/geneview-data")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["pas"]) == 2
    # FindingRow (spec §7d) deliberately has no coordinate fields at all --
    # confirm the response's pas coords came from the ledger-backed `pas`
    # list, and findings carry none.
    for f in body["findings"]:
        assert "chrom" not in f and "start" not in f and "end" not in f
    assert {f["pas_uid"] for f in body["findings"]} <= {p["pas_uid"] for p in body["pas"]}


def test_geneview_data_window_filters_by_bounds(client):
    full = client.get("/genes/ENSG00000000001/geneview-data").json()
    assert len(full["pas"]) == 2
    narrow = client.get(
        "/genes/ENSG00000000001/geneview-data", params={"start": 999, "end": 1000}
    ).json()
    assert len(narrow["pas"]) == 1
    assert narrow["pas"][0]["end"] == 1000


def test_geneview_data_isoforms_and_cluster_tracks(client):
    resp = client.get("/genes/ENSG00000000001/geneview-data")
    assert resp.status_code == 200
    body = resp.json()

    assert body["gene_name"] == "TESTA1"

    isoforms = body["isoforms"]
    assert len(isoforms) == 2
    for isoform in isoforms:
        assert isoform["transcript_id"].startswith("ENST")
        assert len(isoform["exons"]) > 0

    tracks = body["cluster_tracks"]
    assert len(tracks) == 2
    assert [t["cluster"] for t in tracks] == ["cl_A", "cl_B"]
    for track in tracks:
        assert track["n_cells"] > 0
        assert len(track["values"]) == len(body["pas"]) == 2

    # At least one cluster had reads for this gene; its PAS proportions
    # should sum to ~1.0 (mirrors the matplotlib reference's
    # row-normalised proportions).
    summed = [
        sum(v["proportion"] for v in t["values"] if v["proportion"] is not None)
        for t in tracks
        if any(v["proportion"] is not None for v in t["values"])
    ]
    assert summed, "expected at least one cluster with non-null proportions"
    assert any(abs(s - 1.0) < 1e-6 for s in summed)


def test_geneview_data_no_gtf_match_degrades_gracefully(client):
    resp = client.get("/genes/ENSG_NOT_A_GENE/geneview-data")
    assert resp.status_code == 200
    body = resp.json()
    assert body["gene_name"] == ""
    assert body["isoforms"] == []


def test_gene_counts_heavy_path(client):
    resp = client.get("/genes/ENSG00000000001/counts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_cells"] == 6
    assert len(body["pas_uids"]) == 2
    assert len(body["cells"]) == 6


def test_gene_counts_unknown_gene_returns_empty(client):
    resp = client.get("/genes/ENSG_NOT_A_GENE/counts")
    assert resp.status_code == 200
    assert resp.json()["n_cells"] == 0


# NOTE (2026-08-14): the old geneview.svg/.png PLACEHOLDER-stub endpoints
# (fake SVG served back for both extensions, tested here as
# test_geneview_svg_placeholder/test_geneview_png_placeholder) are REMOVED --
# replaced by the real `ema switch geneview` output via the host-side
# geneview worker (see api/geneview.py, geneview/client.py,
# geneview-worker/geneview_worker.py). `.svg` was never a real output
# extension of that replacement (ema's real outputs are .html/.png/.svg but
# the hub only serves .html + .png -- see GeneviewRender), so it now 404s;
# `.png` calls the real worker and must degrade gracefully (not crash) when
# it's unreachable, which is what these two tests now assert instead.


def test_geneview_svg_no_longer_served(client):
    resp = client.get("/genes/ENSG00000000001/geneview.svg")
    assert resp.status_code == 404


def test_geneview_png_degrades_gracefully_when_worker_unreachable(client):
    # No geneview worker is running in the test environment (it's a separate
    # host-side process, not part of this app) -- the endpoint must return a
    # clean, structured error (503, from GeneviewWorkerError) rather than an
    # unhandled 500/crash.
    resp = client.get("/genes/ENSG00000000001/geneview.png")
    assert resp.status_code == 503
    assert "geneview worker unreachable" in resp.json()["detail"]


def test_pas_detail_and_provenance(client):
    # Content-addressed pas_uid = strand-aware 3'-summit position (E1,
    # ids.pas_summit_pos: end-1 on '+', start on '-') -- NOT the raw `end`
    # column. For chr1:999-1000:+ that's chr1:999:+.
    pas_uid = "chr1:999:+"
    resp = client.get(f"/pas/{pas_uid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["gene_id"] == "ENSG00000000001"
    assert body["dropped_at"] == ""

    prov = client.get(f"/pas/{pas_uid}/provenance")
    assert prov.status_code == 200
    trail = prov.json()["trail"]
    assert any("SURVIVED" in step for step in trail)


def test_pas_dropped_provenance_shows_drop_reason(client):
    dropped_uid = "chr3:9999:+"  # atlas_snap-dropped PAS in the fixture (chr3:9999-10000:+ -> summit chr3:9999:+)
    prov = client.get(f"/pas/{dropped_uid}/provenance")
    assert prov.status_code == 200
    trail = prov.json()["trail"]
    assert any("DROPPED at stage='atlas_snap'" in step for step in trail)


def test_pas_404(client):
    resp = client.get("/pas/chrZZZ:1:+")
    assert resp.status_code == 404


def test_cell_detail_and_provenance(client):
    cell_uid = "ds1:AAACCCAAGT"
    resp = client.get(f"/cells/{cell_uid}")
    assert resp.status_code == 200
    assert resp.json()["barcode"] == "AAACCCAAGT"

    prov = client.get(f"/cells/{cell_uid}/provenance")
    assert prov.status_code == 200
    assert any("SURVIVED" in step for step in prov.json()["trail"])


def test_cell_dropped_provenance(client):
    dropped_cell_uid = "ds1:AAACCCAAGA"
    prov = client.get(f"/cells/{dropped_cell_uid}/provenance")
    assert prov.status_code == 200
    trail = prov.json()["trail"]
    assert any("DROPPED at stage='cb_filter'" in step for step in trail)


def test_cell_404(client):
    resp = client.get("/cells/does-not-exist")
    assert resp.status_code == 404


def test_umap_leiden_always_works(client, fixture_run_id: str):
    resp = client.get(f"/datasets/{fixture_run_id}/umap", params={"color": "leiden"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_points"] == 6
    assert all(p["leiden"] is not None for p in body["points"])


def test_umap_celltype_gated_501(client, fixture_run_id: str):
    """Spec §7c: celltype/stage/sample recolor is gated on A1+A2/B2+B7 --
    the fixture's clusters.h5ad has no `celltype` obs column, so this must
    fail loud (501 + gate body), never silently return empty/null colors.
    """
    resp = client.get(f"/datasets/{fixture_run_id}/umap", params={"color": "celltype"})
    assert resp.status_code == 501
    body = resp.json()
    assert body["available"] is False
    assert "A1" in body["gate"]


def test_umap_unknown_run_404(client):
    resp = client.get("/datasets/does-not-exist/umap", params={"color": "leiden"})
    assert resp.status_code == 404


def test_search_finds_gene_pas_and_cell(client):
    resp = client.get("/search", params={"q": "ENSG00000000001"})
    assert resp.status_code == 200
    body = resp.json()
    assert any(g["gene_id"] == "ENSG00000000001" for g in body["genes"])

    resp2 = client.get("/search", params={"q": "chr1:999"})
    assert any(p["pas_uid"] == "chr1:999:+" for p in resp2.json()["pas"])

    resp3 = client.get("/search", params={"q": "AAACCCAAGT"})
    assert any(c["barcode"] == "AAACCCAAGT" for c in resp3.json()["cells"])


def test_concordance_and_benchmarks_are_honest_stubs(client, fixture_run_id: str):
    resp = client.get("/concordance", params={"run_id": fixture_run_id})
    assert resp.status_code == 200
    assert resp.json()["available"] is False

    resp2 = client.get("/benchmarks", params={"run_id": fixture_run_id})
    assert resp2.status_code == 200
    assert resp2.json()["available"] is False


# --------------------------------------------------------------------------
# browse: GET /genes, /pas, /cells (searchable, paginated lists)
# --------------------------------------------------------------------------


def test_genes_list_returns_every_gene_with_surviving_pas(client):
    resp = client.get("/genes")
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 2
    gene_ids = {g["gene_id"] for g in page["items"]}
    assert gene_ids == {"ENSG00000000001", "ENSG00000000002"}
    # aggregate fields, not a bare id list
    one = next(g for g in page["items"] if g["gene_id"] == "ENSG00000000001")
    assert one["n_pas"] == 2
    assert one["n_findings"] == 2
    assert one["chrom"] == "chr1"


def test_genes_list_search_by_substring(client):
    resp = client.get("/genes", params={"q": "0000002"})
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 1
    assert page["items"][0]["gene_id"] == "ENSG00000000002"


def test_genes_list_locus_overlap_search(client):
    """The TopBar's "jump to chr:coords" search resolves a raw genomic
    interval to the gene(s) whose span overlaps it -- not an exact match.
    """
    resp = client.get("/genes", params={"chrom": "chr1", "start": 1000, "end": 1100})
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 1
    assert page["items"][0]["gene_id"] == "ENSG00000000001"

    # A window with no gene under it finds nothing (not a fail-open match).
    resp2 = client.get("/genes", params={"chrom": "chr1", "start": 900_000, "end": 900_100})
    assert resp2.json()["total"] == 0


def test_genes_list_pagination(client):
    resp = client.get("/genes", params={"limit": 1})
    page = resp.json()
    assert page["total"] == 2
    assert len(page["items"]) == 1
    assert page["next_cursor"] is not None

    resp2 = client.get("/genes", params={"limit": 1, "cursor": page["next_cursor"]})
    page2 = resp2.json()
    assert len(page2["items"]) == 1
    assert page2["next_cursor"] is None
    assert page["items"][0]["gene_id"] != page2["items"][0]["gene_id"]


def test_pas_list_includes_dropped_rows(client):
    """Unlike the geneview-data feed, the PAS browser is a provenance
    browser -- dropped PAS stay visible with their drop reason.
    """
    resp = client.get("/pas")
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 6  # matches qc funnel's n_pas_total
    dropped = [p for p in page["items"] if p["dropped_at"]]
    assert len(dropped) >= 1
    assert any(p["drop_reason"] for p in dropped)


def test_pas_list_search_by_gene_id(client):
    resp = client.get("/pas", params={"q": "ENSG00000000002"})
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 2
    assert all(p["gene_id"] == "ENSG00000000002" for p in page["items"])


def test_cells_list_includes_dropped_rows(client):
    resp = client.get("/cells")
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 7  # matches qc funnel's n_cells_total
    dropped = [c for c in page["items"] if c["dropped_at"]]
    assert len(dropped) >= 1


def test_cells_list_search_by_barcode(client):
    resp = client.get("/cells", params={"q": "AAACCCAAGT"})
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 1
    assert page["items"][0]["barcode"] == "AAACCCAAGT"


def test_pas_and_cells_list_accept_explicit_run_id(client, fixture_run_id: str):
    """Same `?run_id=` override every other endpoint in this module accepts."""
    resp = client.get("/pas", params={"run_id": fixture_run_id, "limit": 1})
    assert resp.status_code == 200
    resp2 = client.get("/cells", params={"run_id": fixture_run_id, "limit": 1})
    assert resp2.status_code == 200

    resp3 = client.get("/pas", params={"run_id": "does-not-exist"})
    assert resp3.status_code == 200
    assert resp3.json()["total"] == 0
