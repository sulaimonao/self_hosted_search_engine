.PHONY: bootstrap dev stop logs verify

FRONTEND_PORT ?= 3100
BACKEND_PORT  ?= 5050
API_URL := http://127.0.0.1:$(BACKEND_PORT)/api/llm/health

bootstrap:
	@bash scripts/bootstrap.sh

dev:
	@echo "▶ Starting API (Flask)…"
	@if ! lsof -iTCP:$(BACKEND_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
	  (cd backend && BACKEND_PORT=$(BACKEND_PORT) ../../.venv/bin/python -m app &) ; \
	fi
	@echo "⏳ Waiting for API…"
	@bash -c 'for i in $$(seq 1 60); do curl -fsS "$(API_URL)" >/dev/null && exit 0; sleep 0.5; done; echo "API not ready" >&2; exit 1'
	@echo "▶ Starting Frontend (Next.js)…"
	@if ! lsof -iTCP:$(FRONTEND_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
	  (cd frontend && npm run dev -- --hostname 0.0.0.0 --port $(FRONTEND_PORT) &) ; \
	fi
	@echo "✅ UI http://127.0.0.1:$(FRONTEND_PORT)  |  API http://127.0.0.1:$(BACKEND_PORT)"

stop:
	@echo "🛑 Stopping dev processes…"
	-@pkill -f "python -m app" || true
	-@pkill -f "next dev" || true

logs:
	@echo "— Flask —"; pgrep -fl "python -m app" || true
	@echo "— Next —";  pgrep -fl "next dev" || true

verify:
	@bash scripts/preflight.sh
