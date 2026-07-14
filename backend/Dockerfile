# syntax=docker/dockerfile:1
# peakatail-hub backend: FastAPI + DuckDB + the two local packages (contract, io).
# NOTE: build context MUST be the repo root — backend/pyproject.toml pulls
#       ../packages/contract and ../packages/io as editable local sources.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
# local editable deps first (better layer caching), then the backend itself
COPY packages/contract ./packages/contract
COPY packages/io ./packages/io
COPY backend ./backend

WORKDIR /app/backend
# resolve + install base runtime deps into /app/backend/.venv
# (fastapi/duckdb/pyarrow/pandas + contract + io -> anndata/h5py/scipy, wheels)
RUN uv sync --no-dev

ENV PATH="/app/backend/.venv/bin:$PATH" \
    HUB_DB_PATH=/data/hub.duckdb \
    HUB_CACHE_DIR=/cache
EXPOSE 8000
# 0.0.0.0 so the port is reachable from the host / other compose services
CMD ["hub", "serve", "--host", "0.0.0.0", "--port", "8000"]
