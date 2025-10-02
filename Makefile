
.PHONY: bootstrap dev stop logs verify

FRONTEND_PORT ?= 3100
BACKEND_PORT  ?= 5050
API_URL := http://127.0.0.1:$(BACKEND_PORT)/api/llm/health
VENV_PY := $(CURDIR)/.venv/bin/python

# Expected command identifiers for dev processes; keep aligned with dev target.
# Bracket trick avoids matching the managing shell that embeds these patterns.
BACKEND_CMD_PATTERN := [p]ython -m backend.app
FRONTEND_CMD_PATTERN := [n]ext dev

bootstrap:
	@bash scripts/bootstrap.sh

dev:
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

verify:
	@bash scripts/preflight.sh
