"""On-demand render cache.

Task brief invariant (stated twice, for the DuckDB file and for this cache):
writes go to `~/.peakatail-hub/cache` (or `HUB_CACHE_DIR`), **never** into
any run directory -- the hub is read-only with respect to run data; the only
thing it ever produces is its own cache. `tests/test_render_cache.py` proves
this by pointing at a fake run dir and asserting no new files appear there.

v1 is a thin stub (task brief: "full rendering logic is a later wave"): the
real geneview SVG/PNG renderer (the `CoordinateScale`/`Ruler`/`GeneModelLayer`
/... layer stack from spec §1) lives in the frontend; the backend's job for
now is to prove the cache *contract* (location + simple size-capped
eviction), returning a placeholder image so `/genes/{id}/geneview.svg|.png`
have something real to serve rather than a bare 501.
"""

from __future__ import annotations

import os
from pathlib import Path

from peakatail_hub import config

_PLACEHOLDER_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="640" height="120" viewBox="0 0 640 120">
  <rect width="640" height="120" fill="#f4f4f5"/>
  <text x="20" y="60" font-family="monospace" font-size="16" fill="#52525b">
    geneview placeholder for {gene_id} -- renderer not wired yet (v1 stub)
  </text>
</svg>
"""


def _cache_file(gene_id: str, ext: str, cache_dir: Path | None = None) -> Path:
    directory = cache_dir if cache_dir is not None else config.cache_dir()
    directory.mkdir(parents=True, exist_ok=True)
    safe_gene_id = "".join(c if c.isalnum() or c in "-_." else "_" for c in gene_id)
    return directory / f"geneview_{safe_gene_id}.{ext}"


def render_geneview_placeholder(gene_id: str, cache_dir: Path | None = None) -> Path:
    """Return a cached placeholder SVG path for `gene_id`, writing it (and
    touching its mtime on a cache hit) under the hub's own cache directory
    only. Enforces the size cap after writing.
    """
    path = _cache_file(gene_id, "svg", cache_dir)
    if path.exists():
        path.touch()  # LRU: mark as recently used
    else:
        path.write_text(_PLACEHOLDER_SVG.format(gene_id=gene_id))
        _enforce_cache_cap(cache_dir if cache_dir is not None else config.cache_dir())
    return path


def _enforce_cache_cap(cache_dir: Path, max_bytes: int | None = None) -> None:
    """Simple size-capped LRU (task brief: "a simple size-capped directory is
    fine for v1") -- evict oldest-by-mtime files first until under the cap.
    """
    cap = max_bytes if max_bytes is not None else config.cache_max_bytes()
    if not cache_dir.exists():
        return
    files = sorted(
        (p for p in cache_dir.iterdir() if p.is_file()),
        key=lambda p: p.stat().st_mtime,
    )
    total = sum(p.stat().st_size for p in files)
    i = 0
    while total > cap and i < len(files):
        size = files[i].stat().st_size
        os.remove(files[i])
        total -= size
        i += 1
