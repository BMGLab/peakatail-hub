from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import duckdb
import pandas as pd

from peakatail_hub.index import find_run_dirs, index_run, index_runs_root
from peakatail_hub.store.db import connect
from tests.conftest import CONTRACT_FIXTURES_DIR


def _row_counts(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    tables = ["runs", "pas_ledger", "cell_ledger", "findings_long", "length_long", "umap_points"]
    return {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}  # noqa: S608


def test_find_run_dirs_discovers_fixture_run():
    dirs = find_run_dirs(CONTRACT_FIXTURES_DIR.parent)
    assert CONTRACT_FIXTURES_DIR in dirs


def test_index_run_populates_all_tables(db_path: Path):
    con = connect(db_path, read_only=False)
    run_id = index_run(con, CONTRACT_FIXTURES_DIR)
    counts = _row_counts(con)
    con.close()

    assert run_id == "fixture-run-0001"
    assert counts["runs"] == 1
    assert counts["pas_ledger"] == 6  # 6 rows in pas_ledger.tsv (4 surviving + 2 dropped)
    assert counts["cell_ledger"] == 7  # 7 rows in cell_ledger.tsv (6 surviving + 1 dropped)
    assert counts["findings_long"] == 4
    assert counts["length_long"] == 30
    assert counts["umap_points"] == 6  # matches n_obs of clusters.h5ad


def test_idempotent_reindex_is_noop(db_path: Path):
    """The task brief's core idempotency requirement: re-running `hub index`
    on an unchanged run must be a fast no-op -- row counts unchanged, and
    (via the manifest_checksum short-circuit) no deletes/inserts happen at
    all on the second pass.
    """
    con = connect(db_path, read_only=False)
    try:
        run_id_1 = index_run(con, CONTRACT_FIXTURES_DIR)
        counts_after_first = _row_counts(con)
        indexed_at_1 = con.execute("SELECT indexed_at FROM runs WHERE run_id = ?", [run_id_1]).fetchone()[0]

        # Second pass over the SAME unchanged manifest must be a no-op: the
        # checksum matches, so index_run raises _UnchangedRun before touching
        # any table (see indexer.py). Route through index_runs_root (the
        # real CLI path) so the report/skip bookkeeping is exercised too.
        report = index_runs_root(con, CONTRACT_FIXTURES_DIR.parent)
        counts_after_second = _row_counts(con)
        indexed_at_2 = con.execute("SELECT indexed_at FROM runs WHERE run_id = ?", [run_id_1]).fetchone()[0]

        assert report.indexed == []
        assert report.skipped_unchanged == [run_id_1]
        assert report.failed == {}
        assert counts_after_first == counts_after_second
        assert indexed_at_1 == indexed_at_2  # `runs` row was never rewritten
    finally:
        con.close()


def test_reindex_when_artifact_changes_but_manifest_bytes_dont(db_path: Path, tmp_path: Path):
    """Regression test for a real bug (2026-07-14): a run whose manifest
    bytes are unchanged but whose ledger/parquet/h5ad content changed (e.g.
    a fixture regenerated in place after a formula fix) was silently
    skipped by the old checksum-only idempotency check, leaving the DuckDB
    store stale with no error. `artifacts_fingerprint` (size+mtime of every
    manifest-registered artifact) must catch this even when
    `manifest_checksum` alone would not.
    """
    run_copy = tmp_path / "run_copy"
    shutil.copytree(CONTRACT_FIXTURES_DIR, run_copy)
    manifest_path = run_copy / "run_manifest.json"
    manifest_bytes_before = manifest_path.read_bytes()

    con = connect(db_path, read_only=False)
    try:
        run_id = index_run(con, run_copy)
        pas_count_before = con.execute(
            "SELECT count(*) FROM pas_ledger WHERE run_id = ?", [run_id]
        ).fetchone()[0]
        drop_reason_before = con.execute(
            "SELECT drop_reason FROM pas_ledger WHERE run_id = ? AND orig_pas_key = 'ds1:+:5'", [run_id]
        ).fetchone()[0]

        # Mutate a referenced ARTIFACT (pas_ledger.tsv) without touching
        # run_manifest.json's bytes at all -- lengthen one row's
        # drop_reason, which changes the file's size deterministically
        # (robust regardless of filesystem mtime granularity), and bump the
        # mtime explicitly too for good measure.
        ledger_path = run_copy / "pas_ledger.tsv"
        lines = ledger_path.read_text().splitlines(keepends=True)
        mutated = [
            line.replace(
                "no atlas hit within atlas_distance=100",
                "no atlas hit within atlas_distance=100 -- REGRESSION TEST MUTATION",
            )
            for line in lines
        ]
        assert mutated != lines, "fixture pas_ledger.tsv no longer contains the expected row to mutate"
        ledger_path.write_text("".join(mutated))
        future = time.time() + 120
        os.utime(ledger_path, (future, future))

        assert manifest_path.read_bytes() == manifest_bytes_before, "test setup bug: manifest bytes must NOT change"

        # This is the crux of the regression: before the fix, this would
        # raise _UnchangedRun (caught by index_runs_root as
        # skipped_unchanged) purely because manifest_checksum still
        # matched -- the artifact change was invisible to the old check.
        report = index_runs_root(con, run_copy.parent)
        assert run_id in report.indexed
        assert report.skipped_unchanged == []
        assert report.failed == {}

        pas_count_after = con.execute(
            "SELECT count(*) FROM pas_ledger WHERE run_id = ?", [run_id]
        ).fetchone()[0]
        drop_reason_after = con.execute(
            "SELECT drop_reason FROM pas_ledger WHERE run_id = ? AND orig_pas_key = 'ds1:+:5'", [run_id]
        ).fetchone()[0]

        assert pas_count_after == pas_count_before  # same row count, different content
        assert drop_reason_before != drop_reason_after
        assert drop_reason_after == "no atlas hit within atlas_distance=100 -- REGRESSION TEST MUTATION"

        # A genuinely-unchanged third pass (no further mutation) IS still a
        # no-op -- proves the fingerprint updated correctly rather than
        # forcing every future pass to re-index forever.
        report_third = index_runs_root(con, run_copy.parent)
        assert report_third.indexed == []
        assert report_third.skipped_unchanged == [run_id]
    finally:
        con.close()


def test_reindex_after_manifest_change_replaces_rows(db_path: Path, tmp_path: Path):
    """A changed manifest (different checksum) IS fully re-processed -- this
    is the complementary case to the no-op test above, proving the gate is
    checksum-based (content), not "run_id already seen at all".
    """
    # Copy the fixture run dir so we can mutate its manifest without
    # touching the real packages/contract fixtures.
    run_copy = tmp_path / "run_copy"
    shutil.copytree(CONTRACT_FIXTURES_DIR, run_copy)

    con = connect(db_path, read_only=False)
    try:
        index_run(con, run_copy)
        counts_before = _row_counts(con)

        manifest_path = run_copy / "run_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["entity_counts"]["n_pas"] = 999  # innocuous content change -> different checksum
        manifest_path.write_text(json.dumps(manifest))

        run_id = index_run(con, run_copy)
        counts_after = _row_counts(con)

        assert run_id == "fixture-run-0001"
        # Row counts for the actual data tables are unchanged (same
        # underlying ledgers/findings), but this proves the re-index path
        # (delete+reinsert) ran rather than being skipped.
        assert counts_before == counts_after
        stored_config = con.execute(
            "SELECT n_pas FROM runs WHERE run_id = ?", [run_id]
        ).fetchone()[0]
        assert stored_config == 999
    finally:
        con.close()


def test_invalid_run_is_skipped_not_fatal(db_path: Path, tmp_path: Path):
    """A run that fails contract validation must be logged and skipped, not
    crash the whole `hub index` pass (task brief: "skip/report ... any run
    that fails validation, logging why").
    """
    runs_root = tmp_path / "runs_root"
    runs_root.mkdir()
    good_run = runs_root / "good_run"
    bad_run = runs_root / "bad_run"
    shutil.copytree(CONTRACT_FIXTURES_DIR, good_run)
    shutil.copytree(CONTRACT_FIXTURES_DIR, bad_run)

    # Break referential integrity: findings_long referencing a pas_uid that
    # is not in pas_ledger.tsv triggers ContractValidationError.
    manifest_path = bad_run / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["run_id"] = "bad-run-0001"
    manifest_path.write_text(json.dumps(manifest))

    findings_path = bad_run / "findings_long.parquet"
    df = pd.read_parquet(findings_path)
    df.loc[0, "pas_uid"] = "chrZZZ:1:+"  # not in pas_ledger
    df.to_parquet(findings_path, index=False)

    con = connect(db_path, read_only=False)
    try:
        report = index_runs_root(con, runs_root)
        assert "fixture-run-0001" in report.indexed
        assert any("bad_run" in path for path in report.failed)
        assert "chrZZZ:1:+" in next(iter(report.failed.values()))
        # The good run's rows must exist despite the bad run failing.
        n_good = con.execute(
            "SELECT count(*) FROM findings_long WHERE run_id = 'fixture-run-0001'"
        ).fetchone()[0]
        assert n_good == 4
        # The bad run must not have partially written any rows.
        n_bad = con.execute(
            "SELECT count(*) FROM findings_long WHERE run_id = 'bad-run-0001'"
        ).fetchone()[0]
        assert n_bad == 0
    finally:
        con.close()
