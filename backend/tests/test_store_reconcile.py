"""Spec §5 / task brief invariant: "range/tile assert full counts reconcile
(nothing trimmed)" -- windowed/paginated reads must never silently drop
rows, and facet counts must reflect the true total, not the current page.
"""

from __future__ import annotations

import duckdb

from peakatail_hub.store import queries


def test_paginated_findings_union_reconciles_with_unfiltered_count(indexed_con: duckdb.DuckDBPyConnection):
    flt = queries.FindingsFilter()  # no filters at all
    total = queries.count_findings(indexed_con, flt)
    assert total == 4  # matches make_fixtures.py's 4 finding rows

    seen_uids: set[str] = set()
    offset = 0
    page_size = 1  # deliberately smaller than total to force multiple pages
    pages_fetched = 0
    while True:
        page = queries.query_findings(indexed_con, flt, offset, page_size)
        if not page:
            break
        for row in page:
            assert row["finding_uid"] not in seen_uids, "page union must not double-count a row"
            seen_uids.add(row["finding_uid"])
        offset += len(page)
        pages_fetched += 1
        assert pages_fetched <= total + 1, "pagination should terminate"

    assert len(seen_uids) == total, "union of all pages must reconcile with the unfiltered total"


def test_facet_counts_reconcile_with_full_table_not_current_page(indexed_con: duckdb.DuckDBPyConnection):
    flt = queries.FindingsFilter()
    total = queries.count_findings(indexed_con, flt)

    # Fetch a single-row "page" (i.e. simulate a client that only asked for
    # the first row) and confirm the facets endpoint's counts do NOT match
    # page-of-1 counts -- they must reconcile with the true unfiltered total.
    page = queries.query_findings(indexed_con, flt, offset=0, limit=1)
    assert len(page) == 1

    facets = queries.findings_facets(indexed_con, flt)
    for dim, values in facets.items():
        dim_total = sum(v["count"] for v in values)
        assert dim_total == total, f"facet dimension {dim!r} total ({dim_total}) must reconcile with full count ({total}), not the 1-row page"


def test_facet_counts_reconcile_under_an_active_filter(indexed_con: duckdb.DuckDBPyConnection):
    """Same invariant, but with a filter applied -- facets must reconcile
    with the FILTERED total (all rows matching that filter), not any page
    of it.
    """
    flt = queries.FindingsFilter(strategy="fisher")
    total = queries.count_findings(indexed_con, flt)
    assert total == 2  # fixture has 2 fisher rows (shorten + lengthen)

    facets = queries.findings_facets(indexed_con, flt)
    strategy_total = sum(v["count"] for v in facets["strategy"])
    assert strategy_total == total
    # every value bucketed under the "strategy" facet must itself be "fisher"
    # since the filter is already applied before grouping.
    assert all(v["value"] == "fisher" for v in facets["strategy"])


def test_geneview_window_never_trims_pas_within_bounds(indexed_con: duckdb.DuckDBPyConnection, fixture_run_id: str):
    """A geneview window covering the gene's full span must return every
    surviving PAS for that gene -- confirming the windowed range query
    doesn't silently downsample (spec: "Never trim/downsample.").
    """
    gene_id = "ENSG00000000001"
    span = queries.gene_pas_span(indexed_con, fixture_run_id, gene_id)
    assert span is not None
    full_window = queries.geneview_pas_in_window(indexed_con, fixture_run_id, gene_id, span["start"], span["end"])
    unbounded = queries.geneview_pas_in_window(indexed_con, fixture_run_id, gene_id, None, None)
    assert len(full_window) == len(unbounded) == span["n_pas"] == 2  # gene 1 has 2 surviving PAS in the fixture
