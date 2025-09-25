.PHONY: setup dev crawl reindex search focused normalize reindex-incremental tail llm-status llm-models research clean seeds index-inc
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

paths:
	@echo "DATA_DIR=$(DATA_DIR)"
	@echo "WHOOSH_DIR=$(WHOOSH_DIR)"
	@echo "CHROMA_DIR=$(CHROMA_DIR)"
	@echo "DUCKDB_PATH=$(DUCKDB_PATH)"
	@echo "NORMALIZED_PATH=${NORMALIZED_PATH:-./data/normalized/normalized.jsonl}"

setup:
	./scripts/ensure_py311.sh $(PYTHON)
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	. $(VENV)/bin/activate && pip install -U pip setuptools wheel && pip install -r requirements.txt
	$(PLAYWRIGHT) install chromium

dev:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; INDEX_DIR="${INDEX_DIR:-./data/whoosh}"; CRAWL_STORE="${CRAWL_STORE:-./data/crawl}"; NORMALIZED_PATH="${NORMALIZED_PATH:-./data/normalized/normalized.jsonl}"; CHROMA_PERSIST_DIR="${CHROMA_PERSIST_DIR:-./data/chroma}"; CHROMADB_DISABLE_TELEMETRY="${CHROMADB_DISABLE_TELEMETRY:-1}"; FLASK_RUN_PORT="${UI_PORT:-${FLASK_RUN_PORT:-5000}}"; FLASK_RUN_HOST="${FLASK_RUN_HOST:-127.0.0.1}"; export INDEX_DIR CRAWL_STORE NORMALIZED_PATH CHROMA_PERSIST_DIR CHROMADB_DISABLE_TELEMETRY FLASK_RUN_PORT FLASK_RUN_HOST; $(PY) bin/dev_check.py; exec $(PY) -m flask --app app --debug run'

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

index-inc:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; exec $(PY) bin/index_inc.py --once'

tail:
	@if [ -z "$$JOB" ]; then echo "Set JOB=<identifier> to tail" >&2; exit 1; fi
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; LOG_DIR="${LOGS_DIR:-./data/logs}"; LOG_PATH="$$LOG_DIR/$$JOB.log"; touch "$$LOG_PATH"; tail -n 50 -f "$$LOG_PATH"'

llm-status:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; HOST="${FLASK_RUN_HOST:-127.0.0.1}"; PORT="${UI_PORT:-${FLASK_RUN_PORT:-5000}}"; curl -s "http://$$HOST:$$PORT/api/llm/status" | python -m json.tool'

llm-models:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; HOST="${FLASK_RUN_HOST:-127.0.0.1}"; PORT="${UI_PORT:-${FLASK_RUN_PORT:-5000}}"; curl -s "http://$$HOST:$$PORT/api/llm/models" | python -m json.tool'

research:
	@if [ -z "$$Q" ]; then echo "Set Q=\"question\"" >&2; exit 1; fi
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; HOST="${FLASK_RUN_HOST:-127.0.0.1}"; PORT="${UI_PORT:-${FLASK_RUN_PORT:-5000}}"; curl -s -H "Content-Type: application/json" -X POST "http://$$HOST:$$PORT/api/research" -d "{\"query\": \"$$Q\", \"budget\": $${BUDGET:-20}}" | python -m json.tool'

clean:
	rm -rf $(VENV)
	@if [ -d "$(WHOOSH_DIR)" ]; then rm -rf "$(WHOOSH_DIR)"; fi
	@if [ -d "$(CHROMA_DIR)" ]; then rm -rf "$(CHROMA_DIR)"; fi
	@if [ -d "$(DATA_DIR)/crawl" ]; then rm -rf "$(DATA_DIR)/crawl"; fi
	@rm -f "$(DUCKDB_PATH)"
