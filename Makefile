
.DEFAULT_GOAL := start

.PHONY: start bootstrap dev stop logs verify first-run preflight setup export-dataset
.PHONY: desktop desktop-build dev-desktop
.PHONY: api web
.PHONY: lint-makefile diag
.PHONY: ollama-pull-self-heal ollama-health index-health index-rebuild

lint-makefile:
	@echo "Ensure all recipe lines use tabs (not spaces)."

.PHONY: ollama-pull-self-heal
ollama-pull-self-heal:
	@echo "Pulling self-heal model: $${SELF_HEAL_MODEL:-llama3.1:8b-instruct}"
	ollama pull $${SELF_HEAL_MODEL:-llama3.1:8b-instruct}

.PHONY: ollama-health
ollama-health:
	@API_ORIGIN="$${API_ORIGIN:-http://127.0.0.1:$(BACKEND_PORT)}"; \
	API_ORIGIN="$${API_ORIGIN%/}"; \
	RESPONSE=$$(curl -sS "$${API_ORIGIN}/api/admin/ollama/health"); \
	if command -v jq >/dev/null 2>&1; then \
	printf '%s\n' "$$RESPONSE" | jq .; \
	else \
	printf '%s\n' "$$RESPONSE"; \
	fi

index-health:
	@API_ORIGIN="$${API_ORIGIN:-http://127.0.0.1:$(BACKEND_PORT)}"; \
	API_ORIGIN="$${API_ORIGIN%/}"; \
	RESPONSE=$$(curl -sS "$$API_ORIGIN/api/index/health"); \
	if command -v jq >/dev/null 2>&1; then \
	printf '%s\n' "$$RESPONSE" | jq .; \
	else \
	printf '%s\n' "$$RESPONSE"; \
	fi

index-rebuild:
	@API_ORIGIN="$${API_ORIGIN:-http://127.0.0.1:$(BACKEND_PORT)}"; \
	API_ORIGIN="$${API_ORIGIN%/}"; \
	RESPONSE=$$(curl -sS -X POST "$$API_ORIGIN/api/index/rebuild" -H 'Content-Type: application/json' -d '{}'); \
	if command -v jq >/dev/null 2>&1; then \
	printf '%s\n' "$$RESPONSE" | jq .; \
	else \
	printf '%s\n' "$$RESPONSE"; \
	fi

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

start:
	@echo "💡 Tip: Press Ctrl+C to quit safely. Cleanup will run automatically."
	@trap '$(MAKE) stop || true' EXIT INT TERM; \
		$(MAKE) dev

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
	@if [ "$(SKIP_SYSTEM_CHECK)" != "1" ]; then \
		echo "▶ Running backend system check…"; \
		mkdir -p diagnostics; \
		response=$$(curl -fsS -X POST "http://127.0.0.1:$(BACKEND_PORT)/api/system_check" -H 'Content-Type: application/json' -d '{}'); \
		status="$$?"; \
		echo "$$response" > diagnostics/system_check_last.json; \
		if [ "$$status" -ne 0 ]; then \
			echo "⚠️  System check request failed (curl exit $$status)"; \
		else \
			critical=$$(printf '%s' "$$response" | python3 scripts/system_check_has_critical.py); \
			if [ "$$critical" = "true" ]; then \
				echo "❌ Critical system check failures detected"; \
				exit 1; \
			fi; \
		fi; \
	else \
		echo "⏭️  System check skipped (SKIP_SYSTEM_CHECK=1)"; \
	fi
	@echo "▶ Starting Frontend (Next.js)…"
	@if ! lsof -iTCP:$(FRONTEND_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
		mkdir -p logs; \
		(cd frontend && \
			if [ -z "$$NEXT_PUBLIC_API_BASE_URL" ]; then \
				export NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:$(BACKEND_PORT); \
			fi; \
			nohup npm run dev -- --hostname localhost --port $(FRONTEND_PORT) > ../logs/frontend.log 2>&1 & echo $$! > ../logs/frontend.pid \
		); \
	fi
	@API_ORIGIN="$${NEXT_PUBLIC_API_BASE_URL}"; \
	if [ -z "$$API_ORIGIN" ]; then \
		API_ORIGIN="http://127.0.0.1:$(BACKEND_PORT)"; \
	fi; \
	API_ORIGIN="$$(printf "%s" "$$API_ORIGIN" | sed 's:/*$$::')"; \
	echo "🚀 Frontend ready at http://localhost:$(FRONTEND_PORT)"; \
	echo "ℹ️  API $$API_ORIGIN"
	@if [ "$(AUTO_OPEN_BROWSER)" = "1" ]; then \
		URL="http://localhost:$(FRONTEND_PORT)"; \
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
	@echo "🛑 Stopping dev processes…"
	@BACKEND_PORT="$(BACKEND_PORT)" \
		FRONTEND_PORT="$(FRONTEND_PORT)" \
		BACKEND_CMD_PATTERN="$(BACKEND_CMD_PATTERN)" \
		FRONTEND_CMD_PATTERN="$(FRONTEND_CMD_PATTERN)" \
		bash scripts/stop_all.sh

api:
	@echo "▶ Starting API (Flask)…"
	@if [ -x "$(VENV_PY)" ]; then \
	  BACKEND_PORT="$(BACKEND_PORT)" PYTHONPATH="$(CURDIR)" "$(VENV_PY)" -m backend.app; \
	else \
	  echo "⚠️  Using system python (virtualenv missing)"; \
	  BACKEND_PORT="$(BACKEND_PORT)" PYTHONPATH="$(CURDIR)" python3 -m backend.app; \
	fi

web:
		@echo "▶ Starting Frontend (Next.js)…"
	@NEXT_PUBLIC_API_BASE_URL="$$NEXT_PUBLIC_API_BASE_URL"; \
	if [ -z "$$NEXT_PUBLIC_API_BASE_URL" ]; then \
	  NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:$(BACKEND_PORT)"; \
	fi; \
	NEXT_PUBLIC_API_BASE_URL="$$NEXT_PUBLIC_API_BASE_URL" \
		npm --prefix frontend run dev -- --hostname localhost --port $(FRONTEND_PORT)

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

desktop-dev:
	( cd frontend && pnpm dev ) & \
	BACKEND_DEV=1 FRONTEND_URL=http://127.0.0.1:3100 pnpm --dir desktop/electron dev

desktop-pack:
	python3.11 scripts/pack_backend.py
	cd frontend && pnpm build && pnpm export -o export
	pnpm --dir desktop/electron build

desktop:
	cd desktop && npm install && npm run start

dev-desktop:
	cd desktop && npm install && npm run dev

desktop-build:
	# 1) Build Next.js to static export
	cd frontend && npm install && npm run build && npm run export
	# 2) Stage exports into Electron resources
	mkdir -p desktop/resources/frontend
	rsync -a --delete frontend/out/ desktop/resources/frontend/
	# 3) Build Electron
	cd desktop && npm install && npm run build

export-dataset: setup
	@if [ -z "$(OUT)" ]; then \
	  echo "Usage: make export-dataset OUT=/tmp/data.jsonl [ARGS='--domain example.com']"; \
	  exit 1; \
	fi
	@$(VENV_PY) scripts/export_dataset.py --out "$(OUT)" $(ARGS)
diag:
	python3 tools/e2e_diag.py --fail-on=high
