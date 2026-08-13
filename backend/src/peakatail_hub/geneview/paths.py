"""Reconciles a run's HOST filesystem path (what `runs.root` in the DuckDB
store holds -- straight from the run's own `run_manifest.json`, see
`index/indexer.py`) with THIS container's own read-only `/runs` mount, so
files the host-side geneview worker writes (directly onto the host
filesystem, see `geneview-worker/geneview_worker.py`) can be read back
through the container's mount without the container needing host filesystem
access of its own.
"""

from __future__ import annotations

from pathlib import Path

from peakatail_hub import config

#: Where docker-compose.yml always mounts the configured runs-root, whatever
#: `${PEAKATAIL_RUNS}` on the host resolves to (see that file + `HUB_RUNS_ROOT_HOST`).
CONTAINER_RUNS_ROOT = Path("/runs")


def container_run_dir(run_root_host: str) -> Path:
    """Map a run's HOST root path (`runs.root`) to its path as seen through
    THIS container's `/runs` mount.

    Correct path: `HUB_RUNS_ROOT_HOST` is set to the exact host directory
    `/runs` is mounted from (i.e. the same value as `${PEAKATAIL_RUNS}` in
    docker-compose.yml) -- `run_root_host` is then just re-based from that
    prefix onto `/runs`.

    Best-effort fallback (no `HUB_RUNS_ROOT_HOST` configured): assumes
    `/runs` is mounted from `run_root_host`'s immediate parent directory
    (true for the common "one runs-root directory, PEAKATAIL_RUNS points
    straight at it" deployment shape) and re-bases on just the run
    directory's own basename. This degrades silently to a WRONG path if the
    real mount root sits higher up (e.g. mounting a grandparent directory
    that also holds `grid/`/`reannotate/` subdirectories) -- set the env var
    explicitly in any deployment with nested run directories.
    """
    host_prefix = config.runs_root_host()
    run_root = Path(run_root_host)
    if host_prefix:
        try:
            rel = run_root.resolve().relative_to(Path(host_prefix).resolve())
            return CONTAINER_RUNS_ROOT / rel
        except ValueError:
            pass  # run_root_host isn't under the configured prefix -- fall through
    return CONTAINER_RUNS_ROOT / run_root.name
