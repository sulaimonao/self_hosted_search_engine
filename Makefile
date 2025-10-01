.PHONY: bootstrap dev stop logs verify

FRONTEND_PORT ?= 3100
BACKEND_PORT  ?= 5050
API_URL := http://127.0.0.1:$(BACKEND_PORT)/api/llm/health
VENV_PY := $(CURDIR)/.venv/bin/python

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
        @if [ -f logs/backend.pid ]; then \
          PID=$$(cat logs/backend.pid); \
          if kill -0 $$PID >/dev/null 2>&1; then kill $$PID >/dev/null 2>&1 && echo "Stopped backend ($$PID)" || true; fi; \
          rm -f logs/backend.pid; \
        fi
        @if [ -f logs/frontend.pid ]; then \
          PID=$$(cat logs/frontend.pid); \
          if kill -0 $$PID >/dev/null 2>&1; then kill $$PID >/dev/null 2>&1 && echo "Stopped frontend ($$PID)" || true; fi; \
          rm -f logs/frontend.pid; \
        fi

logs:
	@echo "— Flask —"; pgrep -fl "python -m app" || true
	@echo "— Next —";  pgrep -fl "next dev" || true

verify:
	@bash scripts/preflight.sh
