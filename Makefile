.PHONY: setup dev stop agent-dev crawl reindex search focused normalize reindex-incremental tail llm-status llm-models research clean seeds index-inc seed postchat check budget perf
.PHONY: run index clean-index paths

PYTHON ?= python3
# Prefer 3.11 if available
ifeq ($(shell command -v python3.11 >/dev/null 2>&1 && echo yes),yes)
  PYTHON := python3.11
endif

VENV?=.venv
PY:=$(VENV)/bin/python
PIP:=$(VENV)/bin/pip
PLAYWRIGHT:=$(VENV)/bin/playwright

REPO_ROOT := $(shell pwd)
export PYTHONPATH := $(REPO_ROOT)$(if $(PYTHONPATH),:$(PYTHONPATH))

DATA_DIR := $(REPO_ROOT)/data
WHOOSH_DIR := $(DATA_DIR)/whoosh
CHROMA_DIR := $(DATA_DIR)/chroma
DUCKDB_PATH := $(DATA_DIR)/index.duckdb
DEV_STATE_DIR := $(REPO_ROOT)/.dev
FRONTEND_PID_FILE := $(DEV_STATE_DIR)/frontend.pid
BACKEND_PID_FILE := $(DEV_STATE_DIR)/backend.pid

paths:
	@echo "DATA_DIR=$(DATA_DIR)"
	@echo "WHOOSH_DIR=$(WHOOSH_DIR)"
	@echo "CHROMA_DIR=$(CHROMA_DIR)"
	@echo "DUCKDB_PATH=$(DUCKDB_PATH)"
	@echo "NORMALIZED_PATH=${NORMALIZED_PATH:-./data/normalized/normalized.jsonl}"

setup:
	./scripts/ensure_py311.sh $(PYTHON)
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	. $(VENV)/bin/activate && pip install -U pip setuptools wheel && pip install -r requirements.txt && pip install -e .
	$(PLAYWRIGHT) install chromium
	$(PY) -c "import backend; print('backend package import ok')"

dev:
	@bash -c 'set -euo pipefail; \
          FRONTEND_DIR="$(REPO_ROOT)/frontend"; \
          STATE_DIR="$(DEV_STATE_DIR)"; \
          FRONTEND_PID_FILE="$(FRONTEND_PID_FILE)"; \
          BACKEND_PID_FILE="$(BACKEND_PID_FILE)"; \
          mkdir -p "$$STATE_DIR"; \
          set -a; [ -f .env ] && source .env; set +a; \
          FRONTEND_HOST="$${FRONTEND_HOST:-0.0.0.0}"; \
          FRONTEND_PORT="$${FRONTEND_PORT:-3100}"; \
          FRONTEND_ORIGIN_DEFAULT="http://127.0.0.1:$$FRONTEND_PORT"; \
          FRONTEND_ORIGIN="$${FRONTEND_ORIGIN:-$$FRONTEND_ORIGIN_DEFAULT}"; \
          DATA_ROOT="$(DATA_DIR)"; \
          INDEX_DIR="$${INDEX_DIR:-$$DATA_ROOT/whoosh}"; \
          CRAWL_STORE="$${CRAWL_STORE:-$$DATA_ROOT/crawl}"; \
          NORMALIZED_PATH="$${NORMALIZED_PATH:-$$DATA_ROOT/normalized/normalized.jsonl}"; \
          CHROMA_PERSIST_DIR="$${CHROMA_PERSIST_DIR:-$$DATA_ROOT/chroma}"; \
          CHROMADB_DISABLE_TELEMETRY="$${CHROMADB_DISABLE_TELEMETRY:-1}"; \
          BACKEND_PORT="$${BACKEND_PORT:-$${UI_PORT:-$${FLASK_RUN_PORT:-5050}}}"; \
          FLASK_RUN_PORT="$$BACKEND_PORT"; \
          FLASK_RUN_HOST="$${FLASK_RUN_HOST:-127.0.0.1}"; \
          API_HOST="$$FLASK_RUN_HOST"; \
          if [ "$$API_HOST" = "0.0.0.0" ]; then API_HOST="127.0.0.1"; fi; \
          BACKEND_HOST="$$API_HOST"; \
          NEXT_PUBLIC_API_BASE_URL="$${NEXT_PUBLIC_API_BASE_URL:-http://$$API_HOST:$$BACKEND_PORT}"; \
          export INDEX_DIR CRAWL_STORE NORMALIZED_PATH CHROMA_PERSIST_DIR CHROMADB_DISABLE_TELEMETRY FLASK_RUN_PORT FLASK_RUN_HOST FRONTEND_ORIGIN BACKEND_PORT BACKEND_HOST NEXT_PUBLIC_API_BASE_URL; \
          $(PY) bin/dev_check.py; \
          port_in_use() { lsof -ti tcp:"$$1" >/dev/null 2>&1; }; \
          ensure_pid_file() { \
            local file="$$1"; \
            if [ -f "$$file" ]; then \
              local pid; pid=$$(cat "$$file" 2>/dev/null || true); \
              if [ -n "$$pid" ] && kill -0 "$$pid" 2>/dev/null; then \
                echo "$$pid"; \
                return 0; \
              fi; \
              rm -f "$$file"; \
            fi; \
            return 1; \
          }; \
          FRONTEND_EXISTING=""; \
          if pid="$$(ensure_pid_file "$$FRONTEND_PID_FILE" || true)" && [ -n "$$pid" ]; then \
            FRONTEND_EXISTING="$$pid"; \
          fi; \
          BACKEND_EXISTING=""; \
          if pid="$$(ensure_pid_file "$$BACKEND_PID_FILE" || true)" && [ -n "$$pid" ]; then \
            BACKEND_EXISTING="$$pid"; \
          fi; \
          FRONTEND_STARTED=0; BACKEND_STARTED=0; \
          if [ -n "$$FRONTEND_EXISTING" ] && port_in_use "$$FRONTEND_PORT"; then \
            echo "Frontend already running at http://127.0.0.1:$$FRONTEND_PORT (PID $$FRONTEND_EXISTING)."; \
          else \
            FRONTEND_EXISTING=""; \
          fi; \
          if [ -z "$$FRONTEND_EXISTING" ]; then \
            if port_in_use "$$FRONTEND_PORT"; then \
              echo "Port $$FRONTEND_PORT is in use. Run make stop or set FRONTEND_PORT to a free port." >&2; \
              exit 1; \
            fi; \
            pushd "$$FRONTEND_DIR" >/dev/null; \
            npm install >/dev/null; \
            NEXT_PUBLIC_API_BASE_URL="$$NEXT_PUBLIC_API_BASE_URL" npm run dev -- --hostname "$$FRONTEND_HOST" --port "$$FRONTEND_PORT" & \
            FRONTEND_PID=$$!; \
            echo $$FRONTEND_PID > "$$FRONTEND_PID_FILE"; \
            popd >/dev/null; \
            FRONTEND_STARTED=1; \
            echo "Frontend started at http://127.0.0.1:$$FRONTEND_PORT (PID $$FRONTEND_PID)."; \
          else \
            FRONTEND_PID="$$FRONTEND_EXISTING"; \
          fi; \
          BACKEND_MSG_HOST="$$API_HOST"; \
          if [ -n "$$BACKEND_EXISTING" ] && port_in_use "$$BACKEND_PORT"; then \
            echo "Backend already running at http://$$BACKEND_MSG_HOST:$$BACKEND_PORT (PID $$BACKEND_EXISTING)."; \
          else \
            BACKEND_EXISTING=""; \
          fi; \
          if [ -z "$$BACKEND_EXISTING" ]; then \
            if port_in_use "$$BACKEND_PORT"; then \
              echo "Port $$BACKEND_PORT is in use. Run make stop or set BACKEND_PORT to a free port." >&2; \
              exit 1; \
            fi; \
            $(PY) -m flask --app app --debug run & \
            BACKEND_PID=$$!; \
            echo $$BACKEND_PID > "$$BACKEND_PID_FILE"; \
            BACKEND_STARTED=1; \
            echo "Backend started at http://$$BACKEND_MSG_HOST:$$BACKEND_PORT (PID $$BACKEND_PID)."; \
          else \
            BACKEND_PID="$$BACKEND_EXISTING"; \
          fi; \
          cleanup() { \
            if [ $$FRONTEND_STARTED -eq 1 ] && [ -n "$${FRONTEND_PID:-}" ]; then \
              kill "$$FRONTEND_PID" 2>/dev/null || true; \
              rm -f "$$FRONTEND_PID_FILE"; \
            fi; \
            if [ $$BACKEND_STARTED -eq 1 ] && [ -n "$${BACKEND_PID:-}" ]; then \
              kill "$$BACKEND_PID" 2>/dev/null || true; \
              rm -f "$$BACKEND_PID_FILE"; \
            fi; \
          }; \
          trap cleanup EXIT INT TERM; \
          if [ $$FRONTEND_STARTED -eq 0 ] && [ $$BACKEND_STARTED -eq 0 ]; then \
            echo "Dev services already running. Use make stop to stop them."; \
            exit 0; \
          fi; \
          wait_for_any() { \
            while :; do \
              for pid in "$$@"; do \
                if ! kill -0 "$$pid" 2>/dev/null; then \
                  wait "$$pid" 2>/dev/null; \
                  return $$?; \
                fi; \
              done; \
              sleep 0.2; \
            done; \
          }; \
          PIDS=(); \
          if [ $$FRONTEND_STARTED -eq 1 ]; then PIDS+=("$$FRONTEND_PID"); fi; \
          if [ $$BACKEND_STARTED -eq 1 ]; then PIDS+=("$$BACKEND_PID"); fi; \
          if [ $${#PIDS[@]} -eq 1 ]; then \
            wait "$${PIDS[0]}"; \
          else \
            wait_for_any "$${PIDS[@]}"; \
          fi'

stop:
	@bash -c 'set -euo pipefail; \
          STATE_DIR="$(DEV_STATE_DIR)"; \
          FRONTEND_PID_FILE="$(FRONTEND_PID_FILE)"; \
          BACKEND_PID_FILE="$(BACKEND_PID_FILE)"; \
          stop_one() { \
            local label="$$1"; \
            local file="$$2"; \
            if [ ! -f "$$file" ]; then \
              return 1; \
            fi; \
            local pid; pid=$$(cat "$$file" 2>/dev/null || true); \
            if [ -z "$$pid" ]; then \
              rm -f "$$file"; \
              return 0; \
            fi; \
            if kill -0 "$$pid" 2>/dev/null; then \
              echo "Stopping $$label (PID $$pid)..."; \
              kill "$$pid" 2>/dev/null || true; \
              for attempt in 1 2 3 4 5; do \
                if ! kill -0 "$$pid" 2>/dev/null; then break; fi; \
                sleep 0.2; \
              done; \
              if kill -0 "$$pid" 2>/dev/null; then \
                kill -9 "$$pid" 2>/dev/null || true; \
              fi; \
              echo "Stopped $$label."; \
            else \
              echo "Removing stale $$label PID file."; \
            fi; \
            rm -f "$$file"; \
            return 0; \
          }; \
          mkdir -p "$$STATE_DIR"; \
          FRONT_RESULT=1; BACK_RESULT=1; \
          if [ -f "$$FRONTEND_PID_FILE" ]; then stop_one "frontend" "$$FRONTEND_PID_FILE" && FRONT_RESULT=0; fi; \
          if [ -f "$$BACKEND_PID_FILE" ]; then stop_one "backend" "$$BACKEND_PID_FILE" && BACK_RESULT=0; fi; \
          if [ $$FRONT_RESULT -ne 0 ] && [ $$BACK_RESULT -ne 0 ]; then \
            echo "No dev services to stop."; \
          fi'

agent-dev:
	@$(MAKE) dev

run:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; exec $(PY) -m flask --app app --debug run'

index:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; . $(VENV)/bin/activate; exec $(PY) bin/bootstrap_index.py'

clean-index:
	@mkdir -p "$(WHOOSH_DIR)"
	@if [ "$$(realpath $(WHOOSH_DIR))" = "$$(realpath $(REPO_ROOT))" ]; then \
	  echo "Refusing to clean: WHOOSH_DIR resolves to repository root" >&2; exit 2; \
	fi
	@find "$(WHOOSH_DIR)" -maxdepth 1 -type f -name 'MAIN_*' -delete
	@find "$(WHOOSH_DIR)" -maxdepth 1 -type f \( -name '*.seg' -o -name '*_WRITELOCK' \) -delete
	@if [ -d "$(CHROMA_DIR)" ]; then \
	  if [ "$$(realpath $(CHROMA_DIR))" = "$$(realpath $(REPO_ROOT))" ]; then \
	    echo "Refusing to clean: CHROMA_DIR resolves to repository root" >&2; exit 2; \
	  fi; \
	  rm -rf "$(CHROMA_DIR)"; \
	fi
	@rm -f "$(DUCKDB_PATH)"

crawl:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; INDEX_DIR="${INDEX_DIR:-./data/whoosh}"; CRAWL_STORE="${CRAWL_STORE:-./data/crawl}"; export INDEX_DIR CRAWL_STORE URL SEEDS_FILE MAX_PAGES; exec $(PY) bin/crawl.py'

reindex:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; exec $(PY) -m bin.reindex_incremental'

search:
	@if [ -z "$$Q" ]; then echo "Set Q=\"your query\"" >&2; exit 1; fi
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; INDEX_DIR="${INDEX_DIR:-./data/whoosh}"; export INDEX_DIR; exec $(PY) bin/search_cli.py --q "$$Q" --limit "$${LIMIT:-10}"'

focused:
	@if [ -z "$$Q" ]; then echo "Set Q=\"your query\"" >&2; exit 1; fi
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; BUDGET_VALUE=$${BUDGET:-$${FOCUSED_CRAWL_BUDGET:-10}}; STORE="$${CRAWL_STORE:-./data/crawl}"; OUT_DIR="$${STORE%/}/raw"; CMD="$(PY) -m crawler.run --query=\"$$Q\" --budget=$$BUDGET_VALUE --out=$$OUT_DIR"; [ "$$USE_LLM" = "1" ] && CMD="$$CMD --use-llm"; [ -n "$$MODEL" ] && CMD="$$CMD --model=\"$$MODEL\""; eval $$CMD'

normalize:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; exec $(PY) bin/normalize.py'

reindex-incremental:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; exec $(PY) -m bin.reindex_incremental'

seeds:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; exec $(PY) bin/seeds_prepare.py'

seed: seeds

postchat:
	@echo "Review pending plans in data/agent/plans/ and enqueue with /api/tools/enqueue_crawl as needed."

index-inc:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; exec $(PY) bin/index_inc.py --once'

tail:
	@if [ -z "$$JOB" ]; then echo "Set JOB=<identifier> to tail" >&2; exit 1; fi
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; LOG_DIR="${LOGS_DIR:-./data/logs}"; LOG_PATH="$$LOG_DIR/$$JOB.log"; touch "$$LOG_PATH"; tail -n 50 -f "$$LOG_PATH"'

llm-status:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; HOST="${FLASK_RUN_HOST:-127.0.0.1}"; PORT="${BACKEND_PORT:-${UI_PORT:-${FLASK_RUN_PORT:-5050}}}"; curl -s "http://$$HOST:$$PORT/api/llm/status" | python -m json.tool'

llm-models:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; HOST="${FLASK_RUN_HOST:-127.0.0.1}"; PORT="${BACKEND_PORT:-${UI_PORT:-${FLASK_RUN_PORT:-5050}}}"; curl -s "http://$$HOST:$$PORT/api/llm/models" | python -m json.tool'

research:
	@if [ -z "$$Q" ]; then echo "Set Q=\"question\"" >&2; exit 1; fi
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; HOST="${FLASK_RUN_HOST:-127.0.0.1}"; PORT="${BACKEND_PORT:-${UI_PORT:-${FLASK_RUN_PORT:-5050}}}"; curl -s -H "Content-Type: application/json" -X POST "http://$$HOST:$$PORT/api/research" -d "{\"query\": \"$$Q\", \"budget\": $${BUDGET:-20}}" | python -m json.tool'

clean:
	rm -rf $(VENV)
	@if [ -d "$(WHOOSH_DIR)" ]; then rm -rf "$(WHOOSH_DIR)"; fi
	@if [ -d "$(CHROMA_DIR)" ]; then rm -rf "$(CHROMA_DIR)"; fi
	@if [ -d "$(DATA_DIR)/crawl" ]; then rm -rf "$(DATA_DIR)/crawl"; fi
	@rm -f "$(DUCKDB_PATH)"

check:
	pytest -q
	ruff check server scripts policy
	black --check server/agent_tools_repo.py server/agent_policy.py scripts/change_budget.py scripts/perf_smoke.py tests/e2e/test_agent_patch_flow.py
	mypy --ignore-missing-imports server/agent_tools_repo.py server/agent_policy.py scripts/change_budget.py scripts/perf_smoke.py
	pip-audit -r requirements.txt || true
	bandit -q server/agent_tools_repo.py scripts/change_budget.py scripts/perf_smoke.py
	python scripts/perf_smoke.py

budget:
	python scripts/change_budget.py

perf:
	python scripts/perf_smoke.py
