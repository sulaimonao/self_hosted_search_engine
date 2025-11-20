# GitHub Copilot Instructions

_Tailored guidelines for AI coding agents working in this repo._

## Architecture & Data Flow

- **Core layers:**  
	- `server/` + `backend/` host the Flask API, orchestration logic, jobs, and state.  
	- `frontend/` is a Next.js (App Router, Tailwind, shadcn/ui) UI for search, Control Center, and researcher workflows.  
	- `crawler/` (Scrapy) and `engine/` (Whoosh + Chroma/DuckDB) power crawling, normalization, and blended retrieval.  
	- `desktop/` + `electron/` host the Chromium-based research browser shell (Electron), wiring tabs, history, downloads, and settings into the API.  

- **API-only backend:**  
	- `app.py` plus `backend/app/__init__.py` build the Flask app and register all `/api/*` routes.  
	- The root `/` returns a JSON health banner; anything non-API is _not_ a web UI. All UI lives in Next.js or Electron.

- **Capture → normalize → index → query:**  
	- Crawler writes raw pages under `data/crawl/`.  
	- `make normalize` builds `data/normalized/normalized.jsonl`.  
	- Indexers in `engine/` + `backend/` maintain the Whoosh BM25 index (`data/whoosh/`) and vector stores (`data/chroma/`, `data/index.duckdb`).  
	- `/api/search` and `/api/chat` orchestrate blended retrieval across BM25 + vectors, plus page/agent context.

- **Shadow capture & researcher browser loop:**  
	- Browser navigation (web + desktop) can trigger shadow captures via `/api/shadow/snapshot`.  
	- Policies for what to capture are managed via `/api/shadow/policy` and live under `data/agent/documents/shadow/`.  
	- Export of captured datasets is driven by CLI helpers (see `make export-dataset`) and ultimately feeds local RAG/training.

- **State & profiles:**  
	- The repo assumes a single local "profile" per data directory.  
	- Key DBs live in:
		- `data/app_state.sqlite3` (threads/messages/tasks/browser/history/jobs/config).  
		- `data/learned_web.sqlite3` (crawl graph, learned discovery web).  
	- Electron-specific browser state is in `browser_state.sqlite3` under the OS `userData` dir (history, downloads, permissions, preferences).

---

## Browser Project Goal & Mental Model

**Think of this repo as a fully local “researcher browser” plus search stack.** All changes should support this end-state:

- **First-class research browser:**  
	- Electron shell embeds real Chromium `BrowserView` tabs, driven by the React UI (`frontend/`) via `window.browserAPI` and preload bridges under `desktop/` / `electron/`.  
	- Navigation, address bar text, tab titles, favicons, history, and back/forward state all flow through that bridge.

- **Local-first capture + search loop:**  
	- Browsing should feel like a normal browser, but with an optional “shadow mode” that quietly captures pages, normalizes them, embeds them, and feeds the local indexes.  
	- All capture, normalization, and indexing remain on-disk (`data/*`) and under user control; no remote services or hosted APIs should be introduced.

- **Configurable and explainable automation:**  
	- Shadow/autopilot features are _opt-in_, surfaced via the Control Center (`/control-center`) and desktop UI toggles.  
	- Policies (what to crawl, what to store, which domains to include/exclude) are explicit, persisted, and observable (via `/api/shadow/*`, `/api/meta/capabilities`, diagnostics, and logs).

- **Parity between web and desktop shells:**  
	- Web UI (browser build) and desktop UI (Electron) should expose consistent controls for navigation, search, shadow mode, and diagnostics.  
	- Desktop adds richer browser capabilities (downloads tray, history view, site controls, settings sheet), but should still call the same `/api/*` endpoints as the web UI.

When updating or adding code, prefer designs that:

- Strengthen the **research loop** (browse → capture → index → search → refine).  
- Keep behaviour **predictable, opt-in, local, and inspectable**.  
- Use existing browser bridges (`window.desktop.*`, `window.browserAPI`), capabilities maps, and Control Center wiring instead of ad-hoc shortcuts.

---

## How to Run Things (agents should prefer)

- **Full dev stack (backend + frontend):**  
	- Prefer `make dev` from the repo root.  
	- It loads `.env`, starts Flask on `BACKEND_PORT` (default `5050`), waits for `/api/llm/health`, then runs the Next.js dev server on `FRONTEND_PORT` (default `3100`).  
	- Always treat `http://localhost:3100` as the canonical dev origin; `/api/*` calls proxy to the Flask API.

- **Desktop / browser dev:**  
	- Use `npm run dev:desktop` (or `npm run app:dev` where appropriate) from root to boot API + Next.js + Electron shell with shared diagnostics/preflight.  
	- The Electron preload bridges (`window.desktop.*`, `window.browserAPI`) are the only supported way to talk to main-process browser APIs from React. Prefer extending those over injecting new globals.

- **Backend-only tasks:**  
	- Most CLI entrypoints are in `bin/` (e.g., `crawl.py`, `reindex.py`, `search_cli.py`) and `tools/`.  
	- When adding a new script, mirror argument parsing and logging patterns from existing files in `bin/`.  
	- For browser/shadow exports, prefer extending existing helpers (e.g., dataset export, diagnostics) over ad-hoc scripts.

- **Tests:**  
	- Backend tests live in `tests/` (including `tests/e2e/`).  
	- JS/e2e tests live under `frontend/` and `e2e/`.  
	- When adding browser features, extend existing tests that cover navigation, shadow capture, and capabilities maps rather than inventing new directories.

---

## Patterns & Conventions

- **APIs live under `backend/app/api/`:**  
	- Keep route naming consistent (`/api/<area>/<verb>`).  
	- Return JSON (no HTML) and use existing response helpers and error handling patterns from nearby modules.  
	- For browser-specific features (shadow, browser diagnostics, capabilities, history/downloads APIs), prefer extending existing blueprints in the `meta`, `shadow`, `dev/diag`, or browser-related areas.

- **Jobs & long-running work:**  
	- Anything slow should create a row in the `jobs` table via helpers in `backend/app/db/schema.py`.  
	- Surface progress through `/api/jobs` + `/api/jobs/<id>/status`.  
	- Reuse existing job types and patterns (crawl, indexing, diagnostics, exports) before introducing new ones—especially for browser diagnostics, dataset export, and heavy reindexing.

- **Bundle/import flows:**  
	- Import/export logic is centralized in `backend/app/api/bundle.py` plus helpers in the app-state DB.  
	- If you add a new persisted concept that needs export/import (e.g., browser policies, shadow snapshots, seeds, bookmarks), plug it into that pipeline instead of making ad-hoc endpoints.

- **Repo-edit tooling:**  
	- Code that lets agents propose/apply patches to repos lives under `backend/app/api/repo.py` and the `repos` / `repo_changes` tables.  
	- Always enforce path whitelisting and change budgets; do _not_ bypass these helpers from new code.

- **Crawler & seeds:**  
	- Crawler logic is in `crawler/` and `engine/indexing/`.  
	- Seed registry APIs are the source of truth for crawl queue state (see `seeds/` and the `seeds` API used by the frontend).  
	- Avoid writing directly to `seeds/*.yaml` from scripts; go through the existing seed loader APIs.

- **Frontend data access:**  
	- React components should go through shared fetch/helpers that call `/api/*` (see helpers in `frontend/` and usage in pages/components).  
	- Do not hardcode backend URLs; always use `NEXT_PUBLIC_API_BASE_URL` or existing client utilities.  
	- For browser + shadow features, reuse established client hooks/selectors (Control Center, Chat Tools & Context, browser drawers) instead of calling fetch directly in arbitrary components.

---

## Safety & Data Integrity

- **Never touch `data/` directly from new code** (beyond temporary/dev scripts).  
	- Instead, go through existing DB abstractions (`AppStateDB`, learned web helpers, index store classes) so migrations, clean-up, and jobs remain coherent.  
	- Browser artifacts (history, downloads, policies, snapshots) should use the existing tables and file layouts; if you must add new files, follow current directory conventions.

- **Respect single-profile assumption:**  
	- Do not introduce multi-user IDs into DB schemas.  
	- If you need isolation, use separate data directories or profile-like configuration, following existing patterns.

- **Long-running ops:**  
	- Anything that can block for more than a couple of seconds (crawl, indexing, embedding, large exports/imports, repo checks, browser diagnostics, dataset exports) should be queued as a job and surfaced via `/api/jobs` instead of running entirely in request scope.

- **Privacy and locality for the browser:**  
	- Do **not** send page contents, browsing history, or captured documents to external services.  
	- All LLM calls should go through the existing LLM abstraction (Ollama, local models) wired in `llm/` and `backend/app/llm`—never call remote SaaS APIs directly from browser or backend code.  
	- Keep shadow capture explicitly gated by user toggles and policies; do not auto-enable capture for new features.

---

## When Modifying/Adding Code

- **Backend:**  
	- Follow patterns in `backend/app/api/` for blueprints, in `backend/app/db/schema.py` for DB access, and in `engine/` for retrieval/indexing logic.  
	- Prefer extending existing modules over creating parallel "one-off" implementations.  
	- For browser/shadow features:
		- Respect `/api/meta/capabilities` as the single source of truth for what is enabled.  
		- Reuse `shadow`-related handlers and config tables instead of adding new ad-hoc flags.

- **Frontend (web browser + Control Center):**  
	- Keep Next.js pages/components under `frontend/app/` and use the established Tailwind/shadcn design system.  
	- When wiring new panels (e.g., for diagnostics, jobs, or browser drawers like downloads/history/bookmarks), mirror the Control Center and Agent/Job log components.  
	- Use existing layout primitives and design tokens so new browser UI (bars, drawers, sheets) feels consistent.

- **Electron/Desktop (research browser shell):**  
	- Preload and main-process code lives under `desktop/` and `electron/`.  
	- When adding new desktop features (tabs, site controls, downloads, history, settings, shadow toggles), expose them via the existing preload bridges (`window.desktop.*`, `window.browserAPI`) instead of introducing new globals.  
	- Maintain backwards compatibility with the web build: Electron should be an enhanced shell over the same Next.js app, not a separate UI.

- **Diagnostics & observability:**  
	- Browser and backend diagnostics go through `tools/`, `docs/diagnostics.md`, and `/api/dev/diag/*`.  
	- Prefer adding new checks to the existing diagnostics engine and system check flows instead of inventing separate “health” concepts.

---

## Good First References

When Copilot (or any agent) needs more context, prefer these starting points:

- **Overall stack and dev UX:**  
	- `README.md` (root) — canonical description of the research browser, shadow mode, and search stack.

- **Backend architecture & jobs/bundles/repo tools:**  
	- `docs/backend_architecture.md`  
	- `backend/app/api/`, `backend/app/db/schema.py`

- **Search + crawl + index + shadow data flow:**  
	- `docs/backend_phase0_summary.md`  
	- `docs/roadmap_browser.md`  
	- `search/`, `engine/`, `crawler/`, `seed_loader/`

- **Frontend wiring, Control Center, and browser workflows:**  
	- `frontend/README.md`  
	- `docs/logging_frontend.md`  
	- `frontend/app/control-center/*`, `frontend/app/(browser)/` routes (where present)

- **Electron/Desktop browser:**  
	- `frontend/electron/main.js`, `frontend/electron/preload.ts` (or equivalents)  
	- `desktop/` and `electron/` for BrowserView wiring and browser-specific diagnostics.

Use these references to align changes with the long-term goal: a reliable, fully local research browser that turns everyday browsing into a controllable, high-quality dataset for search and LLM-assisted analysis.

