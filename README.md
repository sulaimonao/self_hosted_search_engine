# Self-Hosted Search Engine

A fully local crawling, indexing, and research stack powered by Scrapy, Whoosh,
Chroma, and Flask. Point the crawler at any site, rebuild the index, and search
from the CLI or the Next.js web UI—no hosted services or third-party APIs
required.

**Quick facts**
- Backend is API-only; all UI is delivered by the Next.js app at
  [http://localhost:3100](http://localhost:3100).
- The backend root `/` responds with `{"ok":true,"service":"backend-api","ui":"frontend-only"}`;
  every other non-`/api/*` path returns a JSON 404.

## Table of contents

- [Stack overview](#stack-overview)
- [Requirements](#requirements)
- [Initial setup](#initial-setup)
- [Running the application](#running-the-application)
- [Researcher browser & shadow mode](#researcher-browser--shadow-mode)
- [Desktop browser mode](#desktop-browser-mode)
- [Command quick reference](#command-quick-reference)
- [Data & storage layout](#data--storage-layout)
- [Testing & quality gates](#testing--quality-gates)
- [Observability & debugging](#observability--debugging)
- [API surface](#api-surface)
- [Discovery & enrichment flows](#discovery--enrichment-flows)
- [LLM integration](#llm-integration)
- [Chat + Page Context + Tools](#chat--page-context--tools)
- [Diagnostics snapshot API](#diagnostics-snapshot-api)

## Stack overview

```
frontend/        Next.js copilot UI (App Router, Tailwind 4, shadcn/ui)
server/          Flask API surface and orchestration logic
backend/         Index builders, retrieval, and CLI utilities
crawler/         Focused crawler (Scrapy) + URL frontier
engine/          Search pipelines (Whoosh BM25 + vector reranker)
llm/             Ollama helpers for discovery, planning, and embeddings
scripts/         Local tooling (change budget guard, telemetry tail, etc.)
seeds/           Curated discovery registry (`docs/registry_structure.md`)
```

Supporting assets live under `data/` at runtime. The directory is safe to delete
while the services are stopped; the next boot will recreate it as needed.

## Requirements

- Python **3.11.x** (pinned via `.python-version` to 3.11.12)
- macOS or Linux capable of running Playwright's Chromium build
- Node.js **18+** (Node 20+ recommended) for the frontend dev server
- npm (bundled with Node.js)
- Optional: [Ollama](https://ollama.com/) for LLM-assisted discovery and chat

Verify the interpreter that will back your virtual environment before running
`make setup`:

```bash
./scripts/ensure_py311.sh python3
```

## Initial setup

1. **Clone** the repository and `cd` into it.
2. **Create a virtual environment** and install the Python packages plus the
   editable package:

   ```bash
   make setup
   ```

   The target installs backend dependencies, Playwright Chromium, and runs a
   quick import check.
3. **Install frontend dependencies** (done automatically by `make dev`, but you
   can pre-install):

   ```bash
   cd frontend
   npm install
   cd ..
   ```
4. **Configure environment overrides (optional)** by copying `.env.example`
   (backend) and/or `frontend/.env.example`:

   ```bash
   cp .env.example .env
   cp frontend/.env.example frontend/.env
   ```

   The root file exposes common knobs such as Flask host/port, Ollama endpoint
   (`OLLAMA_HOST=http://127.0.0.1:11434`), telemetry locations, agent limits,
   and crawler paths. Any values left unset fall back to sensible defaults in
   the Make targets. The frontend example exposes `NEXT_PUBLIC_API_BASE[_URL]`
   if you ever need to point the UI at a remote API during development.

5. **Inspect repository paths** at any time with:

   ```bash
   make paths
   ```

## Running the application

### One-command development stack

The recommended workflow launches both the Flask API and the Next.js frontend in
one terminal:

```bash
make dev
```

`make dev` performs the following:

- Loads `.env` (if present) to populate environment variables.
- Exports crawl/index directories so both processes share the same data roots.
- Starts the Flask API only (binds to `0.0.0.0` and is reachable at
  `http://localhost:5050` from the host; override with
  `BACKEND_PORT`). Auto-reload stays off so a `git pull` or file sync won't
  restart your dev server; opt back in with `BACKEND_RELOAD=1 make dev`.
- Waits for `/api/llm/health` to report ready before booting the frontend. The
  command aborts if the API never becomes healthy, preventing the UI from
  spamming `ECONNREFUSED` during startup.
- Installs frontend dependencies on demand (skips work when `node_modules`
  already exists) and starts the Next.js dev server (binds to `localhost` and is
  reachable at `http://localhost:3100`; override with `FRONTEND_PORT`). Always
  open the UI at `http://localhost:3100` to avoid Next.js dev cross-origin
  warnings; all `/api/*` calls proxy to the Flask API at the URL derived from
  `NEXT_PUBLIC_API_BASE_URL` (defaults to
  `http://127.0.0.1:${BACKEND_PORT}` with a fallback of `5050`). Thanks to the
  dev origin allowlist, `http://127.0.0.1:3100` remains available if you prefer
  that loopback host.
  Opt in with `AUTO_OPEN_BROWSER=1 make dev` to launch that URL automatically
  once the frontend listener is ready (macOS uses `open`, Linux uses
  `xdg-open`, and Windows shells delegate to `cmd /c start`; failures are
  ignored so headless environments stay quiet).
- Streams frontend dev instrumentation (via `/api/dev/log`) into the backend
  terminal so you can observe chat/search actions alongside Flask logs.
- Tears both processes down when either exits or you press
  <kbd>Ctrl</kbd> + <kbd>C</kbd>.

If Ollama is running but no chat-capable models are installed, the UI
automatically calls `/api/llm/autopull` to download `gemma3` (falling back to
`gpt-oss`). Expect the first run of `make dev` to spend a few minutes fetching
model weights.

Run `make stop` (or `npm run stop` from the project root) to terminate lingering
dev servers from another terminal without hunting for process IDs. For an
entirely clean cycle, pair it with the default port before relaunching:

```bash
make stop || true
BACKEND_PORT=5050 make dev
```

### Desktop development

- Run `npm run dev:desktop` to launch the Flask API on `tcp://127.0.0.1:5050`, auto-detect an open renderer port (preferring `http://127.0.0.1:3100`), and open an Electron window pointed at the freshly spawned Next.js dev server. `detect-port` prevents collisions with stale runs, and `kill-port` guarantees the prior renderer is cleaned up before boot.
- Each service runs in the foreground via `concurrently -k --success=first`, so any failing process tears the others down cleanly. Use <kbd>Ctrl</kbd> + <kbd>C</kbd> once to exit; the Playwright harness now shuts down without hanging on `SIGINT`.
- The Electron process reads `process.env.RENDERER_URL`; the dev script exports the detected origin (for example `http://127.0.0.1:3100`) and falls back to the built `index.html` during packaging. Update `frontend/electron/main.js` if you move the renderer bundle.
- Before Electron boots, `scripts/desktop_preflight.ts` first hits the renderer’s `/api/__meta` endpoint to verify it is the freshly started dev server (boot identifier + PID) and then polls `/api/meta/health` and `/api/meta/capabilities`. When hybrid search or chat models are missing it POSTs to `/api/admin/install_models` (defaults to `embeddinggemma` + `gemma:2b`; override with `DESKTOP_EMBED_MODELS` and `DESKTOP_CHAT_MODELS`) and waits for the capability map to report ready. Production launches (`npm run desktop`) reuse the same preflight so the window never opens against a half-configured backend. Tune retry behaviour with `DESKTOP_PREFLIGHT_ATTEMPTS`, `DESKTOP_PREFLIGHT_INTERVAL`, and companions documented inline.
- The API now exposes `GET /health` (200) and enables CORS for both `http://localhost:3100` and `http://127.0.0.1:3100` with `supports_credentials=true`, matching what the Electron shell uses in development.

## Desktop browser mode

The Electron shell now embeds a real Chromium `BrowserView` for every open tab. Navigation, address bar text, tab titles, favicons, and back/forward button state all mirror the active `BrowserView` via IPC—no more cross-origin iframe hacks. Cookies persist across restarts through the dedicated `persist:main` session, and outbound requests spoof a stable Chrome 129 user agent with hardened `navigator` properties to avoid Google/Cloudflare CAPTCHA loops.

Key behaviour:

- Every tab runs inside its own sandboxed `BrowserView`; the renderer simply listens for navigation updates and renders controls.
- The address bar, tab strip, and keyboard shortcuts drive navigation through the preload bridge (`window.browserAPI`), delegating to Electron’s `webContents` APIs.
- Back/forward buttons enable only when the active `BrowserView` can move, and favicons/titles refresh as soon as the page reports them.
- Window resize events relay the updated viewport bounds back to the main process so the active `BrowserView` always fills the content area underneath the React chrome.
- Any navigation failure surfaces an inline retry prompt that triggers a `webContents.reload({ ignoreCache: true })` from the renderer.

Additional desktop capabilities:

- **Persistent browsing data.** History, visits, download metadata, per-origin permission decisions, and browser preferences live in `browser_state.sqlite3` under Electron’s `userData` directory (for example `~/Library/Application Support/Personal Search Engine/` on macOS). Cookies and storage survive restarts because the browser session runs inside the `persist:main` partition and is never cleared on boot.
- **Site controls.** The lock icon next to the address bar opens a site info popover where you can review or reset stored permissions and clear site data. Permission prompts now appear inline with an “Allow/Block” dialog and remember decisions by default.
- **Downloads tray.** Click the download icon in the toolbar (or choose *Downloads* from the menu) to open a tray showing progress, status, and a *Show in folder* action for each file.
- **History view.** The desktop menu links to `/history`, a simple list of recent navigations with one-click open buttons that retarget the active tab.
- **Settings sheet.** A lightweight settings panel controls third-party cookies, address bar search behaviour, spellcheck language, and proxy mode (system/manual with host/port overrides).

To exercise the full desktop experience during development:

```bash
npm run dev:desktop
```

The command boots the API, Next.js renderer, and Electron shell with live reload. The Electron session reuses cookies between runs (`persist:main`), so CAPTCHA challenges solved once stay solved.
- Change the API launch command or port by editing `dev:api` inside `frontend/package.json`; the desktop script will automatically wait for whatever listener you configure (defaults to `5050`).

### Run as Desktop App

Electron support lets you work in a native window without opening Safari/Chrome.

```bash
npm install
npm run build:web  # build the Next.js app once; required for `npm run desktop`
npm run desktop
```

> [!NOTE]
> The desktop orchestrator now checks for `frontend/.next/BUILD_ID` before
> launching. Run `npm --prefix frontend run build:web` first, or set
> `DESKTOP_SKIP_BUILD_CHECK=1` if you need to bypass the guard temporarily.

The `desktop` script boots the Flask API on port `5050`, the Next.js renderer on
port `3100`, waits for the UI to become reachable, and then launches Electron.
Press <kbd>Ctrl</kbd> + <kbd>C</kbd> to shut everything down.

### System check & diagnostics

- After the API reports healthy, `make dev` posts to `/api/system_check`. The
  command aborts only when the response marks `summary.critical_failures` as
  `true`; otherwise, the Next.js dev server starts normally and the results are
  cached to `diagnostics/system_check_last.json`.
- Skip the entire preflight with `SKIP_SYSTEM_CHECK=1 make dev`. Adjust the
  browser harness timeout by exporting `DIAG_TIMEOUT` (milliseconds) before
  running `npm run desktop`, `npm run diagnose:browser`, or the Make target.
- The backend endpoint merges filesystem checks, the diagnostics snapshot job,
  and `/api/llm/health`. When successful it also enqueues a lightweight warmup
  job so the agent model metadata is ready for the first chat.
- Browser diagnostics run through Electron and persist the latest report at
  `diagnostics/browser_diagnostics.json`. Invoke them manually with
  `npm run diagnose:browser` (full) or `npm run diagnose:browser:fast` (10s
  timeout).
- The UI exposes a **System Check** panel that auto-opens when
  `NEXT_PUBLIC_SYSTEM_CHECK_ON_BOOT=1`. Access it later from the desktop menu
  (Help → Run System Check…) or visit `http://localhost:3100/system-check` in
  the browser build. Critical failures block the “Continue” button; warnings
  allow you to proceed.

Build a distributable macOS app bundle with:

```bash
npm run build:desktop
```

Electron Builder drops the packaged app under `dist/`. The build stage runs the
Next.js production build first, then reuses those assets when assembling the
binary. Override `FRONTEND_URL` or `BACKEND_PORT` while running the desktop
script if you need alternative endpoints.

## SQLite migrations

- The backend tracks schema changes in a ledger table named `_migrations`. Each
  migration records its ID and timestamp so the runner can safely re-enter and
  no-op once a change has been applied.
- SQLite only allows constant defaults when adding columns. New columns are
  created with literal defaults such as `0` or left `NULL`, then populated with a
  follow-up `UPDATE` to handle dynamic timestamps or derived data.
- Migrations run automatically when the backend opens the application state DB.
  Logs show `Running state DB migrations` and `State DB migrations finished`—if
  a failure occurs, check backend logs for the migration ID and inspect the
  `_migrations` table for partial progress.
- Stuck locally? Stop the backend, delete the state database (defaults to
  `data/app_state.sqlite3`), and restart. This clears local app state, so only
  do it if you are fine losing cached jobs/history.

Open the browser at `http://localhost:3100` (not `127.0.0.1`) to use the UI and
avoid dev-only cross-origin warnings. Make sure `ollama` is listening on
`http://127.0.0.1:11434` (or adjust `OLLAMA_HOST`). If
`localhost:5050` is busy (macOS ships AirPlay on that port), run
`BACKEND_PORT=5051 make dev` instead; the proxy will automatically follow the
updated port. When something else is already bound to the configured
`BACKEND_PORT`, `make dev` now reuses that listener and proceeds directly to the
health check—it only fails when the existing process never reports healthy. The
Flask API root now returns a JSON ping to confirm the service is API-only and
that the UI lives entirely in Next.js.

Verify the stack after startup with:

```bash
./scripts/dev_verify.sh
```

The helper checks the API directly, confirms the Next.js HTML shell, and ensures
the `/api/*` rewrite succeeds.

### Backend or frontend individually

Run just the Flask backend (using the existing `.venv`) without auto reload:

```bash
make run
```

Need live reload? Prefix the command with `BACKEND_RELOAD=1` to restore the
watchdog behaviour:

```bash
BACKEND_RELOAD=1 make run
```

### Desktop app (Electron + Next.js)

Shadow mode can now run inside a chromium shell without relying on Safari or Chrome.
Start the API in one terminal, then launch the desktop wrapper from another:

```bash
make run  # or: BACKEND_PORT=5050 make run

cd frontend
npm run app:dev
```

The command waits for the Next.js dev server and opens an Electron window that
proxies `http://localhost:3100`. Navigation events trigger shadow crawls when
the in-app toggle is enabled, and progress updates are surfaced via the HUD on
the desktop chrome. The renderer still proxies all `/api/*` calls to the Flask
backend, so keep the API running in the background.

### Build desktop installers

To generate production-ready installers for macOS, Windows, and Linux, run:

```bash
cd frontend
npm run build:desktop
```

The script performs a static export (`next export`) and then packages the
Electron app with `electron-builder`. Artifacts are written to `frontend/dist/`
and include DMG (macOS), NSIS (Windows), and AppImage/deb (Linux) targets.

### Crawling, indexing, and searching

Once the stack is running you can drive the full crawl → normalize → index →
search pipeline entirely from the CLI:

```bash
make crawl URL="https://example.com/"   # polite crawl with dedupe metadata
make normalize                           # normalize newly crawled pages
make reindex-incremental                 # embed + upsert changed docs
make search Q="example setup guide"      # BM25 + vector blended retrieval
```

Set `SEEDS_FILE=/path/to/seeds.txt` when seeding the crawler from a curated URL
list instead of a single entrypoint.

## Researcher browser & shadow mode

The `/shipit` workspace now ships with a researcher-focused browser loop that
keeps capture, organisation, and curation entirely local:

- **Multi-tab navigation** with automatic restore. Each tab preserves its
  history, downloads, and last snapshot.
- **Global and per-domain policies** are exposed via `/api/shadow/policy`.
  Toggle the global default from the header or override specific domains from
  the tab strip. Policies persist under
  `data/agent/documents/shadow/policies.json`.
- **Shadow capture** posts to `/api/shadow/snapshot` on navigation. The backend
  fetches HTML (respecting `robots.txt` unless the policy overrides it),
  normalises the page, chunks + embeds it for RAG, and stages JSONL records for
  downstream training. Raw HTML, metadata, and screenshots are stored under
  `data/agent/documents/shadow/{policy}/{domain}/{sha256}/`.
- **Downloads, history, bookmarks, and page info** live in dedicated drawers.
  Artifacts surface byte sizes, direct download links, and “Open in Finder”
  actions. Bookmarks capture folders + tags and can be promoted to the
  allowed-list seed registry via `/api/seeds`.
- The web and desktop shells read `/api/meta/capabilities` on boot, hiding discovery and shadow panels when the backend reports those features as disabled. Shadow toggles now go through `/api/shadow/shadow_config` + `/api/shadow/toggle`, guaranteeing consistent state even when policies are off.

Export staged snapshots with the new CLI helper:

```bash
# Filters: --domain, --policy, --since, --until, --limit
make export-dataset OUT=/tmp/shadow.jsonl ARGS="--domain example.com --since 2025-01-01"
```

Pass `--format=parquet` (or use a `.parquet` extension) to write Parquet files
when `pandas`/`pyarrow` are available in the virtualenv.

## Command quick reference

| Command | Purpose |
| --- | --- |
| `make setup` | Create `.venv`, install Python deps, install Playwright Chromium |
| `make dev` | Launch Flask + Next.js together with shared environment |
| `make stop` | Stop dev servers started by `make dev` (removes `.dev/*.pid`) |
| `make run` | Run the Flask backend only (respects `.env`) |
| `make crawl` | Crawl a URL or seeds file into `data/crawl/` |
| `make normalize` | Convert raw crawl output into normalized JSON lines |
| `make reindex-incremental` | Embed and upsert changed documents into the vector store |
| `make search Q="..."` | Execute a blended CLI search (BM25 + vectors) |
| `make focused Q="..."` | Run the focused crawler for a query (LLM optional) |
| `make llm-status` | Check Ollama reachability via the Flask API |
| `make llm-models` | List chat-capable models reported by Ollama |
| `make tail JOB=focused` | Tail `data/logs/<JOB>.log` (e.g. focused crawl logs) |
| `make export-dataset OUT=... ARGS="..."` | Export staged shadow snapshots to JSONL or Parquet |
| `make check` | Run linting, typing, tests, security, and performance smoke |
| `make clean` | Remove `.venv` and cached data stores |

Use `make help` for the full phony target list (inspect the `Makefile` for more
advanced flows such as `research` or `index-inc`).

## Data & storage layout

Runtime artefacts live under `data/`:

| Path | Purpose |
| --- | --- |
| `data/crawl/` | Raw crawler outputs (HTML, metadata) |
| `data/normalized/normalized.jsonl` | Normalized text documents ready for indexing |
| `data/whoosh/` | On-disk Whoosh BM25 index |
| `data/chroma/` | Local Chroma vector store for embeddings |
| `data/index.duckdb` | DuckDB metadata used for dedupe and incremental indexing |
| `data/agent/` | Planner artefacts (`frontier.sqlite3`, `documents/`, `vector_store/`) |
| `data/logs/` | Log files (e.g. `focused.log`, diagnostics snapshots) |
| `data/telemetry/` | Structured JSON telemetry written by the Flask API |

Override any of these paths through `.env` or by exporting variables before
invoking the relevant Make target (see `Makefile` for the full list). Fast local
storage is strongly recommended because the Flask app and background workers
share the same directories.

## LangSmith tracing

End-to-end traces are emitted via LangSmith + OpenTelemetry when
`LANGSMITH_ENABLED=true` is present in the environment. The integration uses the
official LangSmith Python SDK and reports spans for the focused crawl pipeline
(`crawl → normalize → index → query`), HTTP endpoints (`/api/search`,
`/api/tools/reindex`, `/api/chat`, `/api/search/crawl`), retrieval calls (Whoosh
and Chroma), and LLM invocations (Ollama chat, embeddings, rerank).

Set the following variables in your shell or `.env` file to enable tracing:

```bash
export LANGSMITH_ENABLED=true
export LANGSMITH_API_KEY=...        # issued from app.langchain.com
export LANGSMITH_ENDPOINT=https://api.smith.langchain.com
export LANGSMITH_PROJECT="self-hosted-search"  # optional override
```

When disabled (the default), tracing imports are no-ops. Errors automatically
record the exception class and redact sensitive inputs using the existing
logging sanitiser.

## Testing & quality gates

The repository ships with an opinionated pre-flight suite. Run it before opening
pull requests:

```bash
make check
```

### Dev environment verification

When the stack is running, execute the helper script for quick diagnostics:

```bash
./scripts/dev_verify.sh
```

It checks the frontend/backend listeners, confirms Ollama exposes the expected
model tags (`gpt-oss`, `gemma3`, `embeddinggemma`), exercises the Flask LLM
endpoints (including CORS preflight), and verifies that `/api/crawl` accepts
URLs containing colons in the path.

`make check` executes:

1. `pytest -q` – unit, API, and e2e coverage (including
   `tests/e2e/test_agent_improves_answer.py`).
2. `ruff check` – linting across the maintainer surface (`server`, `scripts`,
   `policy`).
3. `black --check` – formatting guard for select modules.
4. `mypy` – static type analysis (ignoring external stubs).
5. `pip-audit` – dependency vulnerability scan (allowed to warn without failing).
6. `bandit` – security lint for the maintainer entrypoints.
7. `python scripts/perf_smoke.py` – lightweight performance regression check.

For iterative work, a quick smoke test is usually enough:

```bash
pytest -q
```

The change-budget guard (`python scripts/change_budget.py`) enforces ≤10 files
and ≤500 lines of churn for autonomous agents. Invoke it manually to validate
local diffs before committing.

## Observability & debugging

Structured telemetry is written to newline-delimited JSON under
`data/telemetry/events.ndjson`. Tune the location with `LOG_DIR` and the maximum
field length via `LOG_MAX_FIELD_BYTES`. Follow live events with:

```bash
./scripts/tail_telemetry.sh
```

The refresh pipeline now streams normalized documents to SQLite immediately, even
when the embedding model is still warming up. Pending chunks land in the
`pending_documents`, `pending_chunks`, and `pending_vectors_queue` tables inside
`data/app_state.sqlite3`. A background worker drains that queue once Ollama
reports the embedder as ready, keeping partial crawl results searchable via the
BM25 index until vectors become available.

## Migrations & diagnostics

SQLite migrations live in `backend/app/db/migrations/`. Run them and confirm the
schema guardrails with:

```bash
scripts/check_migrations.sh
```

The script provisions a throwaway data directory, initialises the Flask app, and
asserts that `/api/diag/db` reports `ok: true`. The same endpoint powers runtime
checks—hit it manually when debugging deployments:

```bash
curl -s http://localhost:8000/api/diag/db | jq
```

If the response contains `"error": "schema_mismatch"`, the logged `errors`
array explains which column types are out of compliance (e.g. when
`pending_documents.sim_signature` still uses an `INTEGER` type). Apply the
latest migrations and restart the service to recover.

Every Flask request emits `req.start` / `req.end` events with request, session,
and user correlation IDs. Tool invocations emit
`tool.start` / `tool.end` / `tool.error` events with redacted inputs and result
previews. Planner responses append `agent.turn` summaries, and API responses
include a `run_log` array so the UI can surface per-turn activity.

Inspect the learned discovery database at any time:

```bash
sqlite3 data/learned_web.sqlite3 \
  "SELECT query, url, reason, score FROM discoveries ORDER BY discovered_at DESC LIMIT 5;"
```

Focus crawl logs stream to `data/logs/focused.log`. Tail them with
`make tail JOB=focused` while a crawl is active.

## API surface

Key endpoints (all under `/api/` unless otherwise noted):

| Endpoint | Description |
| --- | --- |
| `POST /api/tools/search_index` | Blend vector + BM25 retrieval, falling back to BM25 when embeddings are unavailable. |
| `GET /api/meta/health` | Lightweight readiness probe used by desktop preflight and health checks. |
| `GET /api/meta/capabilities` | Capability map describing search modes, chat availability, discovery gating, and shadow controls. |
| `POST /api/admin/install_models` | Trigger Ollama pulls for chat or embedding models (pass `{ "chat": ["gemma:2b"], "embedding": ["embeddinggemma"] }`). |
| `POST /api/index/search` | Query the vector index with a semantic embedding (`query`) and optional `filters` mapping to constrain metadata fields (e.g. `{ "category": "news" }`). |
| `POST /api/tools/enqueue_crawl` | Queue pages for polite background crawling with dedupe metadata (`topic`, `reason`, `source_task_id`). |
| `POST /api/tools/fetch_page` | Fetch and normalize a single page, storing it under `data/agent/documents/`. |
| `POST /api/tools/reindex` | Incrementally embed + upsert changed documents into the agent vector store (`data/agent/vector_store/`). |
| `GET /api/tools/status` | Return counters for the frontier queue and vector store. |
| `POST /api/tools/agent/turn` | Run the full policy loop (search → fetch ≤3 pages → reindex → synthesize answer with citations). |
| `POST /api/refresh` | Trigger a focused crawl for the supplied query or explicit `seed_ids`; replies with `202` and a JSON status payload. |
| `GET /api/refresh/status` | Report background crawl state (`queued`, `crawling`, `indexing`) plus counters. |
| `GET /api/jobs/<job_id>/status` | Return structured job progress including phase, stats, progress, and ETA. |
| `GET /api/llm/status` | Report Ollama installation status, reachability, and active host. |
| `GET /api/llm/models` | List locally available chat-capable Ollama models (legacy alias for `/api/llm/llm_models`). |
| `POST /api/diagnostics` | Capture repository + runtime snapshot for debugging. |
| `GET /api/meta/time` | Provide server time (local + UTC) and timezone metadata for chat grounding. |
| `GET /api/shadow/shadow_config` | Retrieve persisted shadow-mode configuration and active policy snapshot. |
| `POST /api/shadow/toggle` | Toggle or explicitly set the persisted shadow-mode indexing state by passing `{ "enabled": <bool> }`. |

The agent persists its planning artefacts in `data/agent/`:

- `frontier.sqlite3` stores the crawl queue with `source_task_id`, `topic`, and
  `reason` columns.
- `documents/` holds normalized JSON captures keyed by URL hash.
- `vector_store/` maintains `index.json` + `embeddings.npy` for semantic
  retrieval.

## Discovery & enrichment flows

### Smart search enrichment

The `/search` endpoint now wraps the base Whoosh query with a smart layer. When
fewer than `SMART_MIN_RESULTS` hits return, the app schedules the focused crawl
(`bin/crawl_focused.py`) in the background and immediately responds with the
current results. The focused crawl:

- Builds deterministic candidates from `search/frontier.py` (docs/blog/support
  paths, Read the Docs/GitBook fallbacks, etc.).
- Merges in the highest-scoring domains from the append-only
  `data/seeds.jsonl` store (managed by `search/seeds.py`).
- Optionally asks a local Ollama model for additional URLs through
  `llm/seed_guesser.py` when the UI toggle is on.
- Uses `FOCUSED_CRAWL_BUDGET` as its page limit so a background run stays
  lightweight.
- Records every touched domain back into `data/seeds.jsonl`, gradually improving
  future crawls.

Browser results update automatically: if the initial response returned fewer
than the configured minimum, the UI polls `/search` every four seconds (for ~20
seconds) and re-renders as new hits land.

### Cold-start discovery flow

With the cold-start upgrades the pipeline no longer requires a manual
`make crawl` kick-off. When the index is empty, the first search request:

1. Schedules a focused crawl using `python -m crawler.run` with the configured
   budget.
2. Streams crawler logs to `data/logs/focused.log` and exposes them via
   `/api/focused/status`.
3. Normalizes every newly fetched page with Trafilatura + language detection and
   incrementally indexes changed documents.
4. Emits `last_index_time` so the browser can auto-refresh as new hits land.

`server.discover.DiscoveryEngine` orchestrates this bootstrap. Each time a query
triggers the flow the engine:

- Loads curated registry entries (`seeds/registry.yaml`) and previously learned
  domain hints from `data/learned_web.sqlite3`.
- Adds optional LLM plans from `llm/seed_guesser.py` when the **Use LLM for
  discovery** toggle is on.
- Calls `DiscoveryEngine.discover()` to score and rank `crawler.frontier.Candidate`
  objects, automatically falling back to the registry frontier instead of
  Wikipedia.
- Walks each candidate through the crawler → chunker → embedder pipeline and
  writes embeddings into the vector store.
- Persists the discovery metadata (query, URL, source, score) so subsequent
  searches can reuse the same domains without a fresh crawl.

### Local file discovery

Enable the local discovery watcher by setting `FEATURE_LOCAL_DISCOVERY=1` for
the Flask API and `NEXT_PUBLIC_FEATURE_LOCAL_DISCOVERY=1` for the Next.js app
(both defaults ship in the `.env.example` files). When active the backend starts
a `watchdog` observer for two directories:

- `~/Downloads` (if it exists)
- `data/downloads` (always created so you can drop files from a headless
  environment)

New `.pdf`, `.html`, `.txt`, or `.md` files are parsed server-side (PDFs via
`pdfminer`, HTML via BeautifulSoup) and broadcast to the UI using SSE. The UI
shows a floating banner—"Found file: …"—with **Include** and **Dismiss**
actions. Choosing **Include** calls `/api/index/upsert` with the extracted text
and stores a confirmation so the same file will not be re-suggested after a
restart. Dismissing records the file path and modification time in
`data/agent/local_discovery_confirmations.json` so subsequent downloads with the
same timestamp are ignored.

Drop a PDF into either watch directory while the stack is running to see the
notification and index the document on demand.

### Manual refresh controls

Trigger a focused crawl on demand by clicking **Refresh now** in the web UI. The
button lives under the status banner and:

- Calls `POST /api/refresh` with the current query, LLM toggle, and optional
  model override.
- Streams progress from the background worker (`queued → crawling → indexing`)
  into a compact progress bar.
- Unlocks once the run finishes so you can retry with a different prompt.

The same API is available for automation:

```bash
curl -X POST http://127.0.0.1:5050/api/refresh \
  -H 'Content-Type: application/json' \
  -d '{"query": "postgres vacuum best practices", "use_llm": true, "model": "llama3.1:8b-instruct"}'

curl "http://127.0.0.1:5050/api/refresh/status?job_id=<hex>&query=postgres%20vacuum%20best%20practices"
```

`POST` now guarantees a JSON response, even when the crawl is merely queued. A
successful request returns HTTP 202 with
`{"status":"queued","seed_ids":[...],"job_id":"<hex>","created":true}`. When a
matching job is already running the same payload is returned with
`"deduplicated": true`. Always inspect the HTTP status before piping the body to
`jq`—error responses are JSON too, but failed requests still carry meaningful
status codes.

Prefer the helper script during development:

```bash
scripts/refresh.sh workspace-example-seed
```

The script builds the required payload, POSTs it to `/api/refresh`, and prints
both the HTTP status and JSON body in a shell-friendly format.

**Tip:** Don’t pipe `/api/refresh` directly into `jq` unless you have confirmed
the response is JSON (status 202/200). Validation failures still return JSON
errors, but scripts should always check the HTTP status first.

`GET /api/refresh/status` yields the current snapshot (`state`, `progress`, and
counters for seeds/pages/docs). When no `job_id` is supplied the endpoint falls
back to the most recent run for the supplied query or lists active jobs.

Invoke the same functionality from the CLI:

```bash
make focused Q="postgres vacuum best practices" USE_LLM=1 MODEL="llama3.1:8b-instruct"
make tail JOB=focused
```

The command honours `.env`, allows a one-off `BUDGET=...` override, and respects
`CRAWL_RESPECT_ROBOTS` unless you disable it.

## LLM integration

### LLM Assist panel

The Next.js UI includes an **LLM Assist** panel that:

- Calls `GET /api/llm/models` to retrieve chat-capable models and the configured
  primary/fallback pair. The dropdown appears only when the backend detects at
  least one chat model and the selection is persisted in `localStorage`
  (`chat:model`).
- When no chat models exist locally and you set `DEV_ALLOW_AUTOPULL=true`, the
  UI surfaces an “Install model” banner that triggers the safe development-only
  `/api/llm/autopull` endpoint (prefers Gemma3, falls back to gpt-oss) and polls
  until the model is ready.
- Adds a **Page context** panel that captures the active preview tab via
  `POST /api/extract` (Playwright + Trafilatura). When the selected model
  supports vision, a base64 PNG screenshot is attached and the next chat request
  automatically includes `{ url, text_context, image_context }`.
- Assistant responses adhere to a strict schema, splitting **Answer** and
  collapsible **Reasoning**, and listing any citations returned by the model.

Install and start Ollama locally (macOS example):

```bash
brew install --cask ollama
ollama serve
ollama pull gpt-oss
ollama pull gemma3
ollama pull embeddinggemma
```

### Embedding model defaults

- The backend defaults to the `embeddinggemma` embedder, with `gpt-oss` as the
  primary chat model and `gemma3` as the fallback. On the first semantic search
  the Flask API checks whether the models exist locally, streams
  `ollama pull` progress to the UI, and queues concurrent queries until
  embeddings are available.
- Pull the models manually if you prefer:

  ```bash
  ollama pull gpt-oss gemma3 embeddinggemma
  ```

- Configure overrides with environment variables:
  - `RAG_EMBED_MODEL_NAME` – embedding model name (defaults to
    `embeddinggemma`).
  - `PLANNER_FALLBACK` – override the planner fallback chat model (defaults to
    the value in `config.yaml`).
  - `OLLAMA_HOST` – Ollama base URL (defaults to `http://127.0.0.1:11434`).

Troubleshooting tips when auto-install stalls:

- **Disk space** – ensure Ollama has several GB free. Remove older models with
  `ollama rm <name>` if pulls fail with `no space left on device`.
- **Network stalls** – verify the host can reach `https://registry.ollama.ai`.
  The UI exposes a retry button and fallback picker, or you can pre-download the
  model into the Ollama cache.
- **Runtime offline** – the “Start Ollama” button issues
  `brew services start ollama` / `systemctl start ollama` depending on the
  platform and surfaces errors when the daemon remains offline.

Once embeddings are available and `ollama serve` is running, `/api/search`
responses return `200` and repeat queries reuse the cached vectors immediately.

Verify connectivity via the Make targets:

```bash
make llm-status
make llm-models
```

Run `scripts/dev_verify.sh` to print the detected models, Ollama health, and a
chat fallback smoke test in one go.

The default behaviour stays fully local: no external APIs are contacted unless
Ollama is enabled. Set `SMART_USE_LLM=true` in `.env` if you want the toggle
pre-enabled for every user.

## Chat + Page Context + Tools

- `/api/chat` accepts `{ model, messages[], stream }` payloads and streams
  NDJSON deltas. The frontend automatically retries without streaming when the
  browser runtime cannot consume a stream, and surfaces the model + trace ID
  from the response.
- A **Use page context** toggle now lives next to the model picker. When
  enabled, the UI captures the active tab’s URL + selection, calls
  `/api/chat/<thread_id>/context?include=selection,history,metadata`, prepends
  the resolved context as a system message, and shows an indicator pill with the
  current host and word count.
- Assistant replies can include `autopilot.tools` directives. The chat panel
  renders each entry as a chip that POSTs to `/api/tools/*`, reporting success
  or errors inline so you can drive the built-in browser helpers without
  leaving the conversation.
- The diagnostics job adds a “Chat OK” probe (`POST /api/chat` with
  `stream:false`), recording the status, model, and preview text in the
  generated summary.

## Shadow mode & embedding queue

- **Default OFF.** The browser shadow crawler now ships disabled on first boot
  and the UI exposes an explicit toggle. The selection persists in the
  `app_settings` table so restarts keep your preference.
- **Progress tracking.** Every background job surfaces a structured payload via
  `GET /api/jobs/<id>/status` (and `/progress`). Phases advance through
  `fetching → extracted → embedding → warming_up/indexed` with step counts,
  retry counters, and ETA estimates. The Next.js header mirrors this with a
  progress bar and status badge.
- **Warm-up awareness.** When the embedding model is still loading, documents
  are stored immediately and appear under the “Pending embeds” card until the
  background worker drains them. The UI highlights `Embedding model warming up`
  instead of failing jobs.
- **Heavier pages.** Playwright navigation now retries with
  `wait_until="domcontentloaded"` and a 120s timeout when the initial
  `networkidle` pass times out, improving reliability on script-heavy domains.
- **Troubleshooting.** The backend keeps a small history of pending chunks with
  retry counts and last errors (`GET /api/docs/pending`). Use it alongside the
  job progress view when diagnosing cold starts or slow embeds.

### Planner LLM fallback

- `models.llm_primary` in `config.yaml` selects the planner's primary Ollama
  model.
- `models.llm_fallback` defines an optional backup used when the primary returns
  `404` / `model not found`.
- Pull at least one model locally (`ollama pull gpt-oss:20b`,
  `ollama pull gemma3:27b`, etc.).
- When both models are missing the planner responds with
  `{ "type": "final", "answer": "Planner LLM is unavailable." }` so the UI can
  degrade gracefully.

### Planner loop controls

- `planner.enable_critique` gates the optional critique-and-retry stage. Leave it
  `false` to preserve the classic step semantics in automated tests, and enable
  it when you want the planner to request structured feedback before
  finalizing.
- `planner.max_steps` caps the number of tool executions or final responses in a
  single run. Hitting the limit now returns a structured
  `stop_reason="max_steps"` response instead of throwing a graph recursion
  error.
- `planner.max_retries_per_step` bounds how many planner-only retries (LLM
  replans, critique revisions, validation failures) are allowed between tool
  calls. When exceeded, the planner exits cleanly with
  `stop_reason="retry_limit"` so callers can surface a useful error.

### Debug traces

- Every backend request now emits single-line JSON logs containing
  `trace`, `method`, `path`, status codes, and chat metadata. Example:
  `{"lvl":"INFO","evt":"http.request","trace":"req_abc123","path":"/api/chat"}`.
- The same `trace_id` is exposed via the `X-Request-Id` response header and is
  included in chat error payloads. Copy the value into the browser console logs
  (prefixed with `[UI]`) to correlate UI actions with backend activity when
  debugging end-to-end flows.

## Diagnostics snapshot API

Operators can capture the current repository state and runtime logs without
leaving the browser. `POST /api/diagnostics` enqueues a background job and
returns `{ "job_id": "<hex>" }`. Poll `/api/jobs/<job_id>/status` until `state`
becomes `done`; the `result` payload contains:

- `summary_markdown` – rendered report with git metadata, dependency versions,
  and log excerpts.
- `summary_path` – on-disk markdown file under `data/logs/diagnostics/` that can
  be downloaded for full context.
- Structured fields for git status, dependency snapshots, and the optional
  `pytest --collect-only` run.

Toggle expensive steps through environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DIAGNOSTICS_RUN_PYTEST` | `false` | Enable `pytest --collect-only -q` inside the diagnostics job (override per-request with `{ "include_pytest": true }`). |
| `DIAGNOSTICS_PYTEST_ARGS` | *(empty)* | Extra CLI arguments appended to the pytest collect command. |
| `DIAGNOSTICS_CMD_TIMEOUT` | `60` | Seconds before git/pytest/pip commands are aborted. |
| `DIAGNOSTICS_LOG_FILES` | `3` | Number of recent `*.log` files to sample from `data/logs`. |
| `DIAGNOSTICS_LOG_LINES` | `40` | Tail length captured for each sampled log file. |

Example macOS workflow:

```bash
source .venv/bin/activate
curl -X POST http://127.0.0.1:5050/api/diagnostics \
     -H 'Content-Type: application/json' \
     -d '{"include_pytest": true}'
# => {"job_id":"abc123..."}
curl http://127.0.0.1:5050/api/jobs/abc123.../status | jq .result.summary_path
```

## Continuous integration

GitHub Actions runs `make check` on Python 3.11 and enforces the same change
budget guard used locally. Linting covers Ruff, Black (check mode), and Mypy for
the maintainer surface; pytest exercises the full suite; `pip-audit` and Bandit
scan the policy-limited paths. The guard fails the build if a staged diff exceeds
50 files or 4,000 lines.

Maintainer autonomy defaults to **Observe** (read-only). Promote to **Patch** to
allow applying a diff after every gate passes. **Maintainer** unlocks multi-file
refactors while still respecting the budgets enforced by `policy/allowlist.yml`.
Regardless of autonomy level, always plan → patch → verify → document risks and
rollback steps before opening a PR.
