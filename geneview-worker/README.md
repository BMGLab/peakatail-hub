# geneview-worker

A tiny (stdlib-only) HTTP service that runs `ema switch geneview` on demand,
on the **host** where the `ema` analysis venv actually lives, and hands the
resulting figures back to the peakatail-hub backend container (which has no
`ema` installed — see `backend/src/peakatail_hub/geneview/` for the
container-side half of this split, and that package's docstrings /
`geneview_worker.py`'s own module docstring for the full design rationale).

## Why a separate process instead of putting this in the backend image

`ema` and its scientific-Python stack (anndata, scanpy, plotly, matplotlib,
...) only exist in the analysis venv on the host
(`/mnt/ssd2/Laugney_Aligned/.peakatail_env` on the deployment server this was
built against). The hub backend's Docker image is deliberately dep-light
(spec §7a) and does not — and should not — bundle `ema`. So generation has
to happen out-of-container: the backend calls this worker over HTTP; the
worker runs `ema switch geneview` as a subprocess and writes the output
directly onto the host filesystem, inside the run directory the backend
already mounts **read-only**. The container never needs write access to run
data — it only ever reads back what this worker wrote.

## Running it

Zero extra Python dependencies — run it with the **ema venv's own**
interpreter:

```bash
TMPDIR=/mnt/ssd2/Laugney_Aligned/rt \
/mnt/ssd2/Laugney_Aligned/.peakatail_env/bin/python geneview_worker.py \
    --port 8095 \
    --ema-bin /mnt/ssd2/Laugney_Aligned/.peakatail_env/bin/ema \
    --gtf /home/sharedFolder/humanSTARindex/Homo_sapiens.GRCh38.99.gtf \
    --scratch-root /mnt/ssd2/Laugney_Aligned/rt/geneview_worker_scratch \
    --tmp-root /mnt/ssd2/Laugney_Aligned/rt \
    --allow-root-prefix /mnt/ssd2/Laugney_Aligned/peakatail_experiments
```

Flags:

- `--ema-bin` — path to the `ema` executable inside the analysis venv.
- `--gtf` — default GTF used when a request doesn't supply one (real runs'
  `resolved_config.directories.gtf_dir` isn't always a usable path from the
  worker's perspective, so the backend currently doesn't forward a
  per-request GTF — this default is what's actually used).
- `--scratch-root` — a writable scratch dir for per-request `ema -o` output
  before it's moved into the run's cache dir (**never `$HOME`** — it fills
  up fast on constrained hosts).
- `--tmp-root` — a **SHORT** writable dir for per-request `TMPDIR`.
  Deliberately separate from `--scratch-root`: `ema switch geneview` spins
  up a multiprocessing `SyncManager` that binds an AF_UNIX socket under
  `$TMPDIR`, and Linux caps that path at ~108 bytes. A `--scratch-root`
  nested path (`.../geneview_worker_scratch/gv_<long-gene-id>_<random>/tmp`)
  blows that limit outright — reproduced verbatim while building this
  worker (`OSError: AF_UNIX path too long`). Point this at something short
  like `/mnt/ssd2/Laugney_Aligned/rt` (the analysis cohort's own existing
  short-tmpdir convention).
- `--allow-root-prefix` (repeatable) — a `run_root` a request supplies must
  resolve under one of these prefixes, or the worker refuses to touch it
  (this worker executes an arbitrary local subprocess against whatever path
  a caller sends — treat it as a private, backend-only service, never
  expose its port publicly).
- `--timeout-sec` — per-gene `ema` subprocess timeout (default 180s; a real
  single-dataset render was measured at ~11s).

### Keeping it running (systemd)

```ini
# /etc/systemd/system/peakatail-geneview-worker.service
[Unit]
Description=peakatail-hub geneview worker (ema switch geneview on demand)
After=network.target

[Service]
Type=simple
User=amiramiritabat
Environment=TMPDIR=/mnt/ssd2/Laugney_Aligned/rt
ExecStart=/mnt/ssd2/Laugney_Aligned/.peakatail_env/bin/python \
    /mnt/ssd2/Laugney_Aligned/hub/peakatail-hub/geneview-worker/geneview_worker.py \
    --port 8095 \
    --ema-bin /mnt/ssd2/Laugney_Aligned/.peakatail_env/bin/ema \
    --gtf /home/sharedFolder/humanSTARindex/Homo_sapiens.GRCh38.99.gtf \
    --scratch-root /mnt/ssd2/Laugney_Aligned/rt/geneview_worker_scratch \
    --tmp-root /mnt/ssd2/Laugney_Aligned/rt \
    --allow-root-prefix /mnt/ssd2/Laugney_Aligned/peakatail_experiments
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now peakatail-geneview-worker
```

(A plain `nohup ... &` works fine for a quick manual start/test too — that's
how this was verified while building it, see the PR/commit description for
the exact commands run against real `B1_cohort_full` data.)

## Wiring it to the hub backend

The backend container needs two things (already set as defaults in
`docker-compose.yml`, override via `.env` / shell env if your deployment
differs):

- `extra_hosts: ["host.docker.internal:host-gateway"]` on the `backend`
  service — lets the container reach a process listening on the host (Linux
  Docker Engine 20.10+; automatic on Docker Desktop).
- `HUB_GENEVIEW_WORKER_URL` (default `http://host.docker.internal:8095`) —
  where the backend sends `POST /geneview` requests.
- `HUB_RUNS_ROOT_HOST` — **must equal** `PEAKATAIL_RUNS` (the same host path
  already mounted as the container's `/runs`). The backend needs this to
  translate a run's `root` (always a HOST path, from its own manifest) back
  into a container-relative `/runs/...` path when reading the figures this
  worker wrote — see `backend/src/peakatail_hub/geneview/paths.py`.

## HTTP API

`GET /health` → `{"status": "ok"}`

`POST /geneview` — body:

```json
{
  "run_root": "/mnt/ssd2/Laugney_Aligned/peakatail_experiments/RERUN_2026-08_fixed/runs/B1_cohort_full",
  "gene_id": "ENSG00000254087",
  "dataset_id": null,
  "cluster_key": "leiden",
  "force": false
}
```

- `run_root` and `gene_id` are required; `run_root` must resolve under one
  of the worker's `--allow-root-prefix` values.
- `dataset_id` (optional) — which `07_clustering/<dataset_id>/clusters.h5ad`
  to render from. Omit it and the worker deterministically picks the
  alphabetically-first dataset with a `clusters.h5ad` (so repeat calls
  without a `dataset_id` always hit the same cache path). A cohort run's
  clustering is per-dataset (no single unified `clusters.h5ad`); rendering
  against one representative dataset — rather than concatenating all of
  them on the fly — is what keeps a cold-cache "first open" a ~10s
  operation instead of a multi-minute one.
- `cluster_key` (default `"leiden"`) — the `obs` column ema colors
  clusters by.
- `force` (default `false`) — bypass the on-disk cache and re-render even
  if a cached figure already exists.

Success response:

```json
{
  "status": "ok",
  "gene_id": "ENSG00000254087",
  "dataset_id": "GSM3516662-StageIA",
  "cluster_key": "leiden",
  "cached": false,
  "duration_sec": 10.88,
  "files": {
    "html": "B3_switch/geneview_cache/ENSG00000254087/GSM3516662-StageIA/gene_ENSG00000254087.html",
    "png": "...gene_ENSG00000254087.png",
    "svg": "...gene_ENSG00000254087.svg",
    "meta_json": "...gene_ENSG00000254087.meta.json",
    "pas_distances_csv": "...gene_ENSG00000254087_pas_distances.csv"
  }
}
```

`files` paths are relative to `run_root`. Error response (any non-2xx):
`{"status": "error", "detail": "..."}`.

## Verified against real data (2026-08-13/14)

Ran directly against `B1_cohort_full` (17-dataset cohort run) on the
analysis server, gene `ENSG00000254087` (LYN):

- Cache miss: `ema switch geneview -i 07_clustering/GSM3516662-StageIA/clusters.h5ad
  --gene-id ENSG00000254087 --pasbed pasbed.bed --gtf .../Homo_sapiens.GRCh38.99.gtf
  --cluster-key leiden --plot-engine both --pas-distance-table --no-progress`
  → 10.9s wall clock, wrote a real interactive plotly HTML (82KB, plotly.js
  CDN reference), a real matplotlib PNG (425KB) + SVG, a `meta.json`
  (gene_name=LYN, chrom 8, 5 PAS, 4 isoforms, cluster_cap_applied), and a
  `_pas_distances.csv` (5 PAS, rank/summit_pos/gap_to_next_bp columns).
- Cache hit (identical request repeated): 0.05s, same files, zero new `ema`
  invocation.
- Error paths: `run_root` outside `--allow-root-prefix` → 403; missing
  `gene_id` → 400; nonexistent `dataset_id` → 404; `ema` non-zero exit →
  500 with the real stderr tail; timeout → 504. None of these leave a
  partial/corrupt cache directory behind.
- A `reannotate/*` run with no pre-existing `B3_switch/` directory at all
  generated correctly on first request (directory created on demand).
