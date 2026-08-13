"""Runtime configuration.

Deliberately NOT pydantic-settings (avoids an extra dependency for three
env-overridable paths); plain env-var-with-default lookups are enough here.

Both `HUB_DB_PATH` and `HUB_CACHE_DIR` default to locations OUTSIDE any run
directory -- this is the same rule stated twice in the task brief (the
DuckDB file "NEVER inside the run dir" and the render cache "NEVER into any
run directory"): the hub must never write into data it only reads.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HUB_HOME = Path.home() / ".peakatail-hub"


def db_path() -> Path:
    override = os.environ.get("HUB_DB_PATH")
    if override:
        return Path(override)
    return DEFAULT_HUB_HOME / "hub.duckdb"


def cache_dir() -> Path:
    override = os.environ.get("HUB_CACHE_DIR")
    if override:
        return Path(override)
    return DEFAULT_HUB_HOME / "cache"


def cache_max_bytes() -> int:
    return int(os.environ.get("HUB_CACHE_MAX_BYTES", str(512 * 1024 * 1024)))  # 512 MiB default


# --------------------------------------------------------------------------
# Geneview worker (2026-08-14) -- `ema switch geneview` runs on the HOST (the
# analysis venv with `ema` installed), not in this container. See
# `geneview-worker/geneview_worker.py`'s module docstring for the full
# design; these two settings are the container-side half of that split.
# --------------------------------------------------------------------------


def geneview_worker_url() -> str:
    """Base URL of the host-side geneview worker. `host.docker.internal`
    requires the backend service to declare
    `extra_hosts: ["host.docker.internal:host-gateway"]` in compose (Linux
    Docker Engine 20.10+) -- see docker-compose.yml.
    """
    return os.environ.get("HUB_GENEVIEW_WORKER_URL", "http://host.docker.internal:8095")


def geneview_worker_timeout_sec() -> float:
    return float(os.environ.get("HUB_GENEVIEW_WORKER_TIMEOUT_SEC", "180"))


def runs_root_host() -> str | None:
    """The HOST filesystem path that this container's `/runs` mount points
    at -- i.e. exactly the `${PEAKATAIL_RUNS}` value docker-compose.yml
    mounts as `/runs:ro`. Needed because `runs.root` in the DuckDB store
    (from the run's own manifest) is always a HOST path, but generated
    geneview files must be read back through THIS container's own `/runs`
    mount, not the host path directly (the container can't see the host
    filesystem outside its mounts). `None` when unset -- callers fall back
    to a best-effort "assume /runs mounts the run's immediate parent
    directory" (see `geneview/paths.py::container_run_dir`), which is
    correct for the common single-runs-root deployment shape but should be
    set explicitly in production.
    """
    return os.environ.get("HUB_RUNS_ROOT_HOST") or None
