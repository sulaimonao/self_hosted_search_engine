
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
MYPY_TARGETS ?= app.py backend crawler engine frontier llm rank search seed_loader server scripts tests

# Expected command identifiers for dev processes; keep aligned with dev target.
# Bracket trick avoids matching the managing shell that embeds these patterns.
BACKEND_CMD_PATTERN := [p]ython -m backend.app
FRONTEND_CMD_PATTERN := [n]ext dev

setup:
	@py_cmd="$${PY:-python3.11}"; \
	if ! command -v "$$py_cmd" >/dev/null 2>&1; then \
	  for candidate in python3 python; do \
	    if command -v "$$candidate" >/dev/null 2>&1; then \
	      py_cmd="$$candidate"; \
	      break; \
	    fi; \
	  done; \
	fi; \
	if ! command -v "$$py_cmd" >/dev/null 2>&1; then \
	  echo "✖ No suitable Python interpreter found (tried $$py_cmd, python3, python)."; \
	  echo "  Set PY=/path/to/python if installed elsewhere."; \
	  exit 1; \
	fi; \
	if [ ! -d "$(VENV_DIR)" ]; then \
	  echo "Creating virtualenv at $(VENV_DIR) with $$py_cmd"; \
	  "$$py_cmd" -m venv "$(VENV_DIR)"; \
	fi; \
	echo "Installing Python dependencies..."; \
	"$(VENV_PY)" -m pip install -U pip wheel >/dev/null; \
	if [ -f requirements.txt ]; then \
	  "$(VENV_PY)" -m pip install -r requirements.txt; \
	fi; \
	if [ -f requirements-dev.txt ]; then \
	  "$(VENV_PY)" -m pip install -r requirements-dev.txt; \
	fi

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
	  echo "▶ Running make first-run (initial setup)…"; \
	  $(MAKE) first-run; \
	fi
	@# Detached with nohup so dev survives terminal exits; logs in logs/*.log
	@BACKEND_PORT="$(BACKEND_PORT)" API_URL="$(API_URL)" VENV_PY="$(VENV_PY)" ./scripts/dev_backend.sh
	@echo "▶ Starting Frontend (Next.js)…"
	@if ! lsof -iTCP:$(FRONTEND_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
	  mkdir -p logs; \
	  (cd frontend && \
	    if [ -z "$$NEXT_PUBLIC_API_BASE_URL" ]; then \
	      export NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:$(BACKEND_PORT); \
	    fi; \
	    nohup npm run dev -- --hostname 0.0.0.0 --port $(FRONTEND_PORT) > ../logs/frontend.log 2>&1 & echo $$! > ../logs/frontend.pid \
	  ) ; \
	fi
	@API_ORIGIN="$${NEXT_PUBLIC_API_BASE_URL}"; \
	if [ -z "$$API_ORIGIN" ]; then \
	  API_ORIGIN="http://127.0.0.1:$(BACKEND_PORT)"; \
	fi; \
	API_ORIGIN="$$(printf "%s" "$$API_ORIGIN" | sed 's:/*$$::')"; \
	echo "✅ UI http://127.0.0.1:$(FRONTEND_PORT)  |  API $$API_ORIGIN"
	@if [ "$(AUTO_OPEN_BROWSER)" = "1" ]; then \
	  URL="http://127.0.0.1:$(FRONTEND_PORT)"; \
	  OS=$$(uname -s); \
	  case "$$OS" in \
	    Darwin) \
	      (open "$$URL" >/dev/null 2>&1 &) || true; \
	      ;; \
	    Linux) \
	      if command -v xdg-open >/dev/null 2>&1; then \
	        (xdg-open "$$URL" >/dev/null 2>&1 &) || true; \
	      fi; \
	      ;; \
	    MINGW*|MSYS*|CYGWIN*) \
	      (cmd /c start "" "$$URL" >/dev/null 2>&1 &) || true; \
	      ;; \
	  esac; \
	fi

stop:
	@set -e; \
	  echo "🛑 Stopping dev processes…"; \
	  BACKEND_PORT="$(BACKEND_PORT)"; \
	  BACKEND_CMD_PATTERN="$(BACKEND_CMD_PATTERN)"; \
	  FRONTEND_PORT="$(FRONTEND_PORT)"; \
	  FRONTEND_CMD_PATTERN="$(FRONTEND_CMD_PATTERN)"; \
	  backend_from_file=""; \
	  if [ -f logs/backend.pid ]; then \
	    backend_from_file="$$(tr '\n' ' ' < logs/backend.pid)"; \
	  fi; \
	  backend_from_pattern="$$(pgrep -f "$$BACKEND_CMD_PATTERN" 2>/dev/null | tr '\n' ' ' || true)"; \
	  backend_from_port="$$(lsof -tiTCP:"$$BACKEND_PORT" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' || true)"; \
	  backend_pids="$$(printf "%s\n%s\n%s\n" "$$backend_from_file" "$$backend_from_pattern" "$$backend_from_port" | tr ' ' '\n' | sed '/^$$/d' | sort -u | tr '\n' ' ')"; \
	  if [ -n "$$backend_pids" ]; then \
	    echo "Stopping backend ($$backend_pids)"; \
	    kill $$backend_pids >/dev/null 2>&1 || true; \
	    sleep 0.5; \
	    still_listening="$$(lsof -tiTCP:"$$BACKEND_PORT" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' || true)"; \
	    if [ -n "$$still_listening" ]; then \
	      echo "Backend still listening on $$BACKEND_PORT; sending SIGKILL"; \
	      kill -9 $$still_listening >/dev/null 2>&1 || true; \
	    fi; \
	  else \
	    echo "No backend process found"; \
	  fi; \
	  rm -f logs/backend.pid; \
	  frontend_from_file=""; \
	  if [ -f logs/frontend.pid ]; then \
	    frontend_from_file="$$(tr '\n' ' ' < logs/frontend.pid)"; \
	  fi; \
	  frontend_from_pattern="$$(pgrep -f "$$FRONTEND_CMD_PATTERN" 2>/dev/null | tr '\n' ' ' || true)"; \
	  frontend_from_port="$$(lsof -tiTCP:"$$FRONTEND_PORT" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' || true)"; \
	  frontend_pids="$$(printf "%s\n%s\n%s\n" "$$frontend_from_file" "$$frontend_from_pattern" "$$frontend_from_port" | tr ' ' '\n' | sed '/^$$/d' | sort -u | tr '\n' ' ')"; \
	  if [ -n "$$frontend_pids" ]; then \
	    echo "Stopping frontend ($$frontend_pids)"; \
	    kill $$frontend_pids >/dev/null 2>&1 || true; \
	    sleep 0.5; \
	    still_listening="$$(lsof -tiTCP:"$$FRONTEND_PORT" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' || true)"; \
	    if [ -n "$$still_listening" ]; then \
	      echo "Frontend still listening on $$FRONTEND_PORT; sending SIGKILL"; \
	      kill -9 $$still_listening >/dev/null 2>&1 || true; \
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
	    ruff check . || true; \
	  else \
	    echo "Skipping ruff (not installed)"; \
	  fi
	@PATH="$(VENV_BIN):$$PATH"; \
	  if command -v black >/dev/null 2>&1; then \
	    black --check . || true; \
	  else \
	    echo "Skipping black (not installed)"; \
	  fi
	@PATH="$(VENV_BIN):$$PATH"; \
	  if command -v mypy >/dev/null 2>&1; then \
	    mypy $(MYPY_TARGETS) || true; \
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
