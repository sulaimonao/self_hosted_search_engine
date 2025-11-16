# Phase 0: Backend + Data Flow Summary

## Backend framework & entrypoints
- `app.py` bootstraps the long-running Flask API by wiring Ollama clients, vector store, crawler, chunker, embedder, cold-start indexer, and tool dispatcher before calling `backend.app.create_app()`; the resulting app config exposes these components to blueprints and background workers. [【F:app.py†L1-L220】]
- `backend/app/__init__.py` provides the Flask factory: it enables tracing/CORS, registers every blueprint under `/api/*`, initializes shared services (search, indexing, agent runtime, progress buses, incident log, job runner), and enforces the "API-only" root route guard. [【F:backend/app/__init__.py†L1-L200】]

## Current data flow (capture → normalize → index → query → LLM)
1. **Capture & discovery**
   - The focused crawler (`engine/indexing/crawl.py`) plus the discovery engine feed `ColdStartIndexer`, which optionally seeds URLs via LLM suggestions before fetching pages. [【F:engine/indexing/coldstart.py†L1-L111】]
   - Raw crawler outputs land under `data/crawl/`, while the frontier/agent artefacts sit under `data/agent/`. [【F:README.md†L453-L466】]
2. **Normalize**
   - `make normalize` converts crawl output into `data/normalized/normalized.jsonl`, standardizing documents for downstream indexing. [【F:README.md†L438-L466】]
3. **Index**
   - `ColdStartIndexer` chunks fetched text, obtains Ollama embeddings, and upserts into the Chroma-backed `VectorStore`, which maintains persistent collections at `data/chroma/` + `data/index.duckdb`. [【F:engine/indexing/coldstart.py†L70-L119】【F:engine/data/store.py†L1-L83】]
4. **Query & retrieval**
   - The Whoosh BM25 index (`data/whoosh/`) and vector store power blended search; APIs like `/api/search`, `/api/chat`, and `/api/reasoning` orchestrate BM25 + vector retrieval and optional planner/agent runs. [【F:README.md†L458-L480】【F:app.py†L76-L178】]
5. **LLM orchestration**
   - `RagAgent`, `PlannerAgent`, and `OllamaJSONClient` drive chat, autopilot, and diagnostics. The chat blueprint handles schema validation, SSE streaming, and tool invocation before persisting responses. [【F:app.py†L14-L118】【F:backend/app/api/chat.py†L1-L120】]

## Persistence layers already in use
- **App state DB** – SQLite at `data/app_state.sqlite3` managed by `backend/app/db/schema.py`. Core tables include `documents`, `page_visits`, `chat_threads`, `chat_messages`, `chat_summaries`, `memories`, browser `tabs/history/bookmarks`, and graph structures (`pages`, `link_edges`). [【F:backend/app/db/schema.py†L200-L444】]
- **Learned web DB** – separate SQLite (`data/learned_web.sqlite3`) storing domains, crawl runs, pages, links, embeddings, and discovery events to fuel the knowledge graph + discovery heuristics. [【F:server/learned_web_db.py†L14-L132】]
- **Vector/keyword indices** – Chroma/DuckDB combo under `data/chroma/` + `data/index.duckdb`, plus Whoosh in `data/whoosh/`. [【F:engine/data/store.py†L1-L83】【F:README.md†L458-L466】]
- **Agent frontier state** – `data/agent/frontier.sqlite3` and related artefacts hold queued tasks and crawl metadata for planner/autopilot flows. [【F:README.md†L458-L466】]

## Browser state persistence
- Electron’s preload initializes `browser_state.sqlite3` in the OS-specific `userData` directory; the `BrowserDataStore` class handles history, downloads, and permission metadata with automatic retention policies. [【F:electron/browser-data.js†L250-L303】]
- Desktop mode documentation confirms that history, downloads, permissions, and per-origin settings persist via that DB while cookies live inside the `persist:main` Chromium session. [【F:README.md†L208-L236】]

## Agent / LLM state storage
- The app-state SQLite schema already includes first-class chat + memory tables: `chat_threads` (thread metadata), `chat_messages` (role/content, foreign-keyed to threads), `chat_summaries`, and `memories` plus the `memory_audit` ledger. These persist LLM conversations, summarizations, and distilled facts accessible to agents. [【F:backend/app/db/schema.py†L230-L275】]
- Planner/crawl metadata is recorded via `crawl_jobs`, `crawl_events`, and `documents`, enabling agents and the UI to track runs, queue states, and stored content. [【F:backend/app/db/schema.py†L168-L227】]

## Where browser ↔ chat currently meet
- Browser visit telemetry lands in `page_visits` and `history`, keyed by `tab_id`, giving us the hooks to associate tabs with chat threads or agent actions later. [【F:backend/app/db/schema.py†L220-L366】]

This document satisfies Phase 0 by cataloging the existing stateful components before introducing new migrations or APIs.
