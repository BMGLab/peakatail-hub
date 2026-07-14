"""`hub` CLI entry point.

    hub index <runs_root> [--db PATH]     # walk runs_root, (re)index into DuckDB
    hub serve [--host] [--port] [--db PATH]   # convenience wrapper around uvicorn

`hub index` is the CLI surface required by the task brief; `hub serve` is a
small convenience addition so the whole backend is runnable via one console
script during development (equivalent to
`uvicorn peakatail_hub.app:app --host ... --port ...` with HUB_DB_PATH set).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from peakatail_hub import config
from peakatail_hub.index import index_runs_root
from peakatail_hub.store.db import connect


def _cmd_index(args: argparse.Namespace) -> int:
    db = Path(args.db) if args.db else config.db_path()
    con = connect(db, read_only=False)
    try:
        report = index_runs_root(con, Path(args.runs_root))
    finally:
        con.close()

    print(f"indexed:           {len(report.indexed)} {report.indexed}")
    print(f"skipped (unchanged): {len(report.skipped_unchanged)} {report.skipped_unchanged}")
    print(f"failed:            {len(report.failed)}")
    for run_dir, error in report.failed.items():
        print(f"  - {run_dir}: {error.splitlines()[0] if error else error}")
    return 1 if report.failed else 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    if args.db:
        os.environ["HUB_DB_PATH"] = str(args.db)
    uvicorn.run("peakatail_hub.app:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hub")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Walk a runs-root directory and (re)index every run into DuckDB.")
    p_index.add_argument("runs_root", help="Directory to walk for run_manifest.json files.")
    p_index.add_argument("--db", default=None, help=f"DuckDB file path (default: {config.db_path()}).")
    p_index.set_defaults(func=_cmd_index)

    p_serve = sub.add_parser("serve", help="Run the FastAPI app with uvicorn.")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--db", default=None, help=f"DuckDB file path (default: {config.db_path()}).")
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=_cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
