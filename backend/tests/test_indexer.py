from __future__ import annotations

import json
import shutil
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
