# peakatail-hub — run it two ways: NATIVE (uv/npm) or DOCKER (compose).
# `make help` lists everything.  Native is fastest for dev; docker is one-command.

SHELL := /bin/bash

# --- shared knobs (override on the CLI, e.g. `make up PEAKATAIL_RUNS=/data/runs`) ---
HUB_DB_PATH ?= /tmp/hub.duckdb                 # native: DuckDB file
RUNS        ?= packages/contract/fixtures      # native: dir to index (run_manifest.json root)
API_PORT    ?= 8000
WEB_PORT    ?= 5173
# docker: HOST runs-root mounted READ-ONLY into the backend as /runs (default: fixtures)
export PEAKATAIL_RUNS ?= ./packages/contract/fixtures
export HUB_API_PORT   ?= $(API_PORT)
export HUB_WEB_PORT   ?= $(WEB_PORT)
COMPOSE := docker compose

.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "peakatail-hub"
	@echo ""
	@echo "NATIVE (uv + npm) — run backend and frontend in two terminals:"
	@echo "  make install      set up all Python venvs (uv 3.12) + frontend npm deps"
	@echo "  make index        build DuckDB from RUNS=$(RUNS) -> HUB_DB_PATH=$(HUB_DB_PATH)"
	@echo "  make backend      run the API (uv run hub serve, :$(API_PORT))"
	@echo "  make frontend     run the vite dev server (:$(WEB_PORT), real backend)"
	@echo "  make test         run all suites (contract / io / backend / frontend)"
	@echo "  make stop-native  kill locally-started hub serve / vite"
	@echo ""
	@echo "DOCKER (compose) — one command, both services:"
	@echo "  make build        build backend + frontend images"
	@echo "  make up           build + index PEAKATAIL_RUNS + start -> http://localhost:$(WEB_PORT)"
	@echo "  make down         stop + remove containers"
	@echo "  make reindex      re-index PEAKATAIL_RUNS (stops backend, indexes, restarts)"
	@echo "  make logs / ps    tail logs / show status"
	@echo "  make clean        down + remove volumes (DuckDB/cache) and built images"
	@echo ""
	@echo "  Point at REAL data (read-only mount):"
	@echo "    PEAKATAIL_RUNS=/path/to/runs_root make up"

# ============================ NATIVE (uv / npm) ============================
.PHONY: install
install:
	cd packages/contract && uv venv --python 3.12 && uv sync --extra test
	cd packages/io       && uv venv --python 3.12 && uv sync --extra test
	cd backend           && uv venv --python 3.12 && uv sync --extra test
	cd frontend          && npm install

.PHONY: index
index:
	cd backend && HUB_DB_PATH=$(HUB_DB_PATH) uv run hub index ../$(RUNS)

.PHONY: backend
backend:
	cd backend && HUB_DB_PATH=$(HUB_DB_PATH) uv run hub serve --host 127.0.0.1 --port $(API_PORT)

.PHONY: frontend
frontend:
	cd frontend && VITE_USE_MOCKS=false npm run dev -- --port $(WEB_PORT)

.PHONY: test
test:
	cd packages/contract && uv run pytest -q
	cd packages/io       && uv run pytest -q
	cd backend           && uv run pytest -q
	cd frontend          && npx tsc -b && npx vitest run

.PHONY: stop-native
stop-native:
	-pkill -f "hub serve" 2>/dev/null || true
	-pkill -f "vite --port" 2>/dev/null || true
	@echo "stopped native hub serve / vite (if running)"

# ============================ DOCKER (compose) ============================
.PHONY: build
build:
	$(COMPOSE) build

# index the read-only-mounted /runs into the shared DuckDB volume (one-shot container)
.PHONY: docker-index
docker-index:
	$(COMPOSE) run --rm --no-deps backend hub index /runs

.PHONY: up
up: build
	$(COMPOSE) run --rm --no-deps backend hub index /runs
	$(COMPOSE) up -d
	@echo ""
	@echo "peakatail-hub is up -> http://localhost:$(HUB_WEB_PORT)   (API: http://localhost:$(HUB_API_PORT))"
	@echo "indexed from PEAKATAIL_RUNS=$(PEAKATAIL_RUNS) (read-only)"

.PHONY: down
down:
	$(COMPOSE) down

# backend holds a read-write lock on the DuckDB volume, so stop it before re-indexing
.PHONY: reindex
reindex:
	$(COMPOSE) stop backend
	$(COMPOSE) run --rm --no-deps backend hub index /runs
	$(COMPOSE) start backend

.PHONY: logs
logs:
	$(COMPOSE) logs -f

.PHONY: ps
ps:
	$(COMPOSE) ps

.PHONY: clean
clean:
	$(COMPOSE) down -v --rmi local
