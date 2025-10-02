
.PHONY: bootstrap dev stop logs verify first-run preflight setup

FRONTEND_PORT ?= 3100
BACKEND_PORT  ?= 5050
API_URL := http://127.0.0.1:$(BACKEND_PORT)/api/llm/health
PY ?= python3.11
VENV ?= .venv
VENV_DIR := $(CURDIR)/$(VENV)
VENV_BIN := $(VENV_DIR)/bin
VENV_PY := $(VENV_BIN)/python
PIP := $(VENV_PY) -m pip

# Expected command identifiers for dev processes; keep aligned with dev target.
# Bracket trick avoids matching the managing shell that embeds these patterns.
BACKEND_CMD_PATTERN := [p]ython -m backend.app
FRONTEND_CMD_PATTERN := [n]ext dev

setup:
	@test -d "$(VENV_DIR)" || $(PY) -m venv "$(VENV_DIR)"
	@$(PIP) -q install -U pip wheel
	@if [ -f requirements.txt ]; then $(PIP) -q install -r requirements.txt; fi
	@if [ -f requirements-dev.txt ]; then $(PIP) -q install -r requirements-dev.txt; fi

bootstrap:
	@bash scripts/bootstrap.sh

dev:
	@# If stdout is not a TTY, skip (prevents sandboxes from hanging)
	@if [ ! -t 1 ]; then \
	  echo "Non-interactive environment detected; skipping 'make dev'."; \
	  echo "Run 'make verify' instead."; \
	  exit 0; \
	fi
	@missing=0; \
	if [ ! -x "$(VENV_PY)" ]; then \
	  echo "⚠️  Missing backend virtualenv at $(VENV_PY)."; \
	  missing=1; \
	fi; \
	if [ ! -d frontend/node_modules ]; then \
	  echo "⚠️  Missing frontend/node_modules (npm deps)."; \
	  missing=1; \
	fi; \
	if [ $$missing -eq 1 ]; then \
	  echo "▶ Running make bootstrap (first-run setup)…"; \
	  $(MAKE) bootstrap; \
	fi
	@# Detached with nohup so dev survives terminal exits; logs in logs/*.log
	@echo "▶ Starting API (Flask)…"
	@if ! lsof -iTCP:$(BACKEND_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
	  mkdir -p logs; \
	  (BACKEND_PORT=$(BACKEND_PORT) nohup $(VENV_PY) -m backend.app > logs/backend.log 2>&1 & echo $$! > logs/backend.pid) ; \
	fi
	@echo "⏳ Waiting for API…"
	@bash -c 'for i in $$(seq 1 60); do curl -fsS "$(API_URL)" >/dev/null && exit 0; sleep 0.5; done; echo "API not ready" >&2; exit 1'
	@echo "▶ Starting Frontend (Next.js)…"
	@if ! lsof -iTCP:$(FRONTEND_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
	  mkdir -p logs; \
	  (cd frontend && nohup npm run dev -- --hostname 0.0.0.0 --port $(FRONTEND_PORT) > ../logs/frontend.log 2>&1 & echo $$! > ../logs/frontend.pid) ; \
	fi
	@echo "✅ UI http://127.0.0.1:$(FRONTEND_PORT)  |  API http://127.0.0.1:$(BACKEND_PORT)"

stop:
	@echo "🛑 Stopping dev processes…"
	@BACKEND_PIDS=""; \
	if [ -f logs/backend.pid ]; then \
	  BACKEND_PIDS=$$(tr '\n' ' ' < logs/backend.pid); \
	else \
	  BACKEND_PIDS=$$(pgrep -f "$(BACKEND_CMD_PATTERN)" | tr '\n' ' ' || true); \
	fi; \
	if [ -n "$$BACKEND_PIDS" ]; then \
	  if kill -0 $$BACKEND_PIDS >/dev/null 2>&1; then \
	    kill $$BACKEND_PIDS >/dev/null 2>&1 && echo "Stopped backend ($$BACKEND_PIDS)" || true; \
	  else \
	    echo "Backend process not running"; \
	  fi; \
	else \
	  echo "No backend process found"; \
	fi; \
	rm -f logs/backend.pid
	@FRONTEND_PIDS=""; \
	if [ -f logs/frontend.pid ]; then \
	  FRONTEND_PIDS=$$(tr '\n' ' ' < logs/frontend.pid); \
	else \
	  FRONTEND_PIDS=$$(pgrep -f "$(FRONTEND_CMD_PATTERN)" | tr '\n' ' ' || true); \
	fi; \
	if [ -n "$$FRONTEND_PIDS" ]; then \
	  if kill -0 $$FRONTEND_PIDS >/dev/null 2>&1; then \
	    kill $$FRONTEND_PIDS >/dev/null 2>&1 && echo "Stopped frontend ($$FRONTEND_PIDS)" || true; \
	  else \
	    echo "Frontend process not running"; \
	  fi; \
	else \
	  echo "No frontend process found"; \
	fi; \
	rm -f logs/frontend.pid

logs:
	@echo "— Flask —"; pgrep -fl "$(BACKEND_CMD_PATTERN)" || echo "(no backend process)"
	@echo "— Next —";  pgrep -fl "$(FRONTEND_CMD_PATTERN)" || echo "(no frontend process)"

verify: setup
	@echo "== Verify =="
	@$(VENV_PY) -V
	@PATH="$(VENV_BIN):$$PATH"; \
	  if command -v ruff >/dev/null 2>&1; then \
	    ruff check .; \
	  else \
	    echo "Skipping ruff (not installed)"; \
	  fi
	@PATH="$(VENV_BIN):$$PATH"; \
	  if command -v black >/dev/null 2>&1; then \
	    black --check .; \
	  else \
	    echo "Skipping black (not installed)"; \
	  fi
	@PATH="$(VENV_BIN):$$PATH"; \
	  if command -v mypy >/dev/null 2>&1; then \
	    mypy; \
	  else \
	    echo "Skipping mypy (not installed)"; \
	  fi
	@PYTHONUNBUFFERED=1 SKIP_E2E=1 SKIP_CRAWL=1 $(VENV_PY) -m pytest -q

first-run: setup
	@echo "Preparing minimal fixtures..."
	@mkdir -p data/normalized
	@if [ ! -f data/normalized/normalized.jsonl ]; then \
	  echo '{"url":"about:blank","title":"seed","text":"hello"}' > data/normalized/normalized.jsonl ; \
	  echo "Wrote sample data/normalized/normalized.jsonl"; \
	fi
	@echo "▶ Installing backend in editable mode"
	@$(PIP) install -e .
	@if [ ! -d frontend/node_modules ]; then \
	  echo "▶ Installing frontend dependencies"; \
	  (cd frontend && npm install --no-audit --no-fund); \
	else \
	  echo "▶ Frontend dependencies already present"; \
	fi
	@echo "First-run ready. Use `make verify` next."

preflight:
	@bash scripts/preflight.sh
