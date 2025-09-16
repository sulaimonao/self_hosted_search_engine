.PHONY: setup dev crawl reindex search focused llm-status llm-models clean

VENV?=.venv
PYTHON?=python3
PY:=$(VENV)/bin/python
PIP:=$(VENV)/bin/pip
PLAYWRIGHT:=$(VENV)/bin/playwright

setup:
	./scripts/ensure_py311.sh $(PYTHON)
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip setuptools wheel
	$(PIP) install -r requirements.txt
	$(PLAYWRIGHT) install chromium

dev:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; INDEX_DIR="${INDEX_DIR:-./data/index}"; CRAWL_STORE="${CRAWL_STORE:-./data/crawl}"; FLASK_RUN_PORT="${UI_PORT:-${FLASK_RUN_PORT:-5000}}"; FLASK_RUN_HOST="${FLASK_RUN_HOST:-127.0.0.1}"; export INDEX_DIR CRAWL_STORE FLASK_RUN_PORT FLASK_RUN_HOST; $(PY) bin/dev_check.py; exec $(PY) -m flask --app app --debug run'

crawl:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; INDEX_DIR="${INDEX_DIR:-./data/index}"; CRAWL_STORE="${CRAWL_STORE:-./data/crawl}"; export INDEX_DIR CRAWL_STORE URL SEEDS_FILE MAX_PAGES; exec $(PY) bin/crawl.py'

reindex:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; INDEX_DIR="${INDEX_DIR:-./data/index}"; CRAWL_STORE="${CRAWL_STORE:-./data/crawl}"; export INDEX_DIR CRAWL_STORE; exec $(PY) bin/reindex.py'

search:
	@if [ -z "$$Q" ]; then echo "Set Q=\"your query\"" >&2; exit 1; fi
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; INDEX_DIR="${INDEX_DIR:-./data/index}"; export INDEX_DIR; exec $(PY) bin/search_cli.py --q "$$Q" --limit "$${LIMIT:-10}"'

focused:
	@if [ -z "$$Q" ]; then echo "Set Q=\"your query\"" >&2; exit 1; fi
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; BUDGET_VALUE=$${BUDGET:-$${FOCUSED_CRAWL_BUDGET:-50}}; USE_LLM_FLAG=""; [ -n "$$USE_LLM" ] && USE_LLM_FLAG="--use-llm"; MODEL_FLAG=""; [ -n "$$MODEL" ] && MODEL_FLAG="--model \"$$MODEL\""; exec $(PY) bin/crawl_focused.py --q "$$Q" --budget "$$BUDGET_VALUE" $$USE_LLM_FLAG $$MODEL_FLAG'

llm-status:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; HOST="${FLASK_RUN_HOST:-127.0.0.1}"; PORT="${UI_PORT:-${FLASK_RUN_PORT:-5000}}"; curl -s "http://$$HOST:$$PORT/api/llm/status" | python -m json.tool'

llm-models:
	@bash -c 'set -euo pipefail; set -a; [ -f .env ] && source .env; set +a; HOST="${FLASK_RUN_HOST:-127.0.0.1}"; PORT="${UI_PORT:-${FLASK_RUN_PORT:-5000}}"; curl -s "http://$$HOST:$$PORT/api/llm/models" | python -m json.tool'

clean:
	rm -rf $(VENV)
	rm -rf data/index data/crawl
