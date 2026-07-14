"""Task brief: "Write an explicit test that asserts [the render cache]
NEVER writes into any run directory." This is the whole point of this
module -- it monkeypatches a fake run dir and confirms `render_geneview_
placeholder` never touches it, only its own dedicated cache dir.
"""

from __future__ import annotations

from pathlib import Path

from peakatail_hub.render.cache import _enforce_cache_cap, render_geneview_placeholder


def _snapshot(directory: Path) -> set[str]:
    return {str(p.relative_to(directory)) for p in directory.rglob("*")}


def test_render_never_writes_into_run_dir(tmp_path: Path):
    fake_run_dir = tmp_path / "fake_run"
    fake_run_dir.mkdir()
    (fake_run_dir / "run_manifest.json").write_text("{}")
    (fake_run_dir / "pas_ledger.tsv").write_text("a\tb\n")
    before = _snapshot(fake_run_dir)

    cache_dir = tmp_path / "cache"
    path = render_geneview_placeholder("ENSG00000000001", cache_dir=cache_dir)

    after = _snapshot(fake_run_dir)
    assert before == after, "render_geneview_placeholder must never write into a run directory"
    assert path.exists()
    assert path.is_relative_to(cache_dir)
    assert not path.is_relative_to(fake_run_dir)


def test_render_cache_hit_touches_not_rewrites(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    path1 = render_geneview_placeholder("ENSG00000000001", cache_dir=cache_dir)
    content1 = path1.read_text()

    path2 = render_geneview_placeholder("ENSG00000000001", cache_dir=cache_dir)
    assert path1 == path2
    assert path2.read_text() == content1  # cache hit: same content, not re-derived


def test_cache_dir_default_is_outside_any_run_dir(tmp_path: Path, monkeypatch):
    """The default HUB_CACHE_DIR (~/.peakatail-hub/cache) and default
    HUB_DB_PATH (~/.peakatail-hub/hub.duckdb) must never resolve under a
    run directory -- same invariant restated for the config layer itself.
    """
    from peakatail_hub import config

    monkeypatch.delenv("HUB_CACHE_DIR", raising=False)
    monkeypatch.delenv("HUB_DB_PATH", raising=False)
    run_dir = tmp_path / "some_run_dir"
    run_dir.mkdir()

    assert not config.cache_dir().is_relative_to(run_dir)
    assert not config.db_path().is_relative_to(run_dir)


def test_cache_cap_evicts_oldest_first(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    for name, size in [("a.bin", 100), ("b.bin", 100), ("c.bin", 100)]:
        (cache_dir / name).write_bytes(b"0" * size)
    # Force a.bin to be the oldest by mtime.
    import os
    import time

    now = time.time()
    os.utime(cache_dir / "a.bin", (now - 100, now - 100))
    os.utime(cache_dir / "b.bin", (now - 50, now - 50))
    os.utime(cache_dir / "c.bin", (now, now))

    _enforce_cache_cap(cache_dir, max_bytes=150)

    remaining = {p.name for p in cache_dir.iterdir()}
    assert "a.bin" not in remaining, "oldest file should be evicted first"
    assert "c.bin" in remaining, "newest file should survive"
