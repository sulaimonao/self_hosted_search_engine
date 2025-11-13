# Repository Summary & Debug Guide

This document condenses the architecture, recent changes (Knowledge Graph feature), how to run and reproduce, and a focused debugging checklist to help quickly investigate issues.

**Last updated:** 2025-11-13

---

## Project Overview

- Languages & frameworks:
  - Backend: Python (Flask) — code under `backend/`.
  - Frontend: TypeScript + React (Next.js) — code under `frontend/`.
  - Desktop: Electron shell in `desktop/` / `electron/`.
  - Tests: pytest (unit) in `tests/`, Playwright e2e in `e2e/`.

- Key responsibilities:
  - `backend/app/__init__.py` - Flask application factory and blueprint registration.
  - `backend/app/db/store.py` - Application state DB helpers (SQLite) and graph SQL.
  - `backend/app/db/schema.py` - DB schema migrations.
  - `backend/app/api/browser.py` - Browser-related HTTP endpoints (graph endpoints live here).
  - `frontend/src/components/KnowledgeGraphPanel.tsx` - Graph UI filters and data mapping.
  - `frontend/src/components/GraphCanvas.tsx` - Force-graph renderer (client-only dynamic import).

---

## Recent changes (Knowledge Graph)

- Frontend
  - `frontend/src/components/KnowledgeGraphPanel.tsx`:
    - Adds a `View` selector (`Pages` vs `Sites (overview)`).
    - Pages view: calls `/api/browser/graph/nodes` and `/api/browser/graph/edges` with filters: `site`, `min_degree`, `category`, `from`, `to`, `indexed`, `limit`.
    - Sites view: calls `/api/browser/graph/sites` and `/api/browser/graph/site_edges` and maps aggregated site nodes into the canvas (node size via `val`, edge `relation` used as weight label).
    - Adds `min_weight` control for Sites view.
    - Adds a legend and list panel.
  - `frontend/src/components/GraphCanvas.tsx`:
    - Accepts optional `val?: number` for node sizing.
    - Adds `linkCanvasObject` to render edge labels (e.g., weights).
    - Colors indexed nodes green; others gray.

- Backend
  - `backend/app/db/store.py`:
    - `graph_nodes(...)` includes `(embedding IS NOT NULL) AS indexed`.
    - Added `graph_site_nodes(...)` for aggregated site-level metrics (pages, degree, fresh_7d, last_seen).
    - Added `graph_site_edges(...)` for aggregated cross-site link weights.
    - `graph_edges(...)` extended to support `start`, `end`, and `category` filters by joining `link_edges` with `pages`.
  - `backend/app/api/browser.py`:
    - New endpoints: `GET /api/browser/graph/sites` and `GET /api/browser/graph/site_edges`.
    - `GET /api/browser/graph/edges` now forwards date/category filters.

- Tests
  - `tests/backend/test_app_state_browser.py` — extended to include `test_graph_site_overview_and_edges_filters`.
  - `tests/api/test_graph_api.py` — API-level tests that monkeypatch `_state_db` and validate graph endpoints.
  - `e2e/graph.spec.ts` — Playwright skeleton to verify `/graph` loads and toggles views.

---

## How to run locally (quick)

- Backend (inside the project root):

```zsh
source .venv/bin/activate
VENV_PY="$(python -c 'import sys; print(sys.executable)')" BACKEND_PORT=5050 ./scripts/dev_backend.sh
# Check health
curl -fsS http://127.0.0.1:5050/api/llm/health | jq .
```

- Frontend (Next.js):

```zsh
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:5050 npm --prefix frontend run dev -- --hostname=localhost --port=3100
open http://localhost:3100/graph
```

- Unit tests (pytest):

```zsh
pytest -q tests/backend/test_app_state_browser.py::test_graph_site_overview_and_edges_filters
pytest -q tests/api/test_graph_api.py
```

- E2E (Playwright) — install deps first:

```zsh
npm --prefix e2e i
make deps-playwright
# ensure backend + frontend running
npx --yes playwright test -c e2e
```

---

## Debugging checklist (targeted for graph-related issues)

1) Graph page fails to compile / 500 error referencing `react-force-graph-2d`:
   - Symptom: Next.js build error "Module not found: Can't resolve 'react-force-graph-2d'" or runtime 500 on `/graph`.
   - Fix: run `npm --prefix frontend i react-force-graph-2d` and restart frontend.
   - Ensure `GraphCanvas` is dynamically imported with `ssr: false`.

2) Graph renders but shows no nodes/edges:
   - Run API smoke checks:
     - `curl -sS http://127.0.0.1:5050/api/browser/graph/summary | jq .`
     - `curl -sS "http://127.0.0.1:5050/api/browser/graph/nodes?limit=10" | jq .`
     - `curl -sS "http://127.0.0.1:5050/api/browser/graph/edges?limit=10" | jq .`
   - Inspect DB (`data/app_state.sqlite3` or configured path in `config.yaml`):
     - `sqlite3 data/app_state.sqlite3 'SELECT COUNT(*) FROM pages; SELECT COUNT(*) FROM link_edges;'
`.

3) `indexed` flag doesn't match external vector index:
   - Current implementation: `indexed` is based on `pages.embedding IS NOT NULL`.
   - If your vector store is external, consider syncing a boolean column in `pages` after successful upsert.

4) Site overview weights incorrect:
   - SQL used in `graph_site_edges` groups by `ps.site, pd.site` counting cross-site link rows. Validate `link_edges` content and `pages.site` assignments.
   - Quick SQL verification (sqlite):

```sql
SELECT ps.site AS src_site, pd.site AS dst_site, COUNT(*) AS weight
FROM link_edges e
JOIN pages ps ON ps.url = e.src_url
JOIN pages pd ON pd.url = e.dst_url
WHERE ps.site IS NOT NULL AND pd.site IS NOT NULL AND ps.site != pd.site
GROUP BY ps.site, pd.site
ORDER BY weight DESC
LIMIT 20;
```

5) Date/category filters not applying properly:
   - Confirm `graph_edges` SQL in `backend/app/db/store.py` includes the appropriate WHERE clauses when `start`, `end`, and `category` are provided.
   - Add a temporary log (or run SQL directly in sqlite) to inspect generated params.

6) Frontend TypeScript/ESLint issues:
   - Ensure `GraphNode` includes `val?: number` to avoid `@ts-expect-error` use.
   - Ambient module typing for `react-force-graph-2d` is avoided by a dynamic import and typed cast in `GraphCanvas`.

7) Electron desktop oddities (ERR_ABORTED or navigation failures):
   - Check timing: ensure frontend server is available before BrowserView loads. This is usually a race during dev startup.

---

## Useful commands & smoke tests

- Summary: `curl -sS http://127.0.0.1:5050/api/browser/graph/summary | jq .`
- Page nodes (indexed):
  `curl -sS "http://127.0.0.1:5050/api/browser/graph/nodes?limit=10&indexed=1" | jq .`
- Page edges with filters:
  `curl -sS "http://127.0.0.1:5050/api/browser/graph/edges?limit=50&category=ai&from=2025-01-01T00:00:00Z&to=2025-12-31T23:59:59Z" | jq .`
- Site overview:
  `curl -sS "http://127.0.0.1:5050/api/browser/graph/sites?limit=50" | jq .`
  `curl -sS "http://127.0.0.1:5050/api/browser/graph/site_edges?limit=100&min_weight=2" | jq .`

---

## Files to inspect first when debugging

- `backend/app/db/store.py` (graph SQL)
- `backend/app/api/browser.py` (graph endpoints)
- `frontend/src/components/KnowledgeGraphPanel.tsx` (filters & mapping)
- `frontend/src/components/GraphCanvas.tsx` (rendering, labels)
- `data/app_state.sqlite3` (or configured DB path)
- `logs/backend.log` and `logs/frontend.log` for runtime errors

---

## Next recommended actions

1. Add a tooltip on site nodes showing `(pages, degree, fresh_7d, last_seen)`.
2. Sync `indexed` boolean with vector-index upserts instead of relying solely on `pages.embedding` (if vector store is external).
3. Add unit tests asserting SQL WHERE clauses for `graph_edges` to prevent regressions.
4. Expand e2e to seed known test dataset and assert node counts + navigation.

---

If you'd like, I can:
- Add the tooltip and UI polish now (frontend changes).
- Add a tiny backend logger that prints generated SQL and params for `graph_edges` and run a reproduction to capture any filter mismatch.
- Convert this summary into a different format (PDF or HTML) and commit it.

File created: `docs/REPO_SUMMARY.md`

