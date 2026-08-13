#!/usr/bin/env python3
"""geneview_worker — a tiny HTTP service that runs `ema switch geneview` on
demand, on the HOST, and hands the resulting figures back to the
peakatail-hub backend (which runs in a container with no `ema` installed).

WHY THIS EXISTS (2026-08-14): the hub's GeneView used to be a hand-rolled
IGV-style track re-implementation (custom canvas layers, a stubbed isoform
aggregation) that never matched what `ema switch geneview` actually produces
-- the real interactive plotly figure (all PAS + full cell metadata on
hover, a switchable per-cluster metric, a PAS-distance table overlay) and
the real static matplotlib figure the professor already reviews. The fix is
to stop reimplementing that view and just render ema's own output. But
`ema` (and its scientific-Python stack) lives only in the analysis venv on
the HOST (`/mnt/ssd2/Laugney_Aligned/.peakatail_env`), not in the hub
backend's Docker image -- so generation has to happen out-of-container.

DESIGN (deliberately the simplest thing that is still robust, per the task
brief -- documented here instead of just in a PR description):

* Stdlib only (`http.server`/`socketserver`), run with the ema venv's own
  interpreter. No FastAPI/uvicorn/flask -- none of those are installed in
  that venv and it is a shared, disk-constrained production environment
  ($HOME is 96% full) that this fix must not `pip install` into.
* One synchronous endpoint, `POST /geneview`: resolve inputs, run `ema
  switch geneview --plot-engine both --pas-distance-table`, move its output
  into a deterministic cache path, respond with what was written. The hub
  backend calls this over HTTP (see
  `backend/src/peakatail_hub/geneview/client.py`) and blocks the request
  until it's done -- "on-demand generation, ~10s first open, cached after"
  (task brief) reads naturally as a synchronous call; no queue/poll needed.
* `ema switch geneview -o <dir>` does NOT write into `<dir>` directly -- it
  suffixes a wall-clock timestamp (`<dir>_YYYY-MM-DD_HHMMSS/figures/...`),
  confirmed by manually invoking it against a real run
  (`B1_cohort_full/07_clustering/<ds>/clusters.h5ad`, gene ENSG00000254087:
  11.3s wall clock, output landed in
  `<given-dir>_2026-08-13_152852/figures/gene_ENSG00000254087.{html,png,svg,
  meta.json}` + `..._pas_distances.csv` one level up in the timestamped
  dir's `figures/`). This worker always renders into a throwaway per-request
  scratch dir, globs for the timestamp-suffixed result, and MOVES (not
  copies -- see `_move_into_cache`) the 5 files into the deterministic,
  gene_id/dataset_id-keyed cache path the hub backend expects, then removes
  the scratch dir. Callers never see ema's timestamp suffix.
* CELLTYPE x STAGE (2026-08-14): the primary render grain is now per
  (celltype, stage), not per-dataset leiden -- `_resolve_celltype_inputs`
  uses `<run_root>/B3_switch/combined/<celltype>.h5ad` (obs['stage'] carries
  the real disease-stage label) + the sibling `combined/pasbed.bed`, with
  `--cluster-key stage --subtitle <celltype>`. Falls through to the
  original per-dataset path (`_resolve_dataset_h5ad`, `--cluster-key
  leiden`) when no `celltype` was requested or this run has no
  `B3_switch/combined/` at all (grid/reannotate runs -- no switch analysis).
* Cache path: `<run_root>/B3_switch/geneview_cache/<gene_id>/<key>/`, `key`
  being whichever of celltype/dataset_id was actually used (see
  `_cache_dir`). `<run_root>` is writable on the HOST filesystem even though the hub
  backend's own Docker mount of the same directory is `:ro` -- the container
  only ever needs to READ these files back (see the client module), not
  write them, so the read-only mount is not a problem once this worker (on
  the host) has written them.
* Per-(run_root, gene_id, dataset_id) in-process lock: two near-simultaneous
  requests for the same gene (e.g. two browser tabs) must not race two `ema`
  subprocesses writing into the same cache directory -- the second request
  blocks until the first finishes, then hits the now-warm cache.
* `TMPDIR`/`XDG_CACHE_HOME`/`MPLCONFIGDIR` are set to subdirectories of a
  per-request scratch dir under `--scratch-root` (never $HOME -- home is 96%
  full on this host) -- isolates concurrent requests from each other and
  keeps matplotlib/plotly's own caches off a nearly-full disk.
* `TMPDIR` specifically is carved out of a SEPARATE, SHORT `--tmp-root`
  (e.g. `/mnt/ssd2/Laugney_Aligned/rt`), not a subdirectory of
  `--scratch-root`. `ema switch geneview` spins up a multiprocessing
  `SyncManager`, which binds an AF_UNIX socket under `$TMPDIR` -- Linux caps
  `sun_path` at ~108 bytes, and a `--scratch-root`-nested path like
  `.../geneview_worker_scratch/gv_ENSG00000254087_ab12cd34/tmp` blows that
  limit outright (`OSError: AF_UNIX path too long`, reproduced verbatim
  while building this worker). `tmp_root`'s own `tempfile.mkdtemp` request
  dirs are deliberately short, unprefixed random names (no gene_id in the
  path) to stay well under the limit regardless of gene_id length.
* `--allow-root-prefix` (repeatable) is a simple path-traversal guard: this
  worker executes an arbitrary local subprocess on whatever `run_root` a
  caller supplies, so it refuses to touch anything outside the configured
  prefix(es) rather than trusting the hub backend's request body blindly.

Run it (see geneview-worker/README.md for the systemd-unit version):

    TMPDIR=/mnt/ssd2/Laugney_Aligned/rt \\
    /mnt/ssd2/Laugney_Aligned/.peakatail_env/bin/python geneview_worker.py \\
        --port 8095 \\
        --ema-bin /mnt/ssd2/Laugney_Aligned/.peakatail_env/bin/ema \\
        --gtf /home/sharedFolder/humanSTARindex/Homo_sapiens.GRCh38.99.gtf \\
        --scratch-root /mnt/ssd2/Laugney_Aligned/rt/geneview_worker_scratch \\
        --tmp-root /mnt/ssd2/Laugney_Aligned/rt \\
        --allow-root-prefix /mnt/ssd2/Laugney_Aligned/peakatail_experiments
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

logger = logging.getLogger("geneview_worker")

#: Files ema writes per gene under `<out>_<timestamp>/figures/` -- the first
#: four always exist on a successful `--plot-engine both` render; the CSV
#: only exists when `--pas-distance-table` produced at least one PAS.
_EMA_OUTPUT_SUFFIXES = {
    "html": "{stem}.html",
    "png": "{stem}.png",
    "svg": "{stem}.svg",
    "meta_json": "{stem}.meta.json",
}
_EMA_DISTANCE_CSV = "{stem}_pas_distances.csv"


class GeneviewWorkerError(Exception):
    """Raised for any request-level failure (bad input, ema failure, missing
    output) -- caught once at the top of `do_POST` and turned into a
    structured JSON error response, never an unhandled 500 with a bare
    traceback leaking to the caller."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class Config:
    def __init__(self, args: argparse.Namespace):
        self.ema_bin = Path(args.ema_bin)
        self.default_gtf = Path(args.gtf) if args.gtf else None
        self.scratch_root = Path(args.scratch_root)
        # Deliberately separate from scratch_root -- see module docstring's
        # AF_UNIX note. Defaults to scratch_root's parent if not given, but
        # callers should pass a short path explicitly (e.g. the analysis
        # cohort's existing short-tmpdir convention).
        self.tmp_root = Path(args.tmp_root) if args.tmp_root else self.scratch_root
        self.allow_root_prefixes = [Path(p).resolve() for p in args.allow_root_prefix]
        self.timeout_sec = args.timeout_sec
        self.scratch_root.mkdir(parents=True, exist_ok=True)
        self.tmp_root.mkdir(parents=True, exist_ok=True)


# One lock per (run_root, gene_id, dataset_id) cache directory, created
# lazily -- see module docstring's "per-gene lock" note.
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


def _check_allowed_root(run_root: Path, cfg: Config) -> None:
    resolved = run_root.resolve()
    if not any(resolved == p or p in resolved.parents for p in cfg.allow_root_prefixes):
        raise GeneviewWorkerError(
            f"run_root {resolved} is not under any --allow-root-prefix "
            f"({[str(p) for p in cfg.allow_root_prefixes]}); refusing to run ema against it.",
            status=403,
        )
    if not resolved.is_dir():
        raise GeneviewWorkerError(f"run_root {resolved} does not exist or is not a directory", status=404)


def _resolve_dataset_h5ad(run_root: Path, dataset_id: str | None) -> tuple[str, Path]:
    """Pick the `clusters.h5ad` to render from. Explicit `dataset_id` wins;
    otherwise deterministically picks the alphabetically-first dataset under
    `07_clustering/` so repeat calls without a dataset_id always resolve to
    the same cache path. Falls back to a bare `<run_root>/clusters.h5ad`
    (single-h5ad run/fixture shape) if `07_clustering/` doesn't exist at all.
    """
    clustering_root = run_root / "07_clustering"
    if dataset_id is not None:
        h5ad = clustering_root / dataset_id / "clusters.h5ad"
        if not h5ad.exists():
            raise GeneviewWorkerError(f"no clusters.h5ad for dataset_id={dataset_id!r} at {h5ad}", status=404)
        return dataset_id, h5ad

    if clustering_root.is_dir():
        candidates = sorted(p for p in clustering_root.iterdir() if (p / "clusters.h5ad").exists())
        if candidates:
            chosen = candidates[0]
            return chosen.name, chosen / "clusters.h5ad"

    bare = run_root / "clusters.h5ad"
    if bare.exists():
        return "default", bare

    raise GeneviewWorkerError(
        f"no clusters.h5ad found under {clustering_root} or at {bare} -- cannot render a geneview for this run",
        status=404,
    )


def _resolve_pasbed(run_root: Path, pasbed: str | None) -> Path:
    path = run_root / (pasbed or "pasbed.bed")
    if not path.exists():
        raise GeneviewWorkerError(f"pasbed not found at {path}", status=404)
    return path


def _resolve_celltype_inputs(run_root: Path, celltype: str) -> tuple[Path, Path] | None:
    """CELLTYPE x STAGE geneview inputs (2026-08-14, per stabilized cohort
    layout): `<run_root>/B3_switch/combined/<celltype>.h5ad` -- a per-
    celltype h5ad combining all datasets, with `obs['stage']` carrying the
    real disease-stage label (verified on B1_cohort_full: 'Normal'/'Met'/
    'StageI'/'IVprimary') -- plus a sibling `combined/pasbed.bed` shared by
    every celltype in the run. This is the switch-context grain the
    professor's headline finding (3'UTR shortening/lengthening ACROSS
    STAGES, WITHIN a cell type) actually needs -- per-dataset leiden
    clusters (the fallback below) have no cross-dataset stage semantics at
    all.

    Returns `None` (never raises) when this run has no `B3_switch/combined/`
    at all (grid/reannotate runs -- no switch/celltype analysis) or no h5ad
    for this specific `celltype` -- callers fall back to
    `_resolve_dataset_h5ad` in that case, exactly as if celltype had never
    been requested.
    """
    h5ad = run_root / "B3_switch" / "combined" / f"{celltype}.h5ad"
    pasbed = run_root / "B3_switch" / "combined" / "pasbed.bed"
    if h5ad.exists() and pasbed.exists():
        return h5ad, pasbed
    return None


def _cache_dir(run_root: Path, gene_id: str, key: str) -> Path:
    """`key` is whichever identity this render was actually generated
    against -- a celltype (CELLTYPE x STAGE path) or a dataset_id (the
    per-dataset fallback path, see `_resolve_celltype_inputs`/
    `generate_geneview`). The two key-spaces don't collide in practice
    (celltype names are long free-text stratum labels, dataset_ids are
    GSM/sample ids) and are never mixed for the same gene_id within one run,
    so a single flat namespace under the gene is enough -- no separate
    `celltype/`/`dataset/` prefix needed.
    """
    return run_root / "B3_switch" / "geneview_cache" / gene_id / key


def _cache_hit_files(cache_dir: Path, gene_id: str) -> dict[str, Path] | None:
    stem = f"gene_{gene_id}"
    files = {kind: cache_dir / pattern.format(stem=stem) for kind, pattern in _EMA_OUTPUT_SUFFIXES.items()}
    if not all(p.exists() for p in files.values()):
        return None
    csv_path = cache_dir / _EMA_DISTANCE_CSV.format(stem=stem)
    files["pas_distances_csv"] = csv_path if csv_path.exists() else None
    return files


def _run_ema(
    cfg: Config, h5ad: Path, gene_id: str, pasbed: Path, gtf: Path | None, cluster_key: str, subtitle: str | None = None
) -> Path:
    """Invoke `ema switch geneview` into a fresh scratch dir; returns the
    (timestamp-suffixed) `figures/` directory ema actually wrote into."""
    request_scratch = Path(tempfile.mkdtemp(prefix=f"gv_{gene_id}_", dir=cfg.scratch_root))
    # Short, unprefixed dir straight under --tmp-root (NOT request_scratch --
    # see module docstring's AF_UNIX note; ema's SyncManager socket path
    # must stay short regardless of gene_id length).
    request_tmp = Path(tempfile.mkdtemp(dir=cfg.tmp_root))
    out_prefix = request_scratch / "out"
    env_dirs = {
        "TMPDIR": request_tmp,
        "XDG_CACHE_HOME": request_scratch / "xdg_cache",
        "MPLCONFIGDIR": request_scratch / "mplconfig",
    }
    for d in env_dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(cfg.ema_bin), "switch", "geneview",
        "-i", str(h5ad),
        "--gene-id", gene_id,
        "--pasbed", str(pasbed),
        "--cluster-key", cluster_key,
        "--plot-engine", "both",
        "--pas-distance-table",
        "--no-progress",
        "--no-log-file",
        "-o", str(out_prefix),
    ]
    if gtf is not None:
        cmd += ["--gtf", str(gtf)]
    if subtitle:
        # CELLTYPE x STAGE path: names the celltype in the figure header
        # rather than repeating it on every track label -- see
        # `_resolve_celltype_inputs`.
        cmd += ["--subtitle", subtitle]

    import os

    env = {**os.environ, **{k: str(v) for k, v in env_dirs.items()}}
    logger.info("running: %s", " ".join(cmd))
    t0 = time.monotonic()
    try:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=cfg.timeout_sec, env=env)
        except subprocess.TimeoutExpired as exc:
            raise GeneviewWorkerError(
                f"ema switch geneview timed out after {cfg.timeout_sec}s for gene_id={gene_id!r}", status=504
            ) from exc
        elapsed = time.monotonic() - t0

        if proc.returncode != 0:
            tail = "\n".join((proc.stderr or "").splitlines()[-30:])
            raise GeneviewWorkerError(
                f"ema switch geneview exited {proc.returncode} for gene_id={gene_id!r} (elapsed={elapsed:.1f}s):\n{tail}",
                status=500,
            )

        # ema appends a wall-clock timestamp to the `-o` prefix -- glob for it
        # rather than parse it out of stdout/logs (see module docstring).
        matches = sorted(request_scratch.glob("out_*/figures"))
        if not matches:
            raise GeneviewWorkerError(
                f"ema switch geneview reported success but no 'out_*/figures' dir was found under {request_scratch} "
                f"for gene_id={gene_id!r}",
                status=500,
            )
        logger.info("ema switch geneview for gene_id=%s done in %.1fs", gene_id, elapsed)
        return matches[-1]
    except Exception:
        # On ANY failure, request_scratch (the -o output tree) is dead weight
        # -- clean it up before re-raising. On SUCCESS it's cleaned by
        # `_move_into_cache` instead (once the wanted files are safely moved
        # out), not here.
        shutil.rmtree(request_scratch, ignore_errors=True)
        raise
    finally:
        # request_tmp (TMPDIR) is never needed past subprocess.run() returning
        # -- clean it up unconditionally, success or failure.
        shutil.rmtree(request_tmp, ignore_errors=True)


def _move_into_cache(figures_dir: Path, gene_id: str, key: str, source: str, cache_dir: Path) -> dict[str, Path]:
    """Move ema's per-gene output out of the (about-to-be-deleted) scratch
    `figures_dir` into the deterministic cache dir. Caller is responsible
    for cleaning up `figures_dir`'s scratch tree afterwards regardless of
    outcome (see `generate_geneview`) -- this function itself never deletes
    anything, so a raised error here always leaves the scratch output
    inspectable for debugging until the caller's `finally` runs.

    `key`/`source` are purely for the error message -- `source` is
    `"celltype"` or `"dataset"` (see `generate_geneview`), so the 404 below
    names the right axis a caller might retry on.
    """
    stem = f"gene_{gene_id}"
    html_src = figures_dir / _EMA_OUTPUT_SUFFIXES["html"].format(stem=stem)
    if not html_src.exists():
        # A real, observed ema behavior (not a bug in this worker): ema
        # exits 0 with "Gene <id> has no PAS in the AnnData or pasbed —
        # skipping" and writes nothing for that gene when it isn't present
        # in the chosen h5ad/pasbed's var_names -- distinct per-dataset (or
        # per-celltype-combined) PAS calling means a gene_id present in one
        # can genuinely be absent from another. Surfaced as a clear 404 (not
        # a generic 500 "file missing") so the hub backend/frontend can show
        # "no PAS for this gene here" rather than a scary unexplained error.
        raise GeneviewWorkerError(
            f"ema reported no renderable output for gene_id={gene_id!r} ({source}={key!r}) -- most likely this "
            f"gene has no PAS in that {source}'s h5ad/pasbed. Try a different {source}.",
            status=404,
        )

    cache_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}
    for kind, pattern in _EMA_OUTPUT_SUFFIXES.items():
        src = figures_dir / pattern.format(stem=stem)
        if not src.exists():
            raise GeneviewWorkerError(
                f"ema wrote {html_src.name} but not {src.name} for gene_id={gene_id!r} -- partial/unexpected "
                f"output in {figures_dir}",
                status=500,
            )
        dst = cache_dir / src.name
        shutil.move(str(src), str(dst))
        result[kind] = dst
    csv_src = figures_dir / _EMA_DISTANCE_CSV.format(stem=stem)
    if csv_src.exists():
        csv_dst = cache_dir / csv_src.name
        shutil.move(str(csv_src), str(csv_dst))
        result["pas_distances_csv"] = csv_dst
    else:
        result["pas_distances_csv"] = None
    return result


def generate_geneview(cfg: Config, body: dict) -> dict:
    run_root_raw = body.get("run_root")
    gene_id = body.get("gene_id")
    if not run_root_raw or not gene_id:
        raise GeneviewWorkerError("both 'run_root' and 'gene_id' are required", status=400)
    run_root = Path(run_root_raw)
    _check_allowed_root(run_root, cfg)

    gtf_raw = body.get("gtf")
    gtf = Path(gtf_raw) if gtf_raw else cfg.default_gtf
    force = bool(body.get("force", False))

    # CELLTYPE x STAGE path (primary, 2026-08-14): a `celltype` was
    # requested AND this run actually has combined per-celltype input for
    # it -- see `_resolve_celltype_inputs`'s docstring for why this is the
    # grain the switch-analysis headline needs. Falls through to the
    # per-dataset path (unchanged from the original single-dataset design)
    # when celltype wasn't requested, or this run has no B3_switch/combined/
    # at all (grid/reannotate runs), or no h5ad for this specific celltype.
    celltype = body.get("celltype")
    celltype_inputs = _resolve_celltype_inputs(run_root, celltype) if celltype else None
    if celltype_inputs is not None:
        h5ad, pasbed = celltype_inputs
        key, source = celltype, "celltype"
        cluster_key = body.get("cluster_key") or "stage"
        subtitle = celltype
        response_celltype, response_dataset_id = celltype, None
    else:
        dataset_id, h5ad = _resolve_dataset_h5ad(run_root, body.get("dataset_id"))
        pasbed = _resolve_pasbed(run_root, body.get("pasbed"))
        key, source = dataset_id, "dataset"
        cluster_key = body.get("cluster_key") or "leiden"
        subtitle = None
        response_celltype, response_dataset_id = None, dataset_id

    cache_dir = _cache_dir(run_root, gene_id, key)
    lock_key = str(cache_dir)
    lock = _lock_for(lock_key)
    with lock:
        if not force:
            hit = _cache_hit_files(cache_dir, gene_id)
            if hit is not None:
                return _response(
                    gene_id, response_celltype, response_dataset_id, cluster_key, run_root, hit,
                    cached=True, duration_sec=0.0,
                )

        t0 = time.monotonic()
        figures_dir = _run_ema(cfg, h5ad, gene_id, pasbed, gtf, cluster_key, subtitle=subtitle)
        try:
            files = _move_into_cache(figures_dir, gene_id, key, source, cache_dir)
        finally:
            # request_scratch (figures_dir's grandparent, "out_<ts>") -- always
            # removed, success or failure (a failure here -- e.g. gene has no
            # PAS here -- must not leak scratch dirs any more than a success
            # does).
            shutil.rmtree(figures_dir.parent.parent, ignore_errors=True)
        duration = time.monotonic() - t0
        return _response(
            gene_id, response_celltype, response_dataset_id, cluster_key, run_root, files,
            cached=False, duration_sec=duration,
        )


def _response(
    gene_id: str, celltype: str | None, dataset_id: str | None, cluster_key: str, run_root: Path,
    files: dict[str, Path | None], cached: bool, duration_sec: float,
) -> dict:
    def _rel(p: Path | None) -> str | None:
        return str(p.relative_to(run_root)) if p is not None else None

    return {
        "status": "ok",
        "gene_id": gene_id,
        # Exactly one of these two is non-null -- see generate_geneview's
        # celltype-vs-dataset branch. Both present (one always null) so
        # callers don't have to guess which key space a cache hit resolved
        # to.
        "celltype": celltype,
        "dataset_id": dataset_id,
        "cluster_key": cluster_key,
        "cached": cached,
        "duration_sec": round(duration_sec, 2),
        "files": {k: _rel(v) for k, v in files.items()},
    }


class Handler(BaseHTTPRequestHandler):
    cfg: Config  # set on the class by main() before serve_forever()

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003 -- stdlib override signature
        logger.info("%s - %s", self.address_string(), fmt % args)

    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 -- stdlib method name
        if self.path.rstrip("/") == "/health":
            self._write_json(200, {"status": "ok"})
            return
        self._write_json(404, {"status": "error", "detail": f"unknown path {self.path!r}"})

    def do_POST(self) -> None:  # noqa: N802 -- stdlib method name
        if self.path.rstrip("/") != "/geneview":
            self._write_json(404, {"status": "error", "detail": f"unknown path {self.path!r}"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            self._write_json(400, {"status": "error", "detail": f"invalid JSON body: {exc}"})
            return
        try:
            result = generate_geneview(self.cfg, body)
            self._write_json(200, result)
        except GeneviewWorkerError as exc:
            self._write_json(exc.status, {"status": "error", "detail": str(exc)})
        except Exception:  # noqa: BLE001 -- must never crash the worker process on a bad request
            logger.exception("unhandled error generating geneview for body=%r", body)
            self._write_json(500, {"status": "error", "detail": "internal error, see worker logs: " + traceback.format_exc(limit=3)})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8095)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--ema-bin", required=True, help="Path to the ema executable inside the analysis venv.")
    parser.add_argument("--gtf", default=None, help="Default GTF path used when a request doesn't supply one.")
    parser.add_argument("--scratch-root", required=True, help="Writable scratch dir for per-request ema output/caches (never $HOME).")
    parser.add_argument(
        "--tmp-root", default=None,
        help="SHORT writable dir for per-request TMPDIR (AF_UNIX path-length limit -- see module docstring). "
        "Defaults to --scratch-root if omitted, but pass a short path explicitly in production.",
    )
    parser.add_argument(
        "--allow-root-prefix", action="append", required=True,
        help="A run_root a request supplies must resolve under one of these prefixes (repeatable).",
    )
    parser.add_argument("--timeout-sec", type=int, default=180, help="Per-gene ema subprocess timeout.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = Config(args)
    Handler.cfg = cfg

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    logger.info(
        "geneview_worker listening on %s:%d (ema=%s, scratch_root=%s, allow_root_prefixes=%s)",
        args.host, args.port, cfg.ema_bin, cfg.scratch_root, cfg.allow_root_prefixes,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
