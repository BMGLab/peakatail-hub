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
