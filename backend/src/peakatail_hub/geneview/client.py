"""HTTP client for the host-side geneview worker
(`geneview-worker/geneview_worker.py`). Stdlib `urllib.request` only --
matches this backend's "dep-light" posture (spec §7a); this is a single,
low-frequency POST per cache-miss, not worth a new httpx/requests runtime
dependency.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from peakatail_hub import config

logger = logging.getLogger("peakatail_hub.geneview")


class GeneviewWorkerError(Exception):
    """Raised for any failure talking to the geneview worker: unreachable
    (connection refused/DNS -- the worker isn't running, or
    `HUB_GENEVIEW_WORKER_URL`/Docker `extra_hosts` isn't configured),
    timed out, or the worker itself returned a structured error (bad
    gene_id, ema failure, disallowed run_root, ...). Callers (api/geneview.py)
    catch this ONE exception type and turn it into a clean HTTP error
    response -- never an unhandled 500 with a raw urllib traceback.
    """

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def request_geneview(
    run_root_host: str,
    gene_id: str,
    celltype: str | None = None,
    dataset_id: str | None = None,
    cluster_key: str | None = None,
    force: bool = False,
) -> dict:
    """POST to the geneview worker's `/geneview` endpoint. `run_root_host`
    MUST be the run's HOST filesystem path (`runs.root` in the DuckDB store,
    straight from the run's manifest) -- the worker runs on the host and has
    no notion of this container's `/runs` mount. Blocks for up to
    `config.geneview_worker_timeout_sec()` (default 180s -- generation
    itself was measured at ~11-15s for one gene against one dataset/celltype
    on real cohort data; the generous ceiling covers a cold-cache burst of
    several concurrent first-opens).

    `celltype`, when given, requests the CELLTYPE x STAGE render grain (the
    switch-analysis headline: 3'UTR length across disease stages, within one
    cell type) -- the worker uses it when this run has a matching
    `B3_switch/combined/<celltype>.h5ad`, and transparently falls back to
    the per-dataset path (using `dataset_id` if given, else its own
    deterministic default) when it doesn't (grid/reannotate runs -- no
    switch analysis). `cluster_key` defaults to whatever the worker itself
    defaults to for the resolved path ('stage' for celltype, 'leiden' for
    dataset) when omitted -- pass it explicitly only to override.

    Returns the worker's parsed JSON response (`{status, gene_id, celltype,
    dataset_id, cluster_key, cached, duration_sec, files: {...}}` -- exactly
    one of `celltype`/`dataset_id` is non-null, reflecting which path was
    actually used) on success. Raises `GeneviewWorkerError` on any failure
    -- connection refused, timeout, or a structured `{status: "error",
    detail: ...}` body from the worker itself (its own status code is
    forwarded).
    """
    url = f"{config.geneview_worker_url().rstrip('/')}/geneview"
    body = json.dumps(
        {
            "run_root": run_root_host,
            "gene_id": gene_id,
            "celltype": celltype,
            "dataset_id": dataset_id,
            "cluster_key": cluster_key,
            "force": force,
        }
    ).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    timeout = config.geneview_worker_timeout_sec()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read())
            detail = payload.get("detail", str(exc))
        except Exception:  # noqa: BLE001 -- worker's error body wasn't parseable JSON
            detail = str(exc)
        raise GeneviewWorkerError(detail, status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise GeneviewWorkerError(
            f"geneview worker unreachable at {url} ({exc.reason}) -- is geneview_worker.py running on the "
            "host, and is HUB_GENEVIEW_WORKER_URL / the backend service's Docker extra_hosts configured?",
            status=503,
        ) from exc
    except TimeoutError as exc:
        raise GeneviewWorkerError(f"geneview worker timed out after {timeout}s for gene_id={gene_id!r}", status=504) from exc

    if payload.get("status") != "ok":
        raise GeneviewWorkerError(payload.get("detail", "geneview worker returned an unrecognized response"), status=502)
    return payload
