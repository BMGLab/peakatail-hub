"""Tests for the multi-directory SOURCES manager (dashboard "collect runs
from everywhere" feature): GET/POST/DELETE /sources, rescan, rescan-all.

Uses the `client` fixture from conftest.py, which pre-indexes
`packages/contract/fixtures` (run_id `fixture-run-0001`) with `source_id`
NULL (as if indexed by the bare `hub index` CLI, before any source was ever
registered) -- exactly the "already indexed elsewhere" case the sources
router has to re-attribute correctly rather than silently ignore.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from tests.conftest import CONTRACT_FIXTURES_DIR


def _copy_run_with_new_id(run_copy: Path, new_run_id: str) -> None:
    """Copy of test_indexer.py's manifest-mutation pattern: give a fixture
    copy a distinct run_id so it's genuinely new to the store rather than
    colliding (byte-identical, same checksum+fingerprint) with whatever
    run_id the base fixture already carries -- the `client` fixture in
    conftest.py pre-indexes CONTRACT_FIXTURES_DIR itself (run_id
    `fixture-run-0001`), so an un-mutated copy would always be a no-op skip.
    """
    manifest_path = run_copy / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["run_id"] = new_run_id
    manifest_path.write_text(json.dumps(manifest))


def test_list_sources_empty_initially(client):
    resp = client.get("/sources")
    assert resp.status_code == 200
    assert resp.json() == []


def test_add_source_indexes_a_fresh_run(client, tmp_path: Path):
    """Adding a source over a directory containing a run NOT yet in the
    store indexes it fresh and tags it with the new source_id/source_path.
    """
    root = tmp_path / "root_a"
    run_copy = root / "some_run_dir"
    shutil.copytree(CONTRACT_FIXTURES_DIR, run_copy)
    _copy_run_with_new_id(run_copy, "fresh-run-a")

    resp = client.post("/sources", json={"path": str(root), "label": "Root A"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["scan"]["indexed"] == ["fresh-run-a"]
    assert body["scan"]["failed"] == {}
    assert body["source"]["path"] == str(root.resolve())
    assert body["source"]["label"] == "Root A"
    assert body["source"]["run_count"] == 1
    assert body["source"]["last_scan_status"] == "ok"
    source_id = body["source"]["source_id"]

    runs = client.get("/runs").json()
    run = next(r for r in runs if r["run_id"] == "fresh-run-a")
    assert run["source_id"] == source_id
    assert run["source_path"] == str(root.resolve())
    assert run["source_label"] == "Root A"


def test_add_source_reattributes_an_already_indexed_run(client, fixture_run_id: str):
    """The `client` fixture pre-indexes CONTRACT_FIXTURES_DIR with source_id
    NULL. Registering CONTRACT_FIXTURES_DIR's parent as a source must NOT
    re-run the heavy indexer (manifest+artifacts unchanged -> skipped), but
    MUST still re-point that run's source_id/source_path at the new source
    -- this is the `index_source`/`touch_run_source` path, and the exact
    scenario the dashboard's "add the fixtures path, rescan, confirm the run
    appears (attributed)" verification exercises.
    """
    runs_before = client.get("/runs").json()
    run_before = next(r for r in runs_before if r["run_id"] == fixture_run_id)
    assert run_before["source_id"] is None

    resp = client.post("/sources", json={"path": str(CONTRACT_FIXTURES_DIR.parent)})
    assert resp.status_code == 201
    body = resp.json()
    assert body["scan"]["indexed"] == []
    assert body["scan"]["skipped_unchanged"] == [fixture_run_id]
    source_id = body["source"]["source_id"]
    assert body["source"]["run_count"] == 1

    runs_after = client.get("/runs").json()
    run_after = next(r for r in runs_after if r["run_id"] == fixture_run_id)
    assert run_after["source_id"] == source_id
    assert run_after["source_path"] == str(CONTRACT_FIXTURES_DIR.parent.resolve())


def test_add_source_bad_path_returns_400(client, tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    resp = client.post("/sources", json={"path": str(missing)})
    assert resp.status_code == 400
    assert client.get("/sources").json() == []


def test_add_source_path_is_a_file_returns_400(client, tmp_path: Path):
    a_file = tmp_path / "not_a_dir.txt"
    a_file.write_text("hello")
    resp = client.post("/sources", json={"path": str(a_file)})
    assert resp.status_code == 400


def test_add_source_empty_directory_reports_empty(client, tmp_path: Path):
    empty_root = tmp_path / "empty_root"
    empty_root.mkdir()
    resp = client.post("/sources", json={"path": str(empty_root)})
    assert resp.status_code == 201
    body = resp.json()
    assert body["scan"]["indexed"] == []
    assert body["scan"]["skipped_unchanged"] == []
    assert body["scan"]["failed"] == {}
    assert body["source"]["last_scan_status"] == "empty"
    assert body["source"]["run_count"] == 0


def test_add_source_same_path_twice_is_idempotent(client, tmp_path: Path):
    root = tmp_path / "root_b"
    root.mkdir()
    resp1 = client.post("/sources", json={"path": str(root)})
    resp2 = client.post("/sources", json={"path": str(root)})
    assert resp1.json()["source"]["source_id"] == resp2.json()["source"]["source_id"]
    assert len(client.get("/sources").json()) == 1


def test_rescan_source(client, tmp_path: Path):
    root = tmp_path / "root_c"
    run_copy = root / "run_dir"
    shutil.copytree(CONTRACT_FIXTURES_DIR, run_copy)
    _copy_run_with_new_id(run_copy, "fresh-run-c")

    add_resp = client.post("/sources", json={"path": str(root)})
    source_id = add_resp.json()["source"]["source_id"]
    assert add_resp.json()["scan"]["indexed"] == ["fresh-run-c"]

    # Nothing changed on disk between add and rescan -> unchanged, not
    # re-indexed, but still a healthy "ok" scan (not an error).
    rescan_resp = client.post(f"/sources/{source_id}/rescan")
    assert rescan_resp.status_code == 200
    body = rescan_resp.json()
    assert body["scan"]["indexed"] == []
    assert body["scan"]["skipped_unchanged"] == ["fresh-run-c"]
    assert body["source"]["last_scan_status"] == "ok"


def test_rescan_unknown_source_404(client):
    resp = client.post("/sources/src_doesnotexist/rescan")
    assert resp.status_code == 404


def test_rescan_all(client, tmp_path: Path, fixture_run_id: str):
    root1 = tmp_path / "root1"
    root2 = tmp_path / "root2"
    shutil.copytree(CONTRACT_FIXTURES_DIR, root1 / "run_dir")
    root2.mkdir()

    client.post("/sources", json={"path": str(root1)})
    client.post("/sources", json={"path": str(root2)})

    resp = client.post("/sources/rescan-all")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["sources"]) == 2
    statuses = {s["source"]["path"]: s["source"]["last_scan_status"] for s in body["sources"]}
    assert statuses[str(root1.resolve())] == "ok"
    assert statuses[str(root2.resolve())] == "empty"


def test_delete_source_cascades_its_runs(client, tmp_path: Path, fixture_run_id: str):
    root = tmp_path / "root_d"
    shutil.copytree(CONTRACT_FIXTURES_DIR, root / "run_dir")
    add_resp = client.post("/sources", json={"path": str(root)})
    source_id = add_resp.json()["source"]["source_id"]
    assert any(r["run_id"] == fixture_run_id for r in client.get("/runs").json())

    del_resp = client.delete(f"/sources/{source_id}")
    assert del_resp.status_code == 204
    assert client.get("/sources").json() == []
    # The run this source owned is gone too -- no orphaned run pointing at a
    # deleted source (see queries.delete_source_cascade docstring).
    assert client.get("/runs").json() == []


def test_delete_unknown_source_404(client):
    resp = client.delete("/sources/src_doesnotexist")
    assert resp.status_code == 404
